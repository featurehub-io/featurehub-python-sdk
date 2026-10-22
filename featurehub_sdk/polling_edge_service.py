from typing import Optional

import re
import urllib3
import threading
import logging
import json
import asyncio
import time
from hashlib import sha256
from typing import List
from featurehub_sdk.edge_service import EdgeService, _env_seconds
from featurehub_sdk.featurehub_repository import FeatureHubRepository
from featurehub_sdk.version import sdk_version

log = logging.getLogger('featurehub_sdk')

class PollingEdgeService(EdgeService):
    # how long (in seconds) a request to the server may take before it is abandoned, overridden by
    # FEATUREHUB_POLLING_TIMEOUT
    TIMEOUT = 12.0

    _interval: int
    _repository: FeatureHubRepository
    _cancel: bool
    _closed: bool
    _worker: Optional[threading.Thread]
    _cond: threading.Condition
    _wakeup: threading.Event
    _requested: int
    _completed: int
    _client_eval: bool
    _stopped: bool
    _invalid_key: bool
    _timeout: float
    _http: urllib3.PoolManager
    _cache_control_pattern: re.Pattern
    _sha_context: Optional[str]
    _etag: Optional[str]

    def __init__(self, edge_url: str, api_keys: List[str],
                 repository: FeatureHubRepository,
                 interval: int):
        self._interval = interval
        self._repository = repository
        self._cancel = False
        self._closed = False
        self._stopped = False
        self._invalid_key = False
        # all requests to the server are made by a single worker thread, so there is only ever one in flight.
        # poll() and context_change() ask the worker for a fetch (bumping _requested) and wait until a fetch that
        # started after their request has finished (_completed catches up). _cond guards all of this state.
        self._worker = None
        self._cond = threading.Condition()
        self._wakeup = threading.Event()
        self._requested = 0
        self._completed = 0
        self._client_eval = '*' in api_keys[0]
        self._context = None
        self._etag = None
        self._sha_context = None
        self._timeout = _env_seconds('FEATUREHUB_POLLING_TIMEOUT', self.TIMEOUT)
        self._http = urllib3.PoolManager()
        self._cache_control_pattern = re.compile('max-age=(\\d+)')

        self._url = f"{edge_url}features?" + "&".join(map(lambda i: 'apiKey=' + i, api_keys))
        log.debug(f"polling url {self._url}")

    # allow us to update the interval of the current polling edge service
    def update_interval(self, interval: int):
        with self._cond:
            self._interval = interval
            # polling stopped by an invalid key (404) or a stale environment stays stopped
            if self._invalid_key or self._stopped:
                return
            if self._closed:  # close() stopped polling, so start it again
                self._closed = False
                self._cancel = False
                self._request_fetch()
            elif self._worker is not None:
                self._wakeup.set()  # so the worker waits for the new interval instead of the old one
            elif interval > 0:
                self._request_fetch()

    # this does the business, calls the remote service and gets the features back. only the worker thread calls it
    def _get_updates(self):
        with self._cond:  # context_change() can update these from another thread
            context = self._context
            sha_context = "0" if self._sha_context is None else self._sha_context
        url = f"{self._url}&contextSha={sha_context}"

        log.debug("polling %s", url)
        headers = {
            'X-SDK': 'Python',
            'X-SDK-Version': sdk_version
        }

        if self._etag:
            headers['if-none-match'] = self._etag

        if context:
            headers['x-featurehub'] = context

        try:
            resp = self._http.request(method='GET', url=url, headers=headers, timeout=self._timeout)
            log.debug("polling status %s", resp.status)

            if resp.status == 200 or resp.status == 236:
                self._process_successful_results(json.loads(resp.data.decode('utf-8')))

                # only keep the etag once the body has been processed, otherwise a bad body would be followed by
                # 304s for that etag and the features would never be fetched again
                if 'etag' in resp.headers:
                    self._etag = resp.headers['etag']

                if 'cache-control' in resp.headers:
                    self._cache_control_polling_interval(resp.headers['cache-control'])

                # if it is a 236, we have been told to stop
                if resp.status == 236:
                    self._stopped = True
                return
        except (ValueError, urllib3.exceptions.HTTPError) as err:
            # HTTPError is the base of all urllib3 errors, including failing to connect at all. ValueError covers
            # a body that isn't valid JSON/UTF-8. Either way it is transient, so the next poll tries again
            log.error("failed to poll featurehub: %s", err)
            return
        except Exception:
            # anything else (unexpected response shape, a failing repository listener) must not stop polling either
            log.exception("failed to process featurehub poll")
            return

        if resp.status == 404: # no such key
            self._repository.notify("failed", None)
            with self._cond:
                self._invalid_key = True
                self._cancel = True
            log.error("Specified API Key does not exist %s", self._url)
        elif resp.status == 503:
            # dacha is busy, just wait
            return
        # otherwise its likely a transient failure, so keep trying

    def _cache_control_polling_interval(self, cache_control: str):
        max_age = re.findall(self._cache_control_pattern, cache_control)
        if max_age: # not none and not empty
            new_interval = int(max_age[0])
            if new_interval > 0:
                self._interval = new_interval

    # the worker: fetch, then wait for the interval (or until a fetch is asked for), and repeat. it stops when
    # cancelled, when the server says the environment is stale, or - with an interval of 0 - once nothing is waiting
    def _run(self):
        try:
            while True:
                with self._cond:
                    if self._finished():
                        return
                    # cleared before reading _requested, so a request made from here on causes another fetch
                    self._wakeup.clear()
                    covers = self._requested

                self._get_updates()

                with self._cond:
                    self._completed = covers
                    self._cond.notify_all()
                    if self._finished():
                        return

                self._wait_for_next_fetch()
        finally:
            with self._cond:
                # only still set if the worker died unexpectedly, so waiters aren't left waiting on it
                if self._worker is threading.current_thread():
                    self._worker = None
                self._cond.notify_all()

    # must be called holding self._cond. decides whether the worker should stop, and if so clears _worker in the same
    # locked block, so a request can't slip in between and find a worker that is about to exit and never serves it
    def _finished(self) -> bool:
        pending = self._requested > self._completed
        if self._cancel or self._stopped or (not pending and self._interval <= 0):
            self._worker = None
            self._cond.notify_all()
            return True
        return False

    # waits out the interval from now, waking early for a fetch request, a close or a change to the interval
    def _wait_for_next_fetch(self):
        started = time.monotonic()
        while True:
            with self._cond:
                if self._cancel or self._stopped or self._requested > self._completed or self._interval <= 0:
                    return
                remaining = started + self._interval - time.monotonic()
                if remaining <= 0:
                    return
                self._wakeup.clear()
            self._wakeup.wait(remaining)

    # must be called holding self._cond. returns the request number to wait for, or None if polling has stopped
    def _request_fetch(self) -> Optional[int]:
        if self._cancel or self._stopped:
            return None
        self._requested += 1
        self._wakeup.set()
        if self._worker is None:
            self._worker = threading.Thread(target=self._run, name="polling-featurehub", daemon=True)
            self._worker.start()
        return self._requested

    def _wait_for_fetch(self, request: Optional[int]):
        if request is None:
            return
        with self._cond:
            self._cond.wait_for(lambda: self._completed >= request or self._worker is None or self._cancel)

    # fetches the features (on the worker thread) and waits for them, starting polling if it isn't running.
    # if the interval is zero, this will just issue a get updates and stop
    async def poll(self):
        with self._cond:
            if self._invalid_key:  # don't try again with a key the server rejected (404)
                return
            self._cancel = False
            self._closed = False
            request = self._request_fetch()
        if request is None:  # the environment is stale, so the server told us to stop asking
            return
        # wait on another thread so a running event loop isn't blocked
        await asyncio.to_thread(self._wait_for_fetch, request)

    def client_evaluated(self):
        return self._client_eval

    def close(self):
        with self._cond:
            self._cancel = True
            self._closed = True
            self._wakeup.set()
            self._cond.notify_all()

    async def context_change(self, header: str):
        with self._cond:
            old_context = self._context
            self._context = header
            self._sha_context = sha256(header.encode('utf-8')).hexdigest()
            request = self._request_fetch() if old_context != header else None
        if request is None:
            return
        await asyncio.to_thread(self._wait_for_fetch, request)

    @property
    def cancelled(self):
        return self._cancel

    @property
    def stopped(self):
        return self._stopped

    @property
    def interval(self):
        return self._interval

    # we get returned a bunch of environments for a GET/Poll API so we need to cycle through them
    # the result is different for streaming
    def _process_successful_results(self, data):
        log.debug("featurehub polling data was %s", data)
        for feature_apikey in data:
            if feature_apikey:
                self._repository.notify("features", feature_apikey['features'])
