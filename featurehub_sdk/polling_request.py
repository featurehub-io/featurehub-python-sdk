import json
import logging
import re
import threading
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from typing import Callable, Dict, List, Optional

import urllib3

from featurehub_sdk.edge_service import PROTOCOL_SDK_VERSION, _edge_url, _env_seconds, _request_headers
from featurehub_sdk.featurehub_repository import FeatureHubRepository
from featurehub_sdk.version import sdk_version

log = logging.getLogger('featurehub_sdk')

_MAX_AGE = re.compile(r'max-age=(\d+)')


class FetchOutcome(Enum):
    FEATURES = 'features'  # features were received and given to the repository
    STALE = 'stale'  # features were received, and the environment is stale (236): nothing more should be requested
    REJECTED = 'rejected'  # the key or environment was rejected (any 4xx): nothing more should be requested
    UNCHANGED = 'unchanged'  # 304, the features held are current
    FAILED = 'failed'  # a temporary failure (network, 5xx, a bad body): the next poll tries again
    DISCARDED = 'discarded'  # the response arrived after it was no longer wanted, so nothing was applied


@dataclass
class FetchResult:
    outcome: FetchOutcome
    # a Cache-Control max-age from a response with features, in seconds
    max_age: Optional[int] = None
    status: Optional[int] = None


# one GET of the features from FeatureHub Edge (featurehub-protocol.yaml featurehub_edge.polling): the URL, the
# headers, the ETag and the context it belongs to, and what the response means. it gives features to the repository,
# but has no threads or schedule of its own: PollingEdgeService decides when to fetch and what an outcome does to
# polling. its context and ETag may be changed from another thread while a fetch is in flight
class PollingRequest:
    # how long (in seconds) a request to the server may take before it is abandoned, overridden by
    # FEATUREHUB_POLLING_REQ_TIMEOUT
    TIMEOUT = 12.0

    def __init__(self, edge_url: str, api_keys: List[str], repository: FeatureHubRepository,
                 headers: Optional[Dict[str, str]] = None):
        self._edge_url = edge_url
        self._api_keys = list(api_keys)
        self._repository = repository
        self._headers = dict(headers) if headers else {}
        self._lock = threading.Lock()
        self._context: Optional[str] = None
        self._sha_context: Optional[str] = None
        self._etag: Optional[str] = None
        self._timeout = _env_seconds('FEATUREHUB_POLLING_REQ_TIMEOUT', self.TIMEOUT)
        self._http = urllib3.PoolManager()

    # apiKey (each, in order), contextSha, sdk_version: featurehub-protocol.yaml featurehub_edge.query_parameters
    def url(self, sha_context: str = "0") -> str:
        return _edge_url(self._edge_url, 'features',
                         [('apiKey', key) for key in self._api_keys] +
                         [('contextSha', sha_context), ('sdk_version', PROTOCOL_SDK_VERSION)])

    # sets the x-featurehub header sent from now on, returning whether it changed. the ETag belongs to the old context
    # (a 304 for it would leave the old context's features), so a change clears it
    def change_context(self, header: Optional[str]) -> bool:
        with self._lock:
            if self._context == header:
                return False
            self._context = header
            self._sha_context = sha256(header.encode('utf-8')).hexdigest() if header else None
            self._etag = None
            return True

    # fetches the features once. wanted() is asked once the response arrives: if it says no (polling was closed while
    # the request was in flight), nothing is applied
    def fetch(self, wanted: Callable[[], bool]) -> FetchResult:
        with self._lock:
            context = self._context
            sha_context = "0" if self._sha_context is None else self._sha_context
            etag = self._etag
        url = self.url(sha_context)

        log.debug("polling %s", url)
        sdk_headers = {
            'X-SDK': 'Python',
            'X-SDK-Version': sdk_version
        }
        if etag:
            sdk_headers['if-none-match'] = etag
        if context:
            sdk_headers['x-featurehub'] = context
        headers = _request_headers(self._headers, sdk_headers)

        try:
            resp = self._http.request(method='GET', url=url, headers=headers, timeout=self._timeout)
            log.debug("polling status %s", resp.status)

            if not wanted():
                return FetchResult(FetchOutcome.DISCARDED, status=resp.status)

            if resp.status == 200 or resp.status == 236:
                self._apply_features(json.loads(resp.data.decode('utf-8')))

                # only keep the etag once the body has been processed, otherwise a bad body would be followed by
                # 304s for that etag and the features would never be fetched again. it belongs to the context it was
                # fetched for, so it isn't kept if the context changed while the request was in flight
                if 'etag' in resp.headers:
                    with self._lock:
                        if self._context == context:
                            self._etag = resp.headers['etag']

                max_age = None
                if 'cache-control' in resp.headers:
                    found = _MAX_AGE.findall(resp.headers['cache-control'])
                    if found:
                        max_age = int(found[0])

                return FetchResult(FetchOutcome.STALE if resp.status == 236 else FetchOutcome.FEATURES,
                                   max_age=max_age, status=resp.status)
        except (ValueError, urllib3.exceptions.HTTPError) as err:
            # HTTPError is the base of all urllib3 errors, including failing to connect at all. ValueError covers
            # a body that isn't valid JSON/UTF-8. Either way it is transient, so the next poll tries again
            log.error("failed to poll featurehub: %s", err)
            return FetchResult(FetchOutcome.FAILED)
        except Exception:
            # anything else (unexpected response shape, a failing repository listener) must not stop polling either
            log.exception("failed to process featurehub poll")
            return FetchResult(FetchOutcome.FAILED)

        if 400 <= resp.status < 500:  # the key or environment is rejected (any 4xx, 429 included)
            return FetchResult(FetchOutcome.REJECTED, status=resp.status)
        if resp.status == 304:
            log.debug("featurehub features unchanged")
            return FetchResult(FetchOutcome.UNCHANGED, status=resp.status)
        if resp.status != 503:  # a 503 is dacha being busy, so just wait. anything else is likely transient too
            log.error("featurehub returned unexpected status %s", resp.status)
        return FetchResult(FetchOutcome.FAILED, status=resp.status)

    # we get returned an environment for each API key. together their features are one full set, so they are given to
    # the repository at once - one environment at a time would remove the features of the others
    def _apply_features(self, data):
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
