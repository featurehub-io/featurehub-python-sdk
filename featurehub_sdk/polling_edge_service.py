from typing import Optional

import re
import urllib3
import threading
import logging
import json
import asyncio
from hashlib import sha256
from typing import List
from featurehub_sdk.edge_service import EdgeService
from featurehub_sdk.featurehub_repository import FeatureHubRepository
from featurehub_sdk.version import sdk_version

log = logging.getLogger('featurehub_sdk')

class PollingEdgeService(EdgeService):
    _interval: int
    _repository: FeatureHubRepository
    _cancel: bool
    _thread: Optional[threading.Timer]
    _client_eval: bool
    _stopped: bool
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
        self._stopped = False
        self._thread = None
        self._client_eval = '*' in api_keys[0]
        self._context = None
        self._etag = None
        self._sha_context = None
        self._http = urllib3.PoolManager()
        self._cache_control_pattern = re.compile('max-age=(\\d+)')

        self._url = f"{edge_url}features?" + "&".join(map(lambda i: 'apiKey=' + i, api_keys))
        log.debug(f"polling url {self._url}")

    # allow us to update the interval of the current polling edge service
    def update_interval(self, interval: int):
        self._interval = interval
        old_cancel = self._cancel
        self._cancel = False
        if old_cancel:  # if we had cancelled, start polling again
            self.poll_with_interval()

    # this does the business, calls the remote service and gets the features back
    async def _get_updates(self):
        # TODO: set timeout of tcp requests to 12 seconds, or give users control over it using environ vars
        sha_context = "0" if self._sha_context is None else self._sha_context
        url = f"{self._url}&contextSha={sha_context}"

        log.debug("polling %s", url)
        headers = {
            'X-SDK': 'Python',
            'X-SDK-Version': sdk_version
        }

        if self._etag:
            headers['if-none-match'] = self._etag

        if self._context:
            headers['x-featurehub'] = self._context

        resp = self._http.request(method='GET', url=url, headers=headers)
        log.debug("polling status %s", resp.status)

        if resp.status == 200 or resp.status == 236:
            if 'etag' in resp.headers:
                self._etag = resp.headers['etag']

            if 'cache-control' in resp.headers:
                self._cache_control_polling_interval(resp.headers['cache-control'])

            self._process_successful_results(json.loads(resp.data.decode('utf-8')))

            # if it is a 236, we have been told to stop
            if resp.status == 236:
                self._stopped = True
        elif resp.status == 404: # no such key
            self._repository.notify("failed", None)
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

    # this is essentially a repeating task because it "calls itself"
    # another way to do this is with a separate class that is itself a thread descendant
    # which waits for the requisite time,  then triggers a callback and then essentially does the same thing
    # if we need a repeating task elsewhere, we should consider refactoring this
    async def poll_with_interval(self):
        if not self._cancel and not self._stopped:
            await self._get_updates()
            if not self._cancel and self._interval > 0:
                self._thread = threading.Timer(self._interval, self.poll_again)
                self._thread.daemon = True # allow it to just disappear off if the app closes down
                self._thread.start()

    # this ends up being synchronous
    def poll_again(self):
        asyncio.run(self.poll_with_interval())

    # async polls, you can choose not to wait for updates
    # if the interval is zero, this will just issue a get updates and stop
    async def poll(self):
        self._cancel = False
        await self.poll_with_interval()

    def client_evaluated(self):
        return self._client_eval

    def close(self):
        self._cancel = True
        if self._thread is not None:
            self._thread.cancel()
            self._thread = None

    async def context_change(self, header: str):
        old_context = self._context
        self._context = header
        self._sha_context = sha256(header.encode('utf-8')).hexdigest()
        if old_context != header:
            await self._get_updates()

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
