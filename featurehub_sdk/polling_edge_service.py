from typing import Optional

import httpx
import urllib3
import threading
import logging
import sys
import json
import asyncio
from featurehub_sdk.edge_service import EdgeService
from featurehub_sdk.featurehub_repository import FeatureHubRepository
from featurehub_sdk.version import sdk_version

log = logging.getLogger(sys.modules[__name__].__name__)

class PollingEdgeService(EdgeService):
    _interval: int
    _repository: FeatureHubRepository
    _cancel: bool
    _thread: Optional[threading.Timer]
    _client_eval: bool
    _http: urllib3.PoolManager

    def __init__(self, edge_url: str, api_keys: list[str],
                 repository: FeatureHubRepository,
                 interval: int):
        self._interval = interval
        self._repository = repository
        self._cancel = False
        self._thread = None
        self._client_eval = '*' in api_keys[0]
        self._context = None
        self._http = urllib3.PoolManager()

        self._url = f"{edge_url}/features?" + "&".join(map(lambda i: 'apiKey=' + i, api_keys))
        log.debug(f"polling url {self._url}")

    # allow us to update the interval of the current polling edge service
    def update_interval(self, interval: int):
        self._interval = interval
        old_cancel = self._cancel
        self._cancel = False
        if not old_cancel:
            self.poll_with_interval()

    # this does the business, calls the remote service and gets the features back
    async def _get_updates(self):
        # TODO: set timeout of tcp requests to 12 seconds, or give users control over it using environ vars
        url = self._url if self._context is None else f"{self._url}&{self._context}"
        log.log(5, "polling ", url)
        resp = self._http.request(method='GET', url=url, headers={'X-SDK:': 'Python', 'X-SDK-Version': sdk_version})
        log.log(5, "polling status", resp.status)
        if resp.status == httpx.codes.OK:
            self._process_successful_results(json.loads(resp.data.decode('utf-8')))
        elif resp.status == 404: # no such key
            self._repository.notify("failed", None)
            self._cancel = True
        elif resp.status == 503:
            # dacha is busy, just wait
            return
        # otherwise its likely a transient failure, so keep trying

    # this is essentially a repeating task because it "calls itself"
    # another way to do this is with a separate class that is itself a thread descenddant
    # which waits for the requisite time,  then triggers a callback and then essentially does the same thing
    # if we need a repeating task elsewhere, we should consider refactoring this
    async def poll_with_interval(self):
        if not self._cancel:
            await self._get_updates()
            if not self._cancel and self._interval > 0:
                self._thread = threading.Timer(self._interval, self.poll_again)
                self._thread.daemon = True # allow it to just disappear off if the app closes down
                self._thread.start()

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
        if old_context != header:
            await self._get_updates()

    # we get returned a bunch of environments for a GET/Poll API so we need to cycle through them
    # the result is different for streaming
    def _process_successful_results(self, data):
        print(f"data was {data}")
        for feature_apikey in data:
            if feature_apikey:
                self._repository.notify("features", feature_apikey['features'])
