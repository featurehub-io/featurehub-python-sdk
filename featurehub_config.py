from __future__ import annotations

from client_context import ClientContext, ClientEvalFeatureContext, ServerEvalFeatureContext
from edge_service import EdgeService
from featurehub_repository import FeatureHubRepository


class FeatureHubConfig:
    # readyness: Readyness;

    _api_keys = []
    _api_key: str
    _edge_url: str
    _client_eval: bool

    def __init__(self, edge_url, api_key):
        self._repository = FeatureHubRepository
        self._edge_url = edge_url
        self._api_key = api_key

        if not edge_url or not api_key:
            raise TypeError('api_key and edge_url must not be null')

        self._api_keys = [api_key]

        self._client_eval = '*' in self._api_key

        if not self._edge_url[-1] == '/':
            self._edge_url += '/'

    def api_key(self, api_key: str) -> FeatureHubConfig:
        self._api_keys.append(api_key)
        return self

    def client_evaluated(self) -> bool:
        return self._client_eval  # is this correct?

    def get_api_keys(self) -> list[str]:
        api_keys = self._api_keys
        return api_keys

    def get_host(self) -> str:
        return self._edge_url

    def repository(self) -> FeatureHubRepository:
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

