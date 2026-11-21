from __future__ import annotations  # so we can reference ourselves

import typing
import os
import re
import logging

from featurehub_sdk.client_context import ClientContext, ClientEvalFeatureContext, ServerEvalFeatureContext, \
    InternalFeatureRepository
from featurehub_sdk.edge_service import EdgeService, parse_duration
from featurehub_sdk.featurehub_repository import FeatureHubRepository
from typing import Dict, List, Callable, Optional
from featurehub_sdk.polling_edge_service import PollingEdgeService, validate_poll_interval
from featurehub_sdk.streaming_edge_service import StreamingEdgeClient

log = logging.getLogger('featurehub_sdk')

DEFAULT_POLL_INTERVAL = 30

POLLING_INTERVAL_ENV = "FEATUREHUB_POLLING_INTERVAL"
POLLING_PASSIVE_ENV = "FEATUREHUB_POLLING_PASSIVE"
# the 1.x name for FEATUREHUB_POLLING_INTERVAL, still read if the new one isn't set
_DEPRECATED_POLL_INTERVAL_ENV = "FEATUREHUB_POLL_INTERVAL"


# the polling interval set in the environment (FEATUREHUB_POLLING_INTERVAL, or the 1.x FEATUREHUB_POLL_INTERVAL), in
# seconds, or None if neither is set. raises ValueError if it isn't a valid interval
def _env_poll_interval_if_set() -> Optional[float]:
    for name in (POLLING_INTERVAL_ENV, _DEPRECATED_POLL_INTERVAL_ENV):
        value = (os.environ.get(name) or '').strip()
        if value:
            if name == _DEPRECATED_POLL_INTERVAL_ENV:
                log.warning("%s is deprecated, use %s instead (with a unit, e.g. %ss)", _DEPRECATED_POLL_INTERVAL_ENV,
                            POLLING_INTERVAL_ENV, value)
                return _parse_poll_interval(name, value, seconds_without_unit=True)
            return _parse_poll_interval(name, value)
    return None


# the polling interval from the environment, or 30 seconds
def _env_poll_interval() -> float:
    interval = _env_poll_interval_if_set()
    return DEFAULT_POLL_INTERVAL if interval is None else interval


# seconds_without_unit: the 1.x FEATUREHUB_POLL_INTERVAL was a number of seconds, so it still is
def _parse_poll_interval(name: str, value: str, seconds_without_unit: bool = False) -> float:
    try:
        seconds = float(value) if seconds_without_unit and re.fullmatch(r'\s*\d+(\.\d+)?\s*', value) \
            else parse_duration(value)
    except ValueError:
        raise ValueError(f"{name} must be a duration with a unit, such as 30s or 1m, not {value!r}")
    seconds = int(seconds) if float(seconds).is_integer() else seconds
    try:
        validate_poll_interval(seconds)
    except ValueError as e:
        raise ValueError(f"{name}={value!r}: {e}")
    return seconds


class FeatureHubConfig:
    _api_keys: List[str]
    _edge_url: str
    _client_eval: bool
    _repository: InternalFeatureRepository
    _edge_service: typing.Optional[EdgeService]
    _edge_service_provider: Callable[[InternalFeatureRepository, List[str], str], EdgeService]
    _headers: Dict[str, str]

    # headers are extra headers the built-in edge services send with every request to FeatureHub (e.g. for an API
    # gateway or a proxy in front of it). the SDK's own headers win over any of the same name
    def __init__(self, edge_url, api_keys: List[str],
                 repository: typing.Optional[InternalFeatureRepository] = None,
                 edge_provider: typing.Optional[Callable[[InternalFeatureRepository, List[str], str], EdgeService]] = None,
                 headers: Optional[Dict[str, str]] = None):
        self._edge_service = None
        self._headers = dict(headers) if headers else {}
        self._repository = repository if repository is not None else FeatureHubRepository()
        self._edge_url = edge_url
        self._api_keys = api_keys

        if not edge_url or not api_keys:
            raise TypeError('api_key and edge_url must not be null')

        if any("*" in key for key in api_keys):
            if not all("*" in key for key in api_keys):
                raise TypeError('all api keys provided must be of the same type - all keys client or all keys eval')

        self._client_eval = '*' in self._api_keys[0]

        if not self._edge_url[-1] == '/':
            self._edge_url += '/'

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
    # will be 90% of the time)
    # chosen from the environment, as the Go SDK does, in this order:
    # - FEATUREHUB_POLLING_PASSIVE set (any value): passive polling, at FEATUREHUB_POLLING_INTERVAL if set, else 0
    #   (fetch once, at start)
    # - FEATUREHUB_POLLING_INTERVAL set: active polling at that interval
    # - otherwise a client evaluated key streams. a server evaluated key has no default: this SDK doesn't send the
    #   context over streaming, so it must poll, chosen with use_polling_edge_service() or the variables above
    def _create_default_provider(self, repository: InternalFeatureRepository, api_keys: List[str],
                                 edge_url: str) -> EdgeService:
        env_interval = _env_poll_interval_if_set()
        if (os.environ.get(POLLING_PASSIVE_ENV) or '').strip():
            interval = 0 if env_interval is None else env_interval
            return PollingEdgeService(edge_url, api_keys, repository, interval, self._headers, passive=True)

        if env_interval is not None:
            return PollingEdgeService(edge_url, api_keys, repository, env_interval, self._headers)

        if self._client_eval:
            return StreamingEdgeClient(edge_url, api_keys, repository, self._headers)

        raise ValueError("a server evaluated API key must poll: call use_polling_edge_service(), or set "
                         f"{POLLING_INTERVAL_ENV} or {POLLING_PASSIVE_ENV}")

    # interval is in seconds: 0 polls once, otherwise it must be at least 5. defaults to the environment variable
    # FEATUREHUB_POLLING_INTERVAL, or 30. passive polls only when features are read and are older than the interval,
    # rather than on a timer
    def use_polling_edge_service(self, interval: Optional[int] = None, passive: bool = False):
        if interval is None:
            interval = _env_poll_interval()
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
