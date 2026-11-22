from __future__ import annotations  # so we can reference ourselves

import typing
import os
import logging
from urllib.parse import urlsplit, urlunsplit

from featurehub_sdk.client_context import ClientContext, ClientEvalFeatureContext, ServerEvalFeatureContext, \
    InternalFeatureRepository
from featurehub_sdk.edge_service import EdgeService, parse_duration
from featurehub_sdk.featurehub_repository import FeatureHubRepository
from typing import Dict, List, Callable, Optional
from featurehub_sdk.polling_edge_service import PollingEdgeService, validate_poll_interval
from featurehub_sdk.streaming_edge_service import StreamingEdgeClient

log = logging.getLogger('featurehub_sdk')

EDGE_URL_ENV = "FEATUREHUB_EDGE_URL"
CLIENT_API_KEY_ENV = "FEATUREHUB_CLIENT_API_KEY"
SERVER_API_KEY_ENV = "FEATUREHUB_SERVER_API_KEY"
CONNECT_TYPE_ENV = "FEATUREHUB_CONNECT_TYPE"
CONNECT_INTERVAL_ENV = "FEATUREHUB_CONNECT_INTERVAL"
# the 1.x polling interval, a number of seconds with no unit. read only by use_polling_edge_service(), as 1.x did, and
# only when neither FEATUREHUB_CONNECT_TYPE nor FEATUREHUB_CONNECT_INTERVAL is set
LEGACY_POLL_INTERVAL_ENV = "FEATUREHUB_POLL_INTERVAL"

_CONNECT_TYPES = ('active', 'passive', 'streaming')


# an environment variable, trimmed, or None if it is absent or empty (featurehub-protocol.yaml
# providers.environment_variables.set)
def _env(name: str) -> Optional[str]:
    value = (os.environ.get(name) or '').strip()
    return value or None


# FEATUREHUB_CONNECT_TYPE, lowercased, or None if not set. raises ValueError for anything but active, passive or streaming
def _env_connect_type() -> Optional[str]:
    value = _env(CONNECT_TYPE_ENV)
    if value is None:
        return None
    if value.lower() not in _CONNECT_TYPES:
        raise ValueError(f"{CONNECT_TYPE_ENV} must be active, passive or streaming, not {value!r}")
    return value.lower()


# FEATUREHUB_CONNECT_INTERVAL in seconds, or None if not set. it is 0 (connect once and stop) or at least 5 seconds, with
# a unit (30s, 5000ms, 1.5m, 1h); raises ValueError otherwise
def _env_connect_interval() -> Optional[float]:
    value = _env(CONNECT_INTERVAL_ENV)
    if value is None:
        return None
    try:
        seconds = parse_duration(value)
    except ValueError:
        raise ValueError(f"{CONNECT_INTERVAL_ENV} must be a number and a unit (ms, s, m or h), such as 30s or 1m, "
                         f"or 0, not {value!r}")
    seconds = int(seconds) if seconds.is_integer() else seconds
    try:
        validate_poll_interval(seconds)
    except ValueError as e:
        raise ValueError(f"{CONNECT_INTERVAL_ENV}={value!r}: {e}")
    return seconds


# the 1.x FEATUREHUB_POLL_INTERVAL in seconds, if set and neither FEATUREHUB_CONNECT_TYPE nor
# FEATUREHUB_CONNECT_INTERVAL is (then it isn't consulted at all), else None
def _env_legacy_poll_interval() -> Optional[float]:
    value = _env(LEGACY_POLL_INTERVAL_ENV)
    if value is None or _env(CONNECT_TYPE_ENV) is not None or _env(CONNECT_INTERVAL_ENV) is not None:
        return None
    log.warning("%s is deprecated, use %s instead (with a unit, e.g. %ss)", LEGACY_POLL_INTERVAL_ENV,
                CONNECT_INTERVAL_ENV, value)
    try:
        seconds = int(value)
    except ValueError:
        raise ValueError(f"{LEGACY_POLL_INTERVAL_ENV} must be a whole number of seconds, not {value!r}")
    validate_poll_interval(seconds)
    return seconds


# the validation error for polling without an interval, naming FEATUREHUB_POLL_INTERVAL if it was set but ignored
def _no_interval_error(what: str) -> ValueError:
    message = f"{what} needs a polling interval: pass one, or set {CONNECT_INTERVAL_ENV} (such as 30s, or 0 to poll once)"
    if _env(LEGACY_POLL_INTERVAL_ENV) is not None:
        message += f". {LEGACY_POLL_INTERVAL_ENV} is ignored, as {CONNECT_TYPE_ENV} or {CONNECT_INTERVAL_ENV} is set"
    return ValueError(message)


class FeatureHubConfig:
    _api_keys: List[str]
    _edge_url: str
    _client_eval: bool
    _repository: InternalFeatureRepository
    _edge_service: typing.Optional[EdgeService]
    _edge_service_provider: Callable[[InternalFeatureRepository, List[str], str], EdgeService]
    _headers: Dict[str, str]

    # headers are extra headers the built-in edge services send with every request to FeatureHub (e.g. for an API
    # gateway or a proxy in front of it). the SDK's own headers win over any of the same name.
    # edge_url defaults to FEATUREHUB_EDGE_URL, and api_keys to FEATUREHUB_CLIENT_API_KEY or else
    # FEATUREHUB_SERVER_API_KEY: what is given here always wins
    def __init__(self, edge_url: Optional[str] = None, api_keys: Optional[List[str]] = None,
                 repository: typing.Optional[InternalFeatureRepository] = None,
                 edge_provider: typing.Optional[Callable[[InternalFeatureRepository, List[str], str], EdgeService]] = None,
                 headers: Optional[Dict[str, str]] = None):
        self._edge_service = None
        self._headers = dict(headers) if headers else {}
        self._repository = repository if repository is not None else FeatureHubRepository()
        if not edge_url:
            edge_url = _env(EDGE_URL_ENV)
        if not api_keys:
            env_key = _env(CLIENT_API_KEY_ENV) or _env(SERVER_API_KEY_ENV)
            api_keys = [env_key] if env_key else None

        if not edge_url or not api_keys:
            raise TypeError(f'api_keys and edge_url must be given, or set in {EDGE_URL_ENV} and {CLIENT_API_KEY_ENV} '
                            f'or {SERVER_API_KEY_ENV}')
        self._edge_url = edge_url
        self._api_keys = list(api_keys)

        if any("*" in key for key in api_keys):
            if not all("*" in key for key in api_keys):
                raise TypeError('all api keys provided must be of the same type - all keys client or all keys eval')

        self._client_eval = '*' in self._api_keys[0]

        # the path ends with a slash, so features can be added to it (a query string in the host is kept after it)
        parts = urlsplit(self._edge_url)
        if not parts.path.endswith('/'):
            self._edge_url = urlunsplit(parts._replace(path=parts.path + '/'))

        # this is the function we use to create our edge service if no other is specified
        self._edge_service_provider = edge_provider if edge_provider else self._create_default_provider
        self._edge_service = None

    def client_evaluated(self) -> bool:
        return self._client_eval  # is this correct?

    def get_api_keys(self) -> List[str]:
        return self._api_keys.copy()

    def get_host(self) -> str:
        return self._edge_url

    def repository(self, repository: typing.Optional[FeatureHubRepository] = None) -> InternalFeatureRepository:
        if repository:
            self._repository = repository

        return self._repository

    async def init(self) -> FeatureHubConfig:
        log.info("Init request made")
        # ensure the repository exists
        self.repository()

        # ensure the edge service provider exists
        await self.get_or_create_edge_service().poll()

        return self

    # uses the defined provider to make us an edge instance
    def _create_edge_service(self) -> EdgeService:
        # call to get the edge service method and then call that method with the parameters
        # we don't store this result as Server Evaluated clients need new
        return self.edge_service_provider()(self._repository, self._api_keys, self._edge_url)

    # checks to see if we already have an edge service, and if we don't, ask the provider to create
    # one for us
    def get_or_create_edge_service(self) -> EdgeService:
        if self._edge_service is None:
            self._edge_service = self._create_edge_service()
        return self._edge_service

    # this returns a function pointer that we call to get the actual edge service instance
    # it allows people to replace the way we create the edge service with a method of their own, e.g. with
    # a different provider or a customised provider creation
    def edge_service_provider(self,
                              edge_provider:
                              typing.Optional[Callable[[InternalFeatureRepository, List[str], str], EdgeService]] = None) \
            -> Callable[[InternalFeatureRepository, List[str], str], EdgeService]:
        # did the give us a new one? if not, return the default one we created on init
        if edge_provider is None:
            return self._edge_service_provider

        self._edge_service_provider = edge_provider

        # they have changed the provider, so make sure its closed and
        if self._edge_service:
            self._edge_service.close()
            self._edge_service = None

        return self._edge_service_provider

    # this is just an internal function that creates the default edge service if the user hasn't provided one (which
    # will be 90% of the time), chosen from the environment (featurehub-protocol.yaml
    # providers.environment_variables.mode_selection):
    # - FEATUREHUB_CONNECT_TYPE=active or passive: polling at FEATUREHUB_CONNECT_INTERVAL, which must be set
    # - FEATUREHUB_CONNECT_TYPE=streaming: streaming (FEATUREHUB_CONNECT_INTERVAL isn't used)
    # - only FEATUREHUB_CONNECT_INTERVAL set: active polling at that interval
    # - neither: a client evaluated key streams. a server evaluated key has no default: this SDK doesn't send the
    #   context over streaming, so it must poll, chosen with use_polling_edge_service() or the variables above
    def _create_default_provider(self, repository: InternalFeatureRepository, api_keys: List[str],
                                 edge_url: str) -> EdgeService:
        connect_type = _env_connect_type()
        if connect_type is None and _env(CONNECT_INTERVAL_ENV) is not None:
            connect_type = 'active'

        if connect_type in ('active', 'passive'):
            interval = _env_connect_interval()
            if interval is None:
                raise _no_interval_error(f"{CONNECT_TYPE_ENV}={connect_type}")
            return PollingEdgeService(edge_url, api_keys, repository, interval, self._headers,
                                      passive=connect_type == 'passive')

        if connect_type == 'streaming' and _env(CONNECT_INTERVAL_ENV) is not None:
            log.warning("%s is not used when streaming (%s=streaming)", CONNECT_INTERVAL_ENV, CONNECT_TYPE_ENV)

        if self._client_eval:
            return StreamingEdgeClient(edge_url, api_keys, repository, self._headers)

        if connect_type == 'streaming':
            raise ValueError(f"{CONNECT_TYPE_ENV}=streaming needs a client evaluated API key (containing '*'): this "
                             "SDK can't stream a server evaluated key, so it must poll")
        raise ValueError("a server evaluated API key must poll: call use_polling_edge_service(), or set "
                         f"{CONNECT_TYPE_ENV} (active or passive) and {CONNECT_INTERVAL_ENV}")

    # interval is in seconds: 0 polls once, otherwise it must be at least 5. if it isn't given it comes from
    # FEATUREHUB_CONNECT_INTERVAL (or the deprecated FEATUREHUB_POLL_INTERVAL, if neither FEATUREHUB_CONNECT_TYPE nor
    # FEATUREHUB_CONNECT_INTERVAL is set); with none of them it is an error, as there is no default interval.
    # passive polls only when features are read and are older than the interval, rather than on a timer
    def use_polling_edge_service(self, interval: Optional[float] = None, passive: bool = False):
        if interval is None:
            interval = _env_connect_interval()
        if interval is None:
            interval = _env_legacy_poll_interval()
        if interval is None:
            raise _no_interval_error("use_polling_edge_service()")
        validate_poll_interval(interval)
        headers = self._headers
        self.edge_service_provider(lambda repository, api_keys,
                                          edge_url: PollingEdgeService(edge_url, api_keys, repository, interval,
                                                                       headers, passive=passive))

    def new_context(self) -> ClientContext:
        repository = self.repository()
        edge_service = self.get_or_create_edge_service()

        return ClientEvalFeatureContext(repository, edge_service) \
            if self._client_eval else \
            ServerEvalFeatureContext(repository, edge_service)

    def close(self):
        if self._edge_service is not None:
            self._edge_service.close()
            self._edge_service = None
