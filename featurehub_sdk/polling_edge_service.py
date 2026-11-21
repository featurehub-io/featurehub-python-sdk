from typing import Optional

import re
import urllib3
import threading
import logging
import json
import asyncio
import time
from hashlib import sha256
from typing import Dict, List
from featurehub_sdk.edge_service import EdgeService, _env_seconds, _request_headers
from featurehub_sdk.featurehub_repository import FeatureHubRepository
from featurehub_sdk.version import sdk_version

log = logging.getLogger('featurehub_sdk')

# no polling interval other than 0 (poll once) may be shorter than this, so no configuration polls the server too often.
# a Cache-Control max-age below it is raised to it. only the SDK's own tests change it
_MIN_POLLING_INTERVAL = 5


def validate_poll_interval(interval) -> None:
    if isinstance(interval, bool) or not isinstance(interval, (int, float)):
        raise ValueError(f"polling interval must be a number of seconds, not {interval!r}")
    if interval < 0:
        raise ValueError(f"polling interval must not be negative ({interval})")
    if 0 < interval < _MIN_POLLING_INTERVAL:
        raise ValueError(f"polling interval must be 0 (poll once) or at least {_MIN_POLLING_INTERVAL} seconds "
                         f"({interval})")


class PollingEdgeService(EdgeService):
    # how long (in seconds) a request to the server may take before it is abandoned, overridden by
    # FEATUREHUB_POLLING_REQ_TIMEOUT
    TIMEOUT = 12.0

    _interval: int
    _repository: FeatureHubRepository
    _cancel: bool
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
    _headers: Dict[str, str]
    _started: bool
    _single_fetch: bool
    _passive: bool
    _last_fetch: Optional[float]

    # headers are extra headers sent with every request (e.g. for an API gateway); the SDK's own headers win over
    # any of the same name.
    # active polling (the default) fetches every interval. passive polling doesn't use a timer: after the first fetch,
    # it fetches again only when features are read (refresh_if_stale) and the last fetch is older than the interval;
    # with an interval of 0 it never fetches again
    def __init__(self, edge_url: str, api_keys: List[str],
                 repository: FeatureHubRepository,
                 interval: int,
                 headers: Optional[Dict[str, str]] = None,
                 passive: bool = False):
        validate_poll_interval(interval)
        self._interval = interval
        self._passive = passive
        # when the last fetch finished (successful or not), so passive polling knows how old the features are
        self._last_fetch = None
        self._headers = dict(headers) if headers else {}
        self._repository = repository
        self._cancel = False
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
        # poll() (or a context change) has started polling, so update_interval() may start it again
        self._started = False
        # closed, but fetching once for a context change: once that is done it is closed again
        self._single_fetch = False
        self._timeout = _env_seconds('FEATUREHUB_POLLING_REQ_TIMEOUT', self.TIMEOUT)
        self._http = urllib3.PoolManager()
        self._cache_control_pattern = re.compile('max-age=(\\d+)')

        self._url = f"{edge_url}features?" + "&".join(map(lambda i: 'apiKey=' + i, api_keys))
        log.debug(f"polling url {self._url}")

    # allow us to update the interval of the current polling edge service
    def update_interval(self, interval: int):
        validate_poll_interval(interval)
        with self._cond:
            self._interval = interval
            # polling stopped by a rejected key or a stale environment stays stopped, and polling that hasn't been
            # started yet (by poll() or init()) isn't started by changing its interval
            if self._invalid_key or self._stopped or not self._started:
                return
            if self._passive:  # nothing is scheduled: the next read uses the new interval
                self._cancel = False
                self._single_fetch = False
                return
            if self._cancel or self._single_fetch:  # close() stopped polling, so start it again
                self._cancel = False
                self._single_fetch = False
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
        sdk_headers = {
            'X-SDK': 'Python',
            'X-SDK-Version': sdk_version
        }

        if self._etag:
            sdk_headers['if-none-match'] = self._etag

        if context:
            sdk_headers['x-featurehub'] = context

        headers = _request_headers(self._headers, sdk_headers)

        try:
            resp = self._http.request(method='GET', url=url, headers=headers, timeout=self._timeout)
            log.debug("polling status %s", resp.status)

            with self._cond:
                if self._cancel:  # closed while the request was in flight, so the response is no longer wanted
                    return

            if resp.status == 200 or resp.status == 236:
                self._process_successful_results(json.loads(resp.data.decode('utf-8')))

                # only keep the etag once the body has been processed, otherwise a bad body would be followed by
                # 304s for that etag and the features would never be fetched again. it belongs to the context it was
                # fetched for, so it isn't kept if the context changed while the request was in flight
                if 'etag' in resp.headers:
                    with self._cond:
                        if self._context == context:
                            self._etag = resp.headers['etag']

                if 'cache-control' in resp.headers:
                    self._cache_control_polling_interval(resp.headers['cache-control'])

                # if it is a 236, the environment is stale: it will never change, so stop for good
                if resp.status == 236:
                    with self._cond:
                        self._stopped = True
                    log.warning("environment is stale, stopped requesting updates")
                    self._repository.mark_environment_stale()
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

        if 400 <= resp.status < 500:  # the key or environment is rejected (any 4xx, 429 included), so stop for good
            self._repository.notify("failed", None)
            with self._cond:
                self._invalid_key = True
                self._cancel = True
            log.error("featurehub rejected the API key with status %s, stopped polling %s", resp.status, self._url)
        elif resp.status == 304:
            log.debug("featurehub features unchanged")
        elif resp.status == 503:
            # dacha is busy, just wait
            return
        else:
            # otherwise its likely a transient failure, so keep trying
            log.error("featurehub returned unexpected status %s", resp.status)

    def _cache_control_polling_interval(self, cache_control: str):
        max_age = re.findall(self._cache_control_pattern, cache_control)
        if max_age: # not none and not empty
            new_interval = int(max_age[0])
            if new_interval > 0:
                with self._cond:  # update_interval() can change it from another thread
                    if self._interval <= 0:  # an interval of 0 polls once, a max-age doesn't start polling again
                        return
                    self._interval = max(new_interval, _MIN_POLLING_INTERVAL)

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
                    self._last_fetch = time.monotonic()
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
    # locked block, so a request can't slip in between and find a worker that is about to exit and never serves it.
    # a stale environment requests nothing more, not even fetches already asked for. passive polling schedules nothing,
    # so its worker stops once the fetches asked for are done
    def _finished(self) -> bool:
        pending = self._requested > self._completed
        if self._cancel or self._stopped or \
                (not pending and (self._interval <= 0 or self._single_fetch or self._passive)):
            if self._single_fetch:  # the context change's fetch after close() is done, so it is closed again
                self._single_fetch = False
                self._cancel = True
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

    # must be called holding self._cond. passive polling: whether the features are older than the interval (or have
    # never been fetched) and nothing is being fetched. a failed fetch counts too, so it isn't retried before the
    # interval is up
    def _needs_refresh(self) -> bool:
        if self._cancel or self._stopped or self._invalid_key or self._requested > self._completed:
            return False
        if self._last_fetch is None:
            return True
        return self._interval > 0 and time.monotonic() - self._last_fetch >= self._interval

    # passive polling: called as features are read. fetches in the background if the features are older than the
    # interval, without waiting for it. does nothing for active polling, or before polling has been started
    def refresh_if_stale(self):
        if not self._passive:
            return
        with self._cond:
            if self._started and self._needs_refresh():
                self._request_fetch()

    # fetches the features (on the worker thread) and waits for them, starting polling if it isn't running.
    # if the interval is zero, this will just issue a get updates and stop. passive polling only fetches the first
    # time, and then whenever the features are older than the interval
    async def poll(self):
        with self._cond:
            if self._invalid_key:  # don't try again with a key the server rejected (404)
                return
            self._cancel = False
            self._single_fetch = False
            if self._passive and self._started and not self._needs_refresh():
                return
            self._started = True
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
            self._single_fetch = False
            self._wakeup.set()
            self._cond.notify_all()

    # fetches the features for a new context, or reports the failure for a rejected key. if polling was closed it
    # fetches once and stays closed. once the environment is stale nothing more can be fetched, so the last features
    # are kept
    async def context_change(self, header: str):
        with self._cond:
            old_context = self._context
            self._context = header
            self._sha_context = sha256(header.encode('utf-8')).hexdigest() if header else None
            if old_context == header or self._stopped:
                return
            # the etag belongs to the old context: a 304 for it would leave the old context's features
            self._etag = None
            invalid_key = self._invalid_key
            if not invalid_key:
                if self._cancel:
                    self._cancel = False
                    self._single_fetch = True
                elif not self._single_fetch:
                    self._started = True
                request = self._request_fetch()
        if invalid_key:  # don't try again with a key the server rejected (the repository already knows it failed)
            self._repository.notify("failed", None)
            return
        await asyncio.to_thread(self._wait_for_fetch, request)

    @property
    def cancelled(self):
        return self._cancel

    @property
    def stopped(self):
        return self._stopped

    @property
    def passive(self):
        return self._passive

    @property
    def interval(self):
        return self._interval

    # we get returned an environment for each API key. together their features are one full set, so they are given to
    # the repository at once - one environment at a time would remove the features of the others
    def _process_successful_results(self, data):
        log.debug("featurehub polling data was %s", data)
        if not isinstance(data, list):
            raise ValueError(f"expected a list of environments, got {type(data).__name__}")
        features = []
        for environment in data:
            if not environment:
                continue
            if not isinstance(environment, dict) or not isinstance(environment.get('features', []), list):
                raise ValueError("expected each environment to have a list of features")
            features.extend(environment.get('features') or [])
        self._repository.notify("features", features)
