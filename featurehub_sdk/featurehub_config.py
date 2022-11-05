from __future__ import annotations  # so we can reference ourselves

import typing
import os
import logging

from featurehub_sdk.client_context import ClientContext, ClientEvalFeatureContext, ServerEvalFeatureContext, \
    InternalFeatureRepository
from featurehub_sdk.edge_service import EdgeService
from featurehub_sdk.featurehub_repository import FeatureHubRepository
from typing import List, Callable
from featurehub_sdk.polling_edge_service import PollingEdgeService
from featurehub_sdk.streaming_edge_service import StreamingEdgeClient

log = logging.getLogger('featurehub_sdk')

class FeatureHubConfig:
    _api_keys: List[str]
    _edge_url: str
    _client_eval: bool
    _repository: InternalFeatureRepository
    _edge_service: typing.Optional[EdgeService]
    _edge_service_provider: Callable[[InternalFeatureRepository, List[str], str], EdgeService]

    def __init__(self, edge_url, api_keys: List[str],
                 repository: typing.Optional[InternalFeatureRepository] = None,
                 edge_provider: typing.Optional[Callable[[InternalFeatureRepository, List[str], str], EdgeService]] = None):
        self._edge_service = None
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
    def _create_default_provider(self, repository: InternalFeatureRepository, api_keys: List[str],
                                 edge_url: str) -> EdgeService:

        return StreamingEdgeClient(edge_url, api_keys, repository)

    def use_polling_edge_service(self, interval: int = int(os.environ.get("FEATUREHUB_POLL_INTERVAL", "30"))):
        self.edge_service_provider(lambda repository, api_keys,
                                          edge_url: PollingEdgeService(edge_url, api_keys, repository, interval))

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
