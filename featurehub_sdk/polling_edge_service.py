import os

import httpx
import threading
from featurehub_sdk.edge_service import EdgeService
from featurehub_sdk.featurehub_repository import FeatureHubRepository

class PollingEdgeService(EdgeService):

    def __init__(self, edge_url: str, *api_keys: list[str],
                 repository: FeatureHubRepository,
                 interval: int = int(os.environ.get("FEATUREHUB_POLL_INTERVAL", "30"))):
        self._interval = interval
        self._repository = repository
        self._cancel = None
        self._thread = None
        self._client_eval = '*' in api_keys[0]
        self._context = None

        self._url = f"{edge_url}/features?" + "&".join(map(lambda i: 'apiKey=' + i, api_keys))

        self.poll()

    # allow us to update the interval of the current polling edge service
    def update_interval(self, interval: int):
        self._interval = interval
        old_cancel = self._cancel
        self._cancel = None
        if old_cancel.is_set():
            self.poll_with_interval()

    # this does the business, calls the remote service and gets the features back
    async def _get_updates(self):
        # TODO: set timeout of tcp requests to 12 seconds, or give users control over it using environ vars
        with httpx.Client(http2=True) as client:
            if self._context is not None:
                client.headers = {'x-featurehub': self._context}

            resp = client.get(self._url)
            if resp.status_code == httpx.codes.OK:
                self._process_successful_results(resp.json())
            elif resp.status_code == 404: # no such key
                self._repository.notify("FAILED", None)
                self._cancel = True
            elif resp.status_code == 503:
                # dacha is busy, just wait
                return
        # otherwise its likely a transient failure, so keep trying

    async def poll_with_interval(self):
        if not self._cancel:
            await self._get_updates()
            if not self._cancel and self._interval > 0:
                # call  again in [interval] seconds
                self._thread = threading.Timer(self._interval, self.poll_with_interval)

    # async polls, you can choose not to wait for updates
    # if the interval is zero, this will just issue a get updates and stop
    async def poll(self):
        self._cancel = None
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
        for feature_apikey in data:
            if feature_apikey:
                self._repository.notify("FEATURES", feature_apikey['features'])
