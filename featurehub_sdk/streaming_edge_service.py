from typing import Optional
from typing import List

import sseclient
import urllib3
import json
import threading
import logging
import sys

from featurehub_sdk.client_context import InternalFeatureRepository
from featurehub_sdk.edge_service import EdgeService, _env_seconds
from featurehub_sdk.version import sdk_version

log = logging.getLogger('featurehub_sdk')


class _StreamingThread(threading.Thread):
    _cancel: bool
    _http: urllib3.PoolManager
    _client: Optional[sseclient.SSEClient] = None
    _repository: InternalFeatureRepository
    _stopped: bool
    _invalid_key: bool
    _url: str
    _wakeup: threading.Event
    _initial_retry_delay: float
    _max_retry_delay: float
    _timeout: urllib3.Timeout

    # delay (in seconds) before reconnecting after a failure, doubling on each consecutive failure up to the max.
    # overridden by FEATUREHUB_STREAMING_INITIAL_RETRY_DELAY and FEATUREHUB_STREAMING_MAX_RETRY_DELAY
    INITIAL_RETRY_DELAY = 1.0
    MAX_RETRY_DELAY = 30.0
    # how long (in seconds) to wait to connect, and for the next data on an open stream, before reconnecting - so a
    # dropped or half-open connection doesn't block forever. overridden by FEATUREHUB_STREAMING_CONNECT_TIMEOUT and
    # FEATUREHUB_STREAMING_READ_TIMEOUT. the read timeout must be longer than the server keeps a quiet stream open
    CONNECT_TIMEOUT = 12.0
    READ_TIMEOUT = 60.0

    def __init__(self, edge_url: str, api_keys: List[str],
                 repository: InternalFeatureRepository):
        super().__init__(daemon=True, name="streaming-featurehub")
        self._url = f"{edge_url}features/{api_keys[0]}"
        self._repository = repository
        self._cancel = False
        self._stopped = False
        self._invalid_key = False
        self._wakeup = threading.Event()
        self._initial_retry_delay = _env_seconds('FEATUREHUB_STREAMING_INITIAL_RETRY_DELAY', self.INITIAL_RETRY_DELAY)
        self._max_retry_delay = max(_env_seconds('FEATUREHUB_STREAMING_MAX_RETRY_DELAY', self.MAX_RETRY_DELAY),
                                    self._initial_retry_delay)
        self._timeout = urllib3.Timeout(connect=_env_seconds('FEATUREHUB_STREAMING_CONNECT_TIMEOUT', self.CONNECT_TIMEOUT),
                                        read=_env_seconds('FEATUREHUB_STREAMING_READ_TIMEOUT', self.READ_TIMEOUT))
        self._http = urllib3.PoolManager()

    def run(self):
        headers = {'Accept': 'text/event-stream', 'X-SDK': 'Python', 'X-SDK-Version': sdk_version}
        # headers = {'Accept': 'text/event-stream'}
        last_event_id = None
        retry_delay = self._initial_retry_delay
        while not self._cancel and not self._stopped:
            resp = None
            try:
                log.debug("featurehub starting request: %s", self._url)
                if last_event_id:
                    headers['Last-Event-Id'] = last_event_id
                else:
                    headers.pop('Last-Event-Id', None)
                resp = self._http.request('GET', self._url, preload_content=False, headers=headers,
                                          timeout=self._timeout)
                if self._cancel:  # closed while connecting, before there was a client for close() to close
                    break
                if resp.status == 200:
                    self._client = sseclient.SSEClient(resp)
                    for event in self._client.events():
                        if self._cancel or self._stopped:  # no events once closed, while a new stream may be starting
                            break
                        # only a stream that delivers the features counts as recovered - a server or proxy that
                        # accepts and immediately drops the connection, or sends anything else, keeps backing off
                        if event.event == 'features':
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
                            else:
                                self._repository.notify(event.event, self._check_data(event.data))
                        except Exception:
                            # a bad event or a failing repository listener shouldn't drop the stream
                            log.exception("failed to process featurehub %s event", event.event)

                        if self._cancel or self._stopped:
                            break
                    log.debug("featurehub stream ended")
                elif resp.status == 404:
                    log.error("key provided for featurehub is invalid")
                    self._invalid_key = True
                    self._cancel = True
                    self._repository.notify("failed", None)
                else:
                    log.error("featurehub returned unexpected status %s", resp.status)
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

            if self._cancel or self._stopped:
                break

            # always wait before reconnecting so an unreachable server isn't hammered, waking early if cancelled
            log.debug("featurehub reconnecting in %ss", retry_delay)
            self._wakeup.wait(retry_delay)
            retry_delay = min(retry_delay * 2, self._max_retry_delay)

    def _process_config(self, data):
        payload = json.loads(data)
        if payload.get('edge.stale') is not None:
            log.warning("environment is stale, stopped requesting updates")
            self._stopped = True

    def _check_data(self, data):
        if data and (data.startswith('{') or data.startswith('[')):
            return json.loads(data)

        return data

    @property
    def stopped(self):
        return self._stopped

    @property
    def invalid_key(self):
        return self._invalid_key

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

    def __init__(self, edge_url: str, api_keys: List[str],
                 repository: InternalFeatureRepository):
        self._edge_url = edge_url
        self._api_keys = api_keys
        self._repository = repository
        self._streaming_thread = _StreamingThread(edge_url, api_keys, repository)

        self._client_evaluated = '*' in api_keys[0]

    async def poll(self):
        thread = self._streaming_thread
        # streaming stopped by an invalid key (404) or a stale environment stays stopped
        if thread.stopped or thread.invalid_key:
            return
        if thread.is_alive() and not thread.cancelled:
            return

        # a closed thread may still be shutting down, and a thread can only be started once, so use a new one
        if thread.ident is not None:
            thread = self._streaming_thread = _StreamingThread(self._edge_url, self._api_keys, self._repository)
        thread.start()

    def close(self):
        if self._streaming_thread.is_alive():
            self._streaming_thread.close()

    def client_evaluated(self):
        return self._client_evaluated

    @property
    def stopped(self):
        return self._streaming_thread.stopped

    # not supported
    async def context_change(self, header: str):
        pass