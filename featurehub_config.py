from __future__ import annotations

from client_context import ClientContext, ClientEvalFeatureContext, ServerEvalFeatureContext
from edge_service import EdgeService
from featurehub_repository import FeatureHubRepository


class FeatureHubConfig:
    # readyness: Readyness;

    _api_keys = []
    _edge_url: str
    _client_eval: bool
    _repository: FeatureHubRepository

    def __init__(self, edge_url, *api_key):
        self._repository = FeatureHubRepository()
        self._edge_url = edge_url

        if not edge_url or not api_key:
            raise TypeError('api_key and edge_url must not be null')

        for key in api_key:
            self._api_keys.append(key)

        self._client_eval = '*' in self._api_keys[0]

        if not self._edge_url[-1] == '/':
            self._edge_url += '/'

    def client_evaluated(self) -> bool:
        return self._client_eval  # is this correct?

    def get_api_keys(self) -> list[str]:
        return self._api_keys

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
        self._create_edge_service(self.edge_service_provider())

        return self

    def _create_edge_service(self, edge_service, repository) -> EdgeService:
        pass

    def _get_or_create_edge_service(self, edge_service, repository) -> EdgeService:
        pass

    def edge_service_provider(self) -> EdgeService:
        pass

    def new_context(self) -> ClientContext:
        repository = self.repository()
        edge_service = self.edge_service_provider()

        return ClientEvalFeatureContext(repository, self._get_or_create_edge_service(edge_service, repository)) \
            if self._client_eval else \
            ServerEvalFeatureContext(repository, self._create_edge_service(edge_service, repository))

