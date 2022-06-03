import asyncio
import unittest
from unittest.mock import MagicMock

from featurehub_sdk.client_context import ServerEvalFeatureContext, ClientEvalFeatureContext
from featurehub_sdk.edge_service import EdgeService
from featurehub_sdk.featurehub_config import FeatureHubConfig

# we need this so we can do async testing (Stack Overflow)
def sync(coro):
    def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(coro(*args, **kwargs))
    return wrapper

# monkey patch MagicMock to support async (Stack Overflow)
async def async_magic():
    pass

MagicMock.__await__ = lambda x: async_magic().__await__()


class FeatureHubConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_edge = MagicMock()
        self.mock_repo = MagicMock()

    def test_api_keys_must_be_consistent_type(self):
        self.assertRaises(TypeError,
            lambda: FeatureHubConfig("http://localhost/", ['abc*123', '123', 'xyz']))

    def test_edge_url_must_be_set(self):
        self.assertRaises(TypeError,
                          lambda: FeatureHubConfig(None, ['abc', '123', 'xyz']))

    def test_config_detects_client_eval(self):
        self.assertEqual(FeatureHubConfig("http://localhost/", ['abc*123']).client_evaluated(), True)

    def test_config_detects_server_eval(self):
        self.assertEqual(FeatureHubConfig("http://localhost/", ['abc123']).client_evaluated(), False)

    def test_edge_url_always_ends_with_slash(self):
        self.assertEqual(FeatureHubConfig("http://localhost", ['abc123']).get_host(), 'http://localhost/')

    def test_api_keys_are_preserved(self):
        self.assertEqual(FeatureHubConfig("http://localhost/", ['abc', '123', 'xyz']).get_api_keys(), ['abc', '123', 'xyz'])

    def test_we_can_replace_the_repository(self):
        cfg = FeatureHubConfig("http://localhost/", ['abc', '123', 'xyz'])
        repo = cfg.repository()
        cfg.repository(repository=self.mock_repo)
        self.assertNotEqual(cfg.repository(), repo)

    @sync
    async def test_init_fh_client_success(self):
        cfg = FeatureHubConfig("http://localhost/", ['abc', '123', 'xyz'],
                               self.mock_repo, lambda rep, keys, edge_provider: self.mock_edge)

        self.assertEqual(cfg.get_or_create_edge_service(), self.mock_edge)

        await cfg.init()
        cfg.close()

        self.mock_edge.poll.assert_called_once_with()
        self.mock_edge.close.assert_called_once_with()

        # mock_repo.notify.assert_called_with('FEATURES', data)

    def test_config_hands_over_server_context(self):
        cfg = FeatureHubConfig("http://localhost/", ['abc', '123', 'xyz'],
                               self.mock_repo, lambda rep, keys, edge_url: self.mock_edge)

        ctx = cfg.new_context()
        self.assertEqual(isinstance(ctx, ServerEvalFeatureContext), True)
        self.assertEqual(isinstance(ctx, ClientEvalFeatureContext), False)

    def test_config_hands_over_client_context(self):
        cfg = FeatureHubConfig("http://localhost/", ['abc*123', '123*abc', 'xyz*abc'],
                               self.mock_repo, lambda rep, keys, edge_url: self.mock_edge)

        ctx = cfg.new_context()
        self.assertEqual(isinstance(ctx, ServerEvalFeatureContext), False)
        self.assertEqual(isinstance(ctx, ClientEvalFeatureContext), True)

    def test_replace_edge_provider_and_request(self):
        cfg = FeatureHubConfig("http://localhost/", ['abc*123', '123*abc', 'xyz*abc'],
                               self.mock_repo)
        cfg.edge_service_provider(lambda rep, keys, edge_url: self.mock_edge)
        self.assertEquals(cfg.get_or_create_edge_service(), self.mock_edge)

    def test_config_edge_service(self):
        cfg = FeatureHubConfig("http://localhost/", ['abc*123', '123*abc', 'xyz*abc'],
                               self.mock_repo)

        self.assertTrue(isinstance(cfg.get_or_create_edge_service(), EdgeService))


if __name__ == '__main__':
    unittest.main()
