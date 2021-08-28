from edge_service import EdgeService
from featurehub_repository import FeatureHubRepository


class ClientContext:
    """holds client context"""

    def __init__(self, repo: FeatureHubRepository, edge: EdgeService):
        """"""
        pass


class ClientEvalFeatureContext(ClientContext):
    pass


class ServerEvalFeatureContext(ClientContext):
    pass
