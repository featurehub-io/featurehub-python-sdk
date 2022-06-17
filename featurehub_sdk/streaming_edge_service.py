from typing import Optional
from typing import List

import sseclient
import urllib3
import json
import threading
import logging
import sys

from featurehub_sdk.client_context import InternalFeatureRepository
from featurehub_sdk.edge_service import EdgeService
from featurehub_sdk.version import sdk_version

log = logging.getLogger(sys.modules[__name__].__name__)


class _StreamingThread(threading.Thread):
    _cancel: bool
    _http: urllib3.PoolManager
    _client: Optional[sseclient.SSEClient] = None
    _repository: InternalFeatureRepository
    _url: str

    def __init__(self, edge_url: str, api_keys: List[str],
                 repository: InternalFeatureRepository):
        super().__init__(daemon=True, name="streaming-featurehub")
        self._url = f"{edge_url}/features/{api_keys[0]}"
        self._repository = repository
        self._cancel = False
        self._http = urllib3.PoolManager()

    def run(self):
        headers = {'Accept': 'text/event-stream', 'X-SDK': 'Python', 'X-SDK-Version': sdk_version}
        # headers = {'Accept': 'text/event-stream'}
        last_event_id = None
        while not self._cancel:
            try:
                log.log(5, "featurehub starting request: %s", self._url)
                if last_event_id is not None:
                    headers['Last-Event-Id'] = last_event_id
                resp = self._http.request('GET', self._url, preload_content=False, headers=headers)
                if resp.status == 200:
                    self._client = sseclient.SSEClient(resp)
                    for event in self._client.events():
                        last_event_id = event.id
                        log.log(5, "received data %s: %s", event.event, event.data)
                        self._repository.notify(event.event, self._check_data(event.data))
                        if self._cancel:
                            self._client.close()
                elif resp.status == 404:
                    self._cancel = True
            except (ValueError, urllib3.exceptions.ProtocolError):
                pass

    def _check_data(self, data):
        if data and (data.startswith('{') or data.startswith('[')):
            return json.loads(data)

        return data

    def cancel(self):
        self._cancel = True

    def close(self):
        self._cancel = True
        if self._client:
            self._client.close()


class StreamingEdgeClient(EdgeService):
    _client_evaluated: bool
    _streaming_thread: _StreamingThread

    def __init__(self, edge_url: str, api_keys: List[str],
                 repository: InternalFeatureRepository):
        self._streaming_thread = _StreamingThread(edge_url, api_keys, repository)

        self._client_evaluated = '*' in api_keys[0]

    async def poll(self):
        if self._streaming_thread.is_alive():
            return

        self._streaming_thread.start()

    def close(self):
        if self._streaming_thread.is_alive():
            self._streaming_thread.close()

    def client_evaluated(self):
        return self._client_evaluated

    # not supported
    async def context_change(self, header: str):
        pass