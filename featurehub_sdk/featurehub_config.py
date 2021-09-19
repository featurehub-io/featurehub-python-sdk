from __future__ import annotations
from featurehub_sdk.client_context import ClientContext, ClientEvalFeatureContext, ServerEvalFeatureContext
from featurehub_sdk.edge_service import EdgeService
from featurehub_sdk.featurehub_client import FeatureHubClient
from featurehub_sdk.featurehub_repository import FeatureHubRepository


class FeatureHubConfig:
    # readyness: Readyness;

    _api_keys = []
    _edge_url: str
    _client_eval: bool
    _repository: FeatureHubRepository

    def __init__(self, edge_url, *api_key):
        self._edge_service = None
        self._repository = FeatureHubRepository()
        self._edge_url = edge_url

        if not edge_url or not api_key:
            raise TypeError('api_key and edge_url must not be null')

        if any("*" in key for key in api_key):
            if not all("*" in key for key in api_key):
                raise TypeError('all api keys provided must be of the same type - all keys client or all keys eval')

        for key in api_key:
            self._api_keys.append(key)

        self._client_eval = '*' in self._api_keys[0]

        if not self._edge_url[-1] == '/':
            self._edge_url += '/'

    def client_evaluated(self) -> bool:
        return self._client_eval  # is this correct?

    def get_api_keys(self) -> list[str]:
        return self._api_keys.copy()

    def get_host(self) -> str:
        return self._edge_url

    def repository(self) -> FeatureHubRepository:
        if not self._repository:
            self._repository = FeatureHubRepository()
        return self._repository

    def init(self) -> FeatureHubConfig:
        # ensure the repository exists
        self.repository()

        # ensure the edge service provider exists
        self._create_edge_service(self.edge_service_provider(), self.repository)

        return self

    def _create_edge_service(self, edge_service, repository) -> EdgeService:
        pass

    def _get_or_create_edge_service(self, edge_service, repository) -> EdgeService:
        pass

    def edge_service_provider(self) -> EdgeService:
        if self._edge_service is None:
            self._edge_service = FeatureHubClient(self._edge_url, self._api_keys, self._repository)
        return self._edge_service

    def new_context(self) -> ClientContext:
        repository = self.repository()
        edge_service = self.edge_service_provider()

        return ClientEvalFeatureContext(repository, self._get_or_create_edge_service(edge_service, repository)) \
            if self._client_eval else \
            ServerEvalFeatureContext(repository, self._create_edge_service(edge_service, repository))

    def close(self):
        pass