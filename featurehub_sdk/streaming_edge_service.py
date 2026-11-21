from typing import Dict, Optional
from typing import List

import sseclient
import urllib3
import json
import threading
import logging
import sys

from featurehub_sdk.client_context import InternalFeatureRepository
from featurehub_sdk.edge_service import EdgeService, _env_number, _env_seconds, _request_headers
from featurehub_sdk.version import sdk_version

log = logging.getLogger('featurehub_sdk')

# no wait before reconnecting is shorter than this, whatever is configured, so there is never a tight reconnect loop
_MIN_RECONNECT_DELAY = 0.1

# events that show the stream works, so the reconnect delay goes back to the initial one
_CONNECTION_WORKS_EVENTS = ('ack', 'features', 'feature', 'delete_feature', 'deleteFeature', 'config')


class _StreamingThread(threading.Thread):
    _cancel: bool
    _http: urllib3.PoolManager
    _client: Optional[sseclient.SSEClient] = None
    _repository: InternalFeatureRepository
    _stopped: bool
    _failed: bool
    _url: str
    _wakeup: threading.Event
    _initial_retry_delay: float
    _max_retry_delay: float
    _backoff_multiplier: float
    _timeout: urllib3.Timeout
    _headers: Dict[str, str]

    # delay (in seconds) before reconnecting after a failure, multiplied on each consecutive failure up to the max.
    # overridden by FEATUREHUB_SSE_INITIAL_RETRY_DELAY, FEATUREHUB_SSE_BACKOFF_MULTIPLIER and
    # FEATUREHUB_SSE_MAX_RETRY_DELAY
    INITIAL_RETRY_DELAY = 1.0
    BACKOFF_MULTIPLIER = 2.0
    MAX_RETRY_DELAY = 30.0
    # how long (in seconds) to wait to connect, and for the next data on an open stream, before reconnecting - so a
    # dropped or half-open connection doesn't block forever. overridden by FEATUREHUB_SSE_CONNECT_TIMEOUT and
    # FEATUREHUB_SSE_READ_TIMEOUT. the read timeout must be longer than the server keeps a quiet stream open
    CONNECT_TIMEOUT = 12.0
    READ_TIMEOUT = 60.0

    def __init__(self, edge_url: str, api_keys: List[str],
                 repository: InternalFeatureRepository,
                 headers: Optional[Dict[str, str]] = None):
        super().__init__(daemon=True, name="streaming-featurehub")
        self._url = f"{edge_url}features/{api_keys[0]}"
        self._repository = repository
        self._headers = dict(headers) if headers else {}
        self._cancel = False
        self._stopped = False
        self._failed = False
        self._wakeup = threading.Event()
        self._initial_retry_delay = max(_env_seconds('FEATUREHUB_SSE_INITIAL_RETRY_DELAY',
                                                     self.INITIAL_RETRY_DELAY), _MIN_RECONNECT_DELAY)
        self._max_retry_delay = max(_env_seconds('FEATUREHUB_SSE_MAX_RETRY_DELAY', self.MAX_RETRY_DELAY),
                                    self._initial_retry_delay)
        self._backoff_multiplier = _env_number('FEATUREHUB_SSE_BACKOFF_MULTIPLIER', self.BACKOFF_MULTIPLIER)
        if self._backoff_multiplier < 1:  # it must back off, so the delay never shrinks
            log.warning("ignoring FEATUREHUB_SSE_BACKOFF_MULTIPLIER below 1, using %s", self.BACKOFF_MULTIPLIER)
            self._backoff_multiplier = self.BACKOFF_MULTIPLIER
        self._timeout = urllib3.Timeout(connect=_env_seconds('FEATUREHUB_SSE_CONNECT_TIMEOUT', self.CONNECT_TIMEOUT),
                                        read=_env_seconds('FEATUREHUB_SSE_READ_TIMEOUT', self.READ_TIMEOUT))
        self._http = urllib3.PoolManager()

    def run(self):
        last_event_id = None
        retry_delay = self._initial_retry_delay
        while not self._cancel and not self._stopped and not self._failed:
            resp = None
            try:
                log.debug("featurehub starting request: %s", self._url)
                sdk_headers = {'Accept': 'text/event-stream', 'X-SDK': 'Python', 'X-SDK-Version': sdk_version}
                if last_event_id:
                    sdk_headers['Last-Event-Id'] = last_event_id
                headers = _request_headers(self._headers, sdk_headers)
                resp = self._http.request('GET', self._url, preload_content=False, headers=headers,
                                          timeout=self._timeout)
                if self._cancel:  # closed while connecting, before there was a client for close() to close
                    break
                if 400 <= resp.status < 500:
                    # the key or environment is rejected (any 4xx, 429 included), so stop for good
                    log.error("featurehub rejected the API key with status %s, stopped streaming", resp.status)
                    self._fail()
                elif resp.status != 200:
                    # a 5xx, or a 1xx or 3xx (not a valid response to an SSE request) is temporary
                    log.error("featurehub returned unexpected status %s", resp.status)
                elif not self._is_event_stream(resp):
                    # e.g. an HTML page from a gateway, proxy or captive portal: a failed connection, not a stream
                    log.error("featurehub returned %s rather than an event stream",
                              resp.headers.get('content-type') or 'no content type')
                else:
                    self._client = sseclient.SSEClient(resp)
                    if self._cancel:  # closed before there was a client for close() to close
                        break
                    for event in self._client.events():
                        if self._cancel or self._stopped or self._failed:  # no events once closed or stopped
                            break
                        # only a stream that delivers FeatureHub events counts as recovered - a server or proxy that
                        # accepts and immediately drops the connection, or only says bye, keeps backing off
                        if event.event in _CONNECTION_WORKS_EVENTS:
                            retry_delay = self._initial_retry_delay
                        # sseclient creates a fresh Event per message with id=None unless the message
                        # carries an id: field, but per the SSE spec the last event id persists until
                        # the server sends a new one (an empty id resets it)
                        if event.id is not None:
                            last_event_id = event.id
                        log.debug("received data %s: %s", event.event, event.data)

                        try:
                            if event.event == 'config':
                                self._process_config(event.data)
                            elif event.event == 'failure':
                                log.error("featurehub reported a failure, stopped streaming")
                                self._fail()
                            elif event.event not in ('ack', 'error'):
                                self._repository.notify(event.event, self._check_data(event.data))
                        except Exception:
                            # a bad event or a failing repository listener shouldn't drop the stream
                            log.exception("failed to process featurehub %s event", event.event)

                        if self._cancel or self._stopped or self._failed:
                            break
                    log.debug("featurehub stream ended")
            except (ValueError, urllib3.exceptions.HTTPError) as err:
                # HTTPError is the base of all urllib3 errors, including failing to connect at all
                if not self._cancel:  # close() interrupting the stream is expected
                    log.error("failed to communicate with featurehub: %s", err)
            except Exception:
                # anything else must not kill the thread, or updates would stop for good
                if not self._cancel:
                    log.exception("unexpected failure streaming from featurehub")
            finally:
                self._client = None  # so close() can't close a stream from an earlier connection
                # with preload_content=False the connection only goes back to the pool once released. it is closed
                # first, as a stream that was cancelled or failed may still have unread data on it
                if resp is not None:
                    resp.close()
                    resp.release_conn()

            if self._cancel or self._stopped or self._failed:
                break

            # the connection was lost and is being re-established: the features held are still the latest known
            try:
                self._repository.notify("bye", None)
            except Exception:
                log.exception("failed to notify featurehub repository of the lost connection")

            # always wait before reconnecting so an unreachable server isn't hammered, waking early if cancelled
            log.debug("featurehub reconnecting in %ss", retry_delay)
            self._wakeup.wait(retry_delay)
            retry_delay = min(retry_delay * self._backoff_multiplier, self._max_retry_delay)

    # a permanent failure: the repository is told, and nothing reconnects
    def _fail(self):
        self._failed = True
        self._repository.notify("failed", None)

    @staticmethod
    def _is_event_stream(resp) -> bool:
        content_type = resp.headers.get('content-type') or ''
        return content_type.split(';')[0].strip().lower() == 'text/event-stream'

    def _process_config(self, data):
        payload = json.loads(data)
        # the edge.stale key alone means stale, whatever its value
        if isinstance(payload, dict) and 'edge.stale' in payload:
            log.warning("environment is stale, stopped requesting updates")
            self._stopped = True
            self._repository.mark_environment_stale()

    def _check_data(self, data):
        if data and (data.startswith('{') or data.startswith('[')):
            return json.loads(data)

        return data

    @property
    def stopped(self):
        return self._stopped

    # stopped for good by a rejected key (any 4xx) or a failure event from FeatureHub
    @property
    def failed(self):
        return self._failed

    @property
    def invalid_key(self):
        return self._failed

    @property
    def cancelled(self):
        return self._cancel

    def cancel(self):
        self._cancel = True
        self._wakeup.set()

    def close(self):
        self._cancel = True
        self._wakeup.set()
        client = self._client  # read once, as the streaming thread clears it when a connection ends
        if client:
            client.close()


class StreamingEdgeClient(EdgeService):
    _client_evaluated: bool
    _streaming_thread: _StreamingThread
    _edge_url: str
    _api_keys: List[str]
    _repository: InternalFeatureRepository

    _headers: Optional[Dict[str, str]]

    # headers are extra headers sent with every connection and reconnection (e.g. for an API gateway); the SDK's own
    # headers win over any of the same name.
    # only client evaluated keys can stream: this SDK doesn't send the context over streaming, so FeatureHub would
    # evaluate a server evaluated key without it and give wrong values. use PollingEdgeService for those
    def __init__(self, edge_url: str, api_keys: List[str],
                 repository: InternalFeatureRepository,
                 headers: Optional[Dict[str, str]] = None):
        if '*' not in api_keys[0]:
            raise ValueError("streaming is only supported for client evaluated API keys (containing '*'), "
                             "use polling for a server evaluated key")
        self._edge_url = edge_url
        self._api_keys = api_keys
        self._repository = repository
        self._headers = headers
        self._streaming_thread = _StreamingThread(edge_url, api_keys, repository, headers)

        self._client_evaluated = True

    async def poll(self):
        thread = self._streaming_thread
        # streaming stopped by a rejected key (4xx), a failure or a stale environment stays stopped
        if thread.stopped or thread.failed:
            return
        if thread.is_alive() and not thread.cancelled:
            return

        # a closed thread may still be shutting down, and a thread can only be started once, so use a new one
        if thread.ident is not None:
            thread = self._streaming_thread = _StreamingThread(self._edge_url, self._api_keys, self._repository,
                                                               self._headers)
        thread.start()

    def close(self):
        if self._streaming_thread.is_alive():
            self._streaming_thread.close()

    def client_evaluated(self):
        return self._client_evaluated

    @property
    def stopped(self):
        return self._streaming_thread.stopped

    # not needed: only client evaluated keys stream, and they evaluate each context locally
    async def context_change(self, header: str):
        pass