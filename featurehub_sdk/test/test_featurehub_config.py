import asyncio
import unittest
from unittest.mock import MagicMock

from featurehub_sdk.client_context import ServerEvalFeatureContext, ClientEvalFeatureContext, InternalFeatureRepository
from featurehub_sdk.edge_service import EdgeService
import os
from unittest.mock import patch

from featurehub_sdk.featurehub_config import FeatureHubConfig
from featurehub_sdk.polling_edge_service import PollingEdgeService
from featurehub_sdk.streaming_edge_service import StreamingEdgeClient

# we need this so we can do async testing (Stack Overflow)
def sync(coro):
    def wrapper(*args, **kwargs):
        asyncio.run(coro(*args, **kwargs))
    return wrapper

# monkey patch MagicMock to support async (Stack Overflow)
async def async_magic():
    pass

MagicMock.__await__ = lambda x: async_magic().__await__()


class FeatureHubConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_edge = MagicMock(spec=EdgeService)
        self.mock_repo = MagicMock(spec=InternalFeatureRepository)

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
        self.assertEqual(cfg.get_or_create_edge_service(), self.mock_edge)

    def test_config_edge_service(self):
        cfg = FeatureHubConfig("http://localhost/", ['abc*123', '123*abc', 'xyz*abc'],
                               self.mock_repo)

        self.assertTrue(isinstance(cfg.get_or_create_edge_service(), EdgeService))

    def test_config_closes_previous_edge_service(self):
        edge = MagicMock()
        self.mock_edge.return_value = edge
        cfg = FeatureHubConfig('http://localhost', ['123'], self.mock_repo, self.mock_edge)
        cfg.get_or_create_edge_service()
        new_edge_provider = MagicMock()
        cfg.edge_service_provider(new_edge_provider)
        self.mock_edge.assert_called()
        edge.close.assert_called()
    def test_client_evaluated_key_streams_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = FeatureHubConfig("http://localhost/", ['ling*kwong'], self.mock_repo, headers={'X-Chago': 'orm'})
            edge = cfg.get_or_create_edge_service()
        self.assertIsInstance(edge, StreamingEdgeClient)
        self.assertEqual(edge._streaming_thread._headers, {'X-Chago': 'orm'})

    def test_server_evaluated_key_has_no_default_mode(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = FeatureHubConfig("http://localhost/", ['kornaphat'], self.mock_repo)
            with self.assertRaises(ValueError):
                cfg.get_or_create_edge_service()
            with self.assertRaises(ValueError):
                cfg.new_context()

    def test_server_evaluated_key_polls_when_chosen(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = FeatureHubConfig("http://localhost/", ['kornaphat'], self.mock_repo, headers={'X-Chago': 'ling'})
            cfg.use_polling_edge_service()
            edge = cfg.get_or_create_edge_service()
        self.assertIsInstance(edge, PollingEdgeService)
        self.assertEqual(edge.interval, 30)
        self.assertEqual(edge._headers, {'X-Chago': 'ling'})

    def test_server_evaluated_key_polls_when_the_env_interval_is_set(self):
        with patch.dict(os.environ, {'FEATUREHUB_POLLING_INTERVAL': '45s'}, clear=True):
            cfg = FeatureHubConfig("http://localhost/", ['kornaphat'], self.mock_repo, headers={'X-Chago': 'ling'})
            edge = cfg.get_or_create_edge_service()
        self.assertIsInstance(edge, PollingEdgeService)
        self.assertEqual(edge.interval, 45)
        self.assertEqual(edge._headers, {'X-Chago': 'ling'})

    def test_reading_features_refreshes_the_edge_service(self):
        for keys in (['ling*kwong'], ['kornaphat']):
            cfg = FeatureHubConfig("http://localhost/", keys, self.mock_repo, lambda rep, k, url: self.mock_edge)
            cfg.new_context().feature('always_wonder')
        self.assertEqual(self.mock_edge.refresh_if_stale.call_count, 2)

    def test_client_evaluated_key_polls_when_the_env_interval_is_set(self):
        with patch.dict(os.environ, {'FEATUREHUB_POLLING_INTERVAL': '1m'}, clear=True):
            cfg = FeatureHubConfig("http://localhost/", ['ling*kwong'], self.mock_repo, headers={'X-Chago': 'orm'})
            edge = cfg.get_or_create_edge_service()
        self.assertIsInstance(edge, PollingEdgeService)
        self.assertEqual(edge.interval, 60)
        self.assertEqual(edge._headers, {'X-Chago': 'orm'})

    def test_an_empty_env_interval_is_not_set(self):
        with patch.dict(os.environ, {'FEATUREHUB_POLLING_INTERVAL': ' '}, clear=True):
            edge = FeatureHubConfig("http://localhost/", ['ling*kwong'], self.mock_repo).get_or_create_edge_service()
        self.assertIsInstance(edge, StreamingEdgeClient)

    def test_an_invalid_env_interval_is_an_error(self):
        for value in ('soon', '2', '-1'):
            with patch.dict(os.environ, {'FEATUREHUB_POLLING_INTERVAL': value}, clear=True):
                with self.assertRaises(ValueError, msg=value):
                    FeatureHubConfig("http://localhost/", ['ling*kwong'], self.mock_repo).get_or_create_edge_service()

    def test_an_explicit_choice_wins_over_the_env_interval(self):
        with patch.dict(os.environ, {'FEATUREHUB_POLLING_INTERVAL': '60s'}, clear=True):
            cfg = FeatureHubConfig("http://localhost/", ['ling*kwong'], self.mock_repo)
            cfg.use_polling_edge_service(15)
            self.assertEqual(cfg.get_or_create_edge_service().interval, 15)
            cfg = FeatureHubConfig("http://localhost/", ['ling*kwong'], self.mock_repo,
                                   edge_provider=lambda repo, keys, url: StreamingEdgeClient(url, keys, repo))
            self.assertIsInstance(cfg.get_or_create_edge_service(), StreamingEdgeClient)

    def test_polling_passive_chooses_passive_polling(self):
        for keys in (['ling*kwong'], ['kornaphat']):
            with patch.dict(os.environ, {'FEATUREHUB_POLLING_PASSIVE': 'true', 'FEATUREHUB_POLLING_INTERVAL': '45s'},
                            clear=True):
                edge = FeatureHubConfig("http://localhost/", keys, self.mock_repo,
                                        headers={'X-Chago': 'orm'}).get_or_create_edge_service()
            self.assertIsInstance(edge, PollingEdgeService, keys)
            self.assertTrue(edge.passive, keys)
            self.assertEqual(edge.interval, 45)
            self.assertEqual(edge._headers, {'X-Chago': 'orm'})

    def test_polling_passive_without_an_interval_fetches_once(self):
        with patch.dict(os.environ, {'FEATUREHUB_POLLING_PASSIVE': 'yes'}, clear=True):
            edge = FeatureHubConfig("http://localhost/", ['kornaphat'], self.mock_repo).get_or_create_edge_service()
        self.assertTrue(edge.passive)
        self.assertEqual(edge.interval, 0)

    def test_an_empty_polling_passive_is_not_set(self):
        with patch.dict(os.environ, {'FEATUREHUB_POLLING_PASSIVE': '', 'FEATUREHUB_POLLING_INTERVAL': '45s'}, clear=True):
            edge = FeatureHubConfig("http://localhost/", ['ling*kwong'], self.mock_repo).get_or_create_edge_service()
        self.assertFalse(edge.passive)

    def test_use_polling_can_be_passive(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = FeatureHubConfig("http://localhost/", ['kornaphat'], self.mock_repo)
            cfg.use_polling_edge_service(60, passive=True)
            edge = cfg.get_or_create_edge_service()
        self.assertTrue(edge.passive)
        self.assertEqual(edge.interval, 60)

    def test_polling_interval_takes_go_durations_with_a_unit(self):
        for value, seconds in (('30s', 30), ('1m', 60), ('1m30s', 90), ('7500ms', 7.5), ('5.5s', 5.5), ('0', 0),
                               ('0s', 0), (' 1h ', 3600)):
            with patch.dict(os.environ, {'FEATUREHUB_POLLING_INTERVAL': value}, clear=True):
                edge = FeatureHubConfig("http://localhost/", ['ling*kwong'], self.mock_repo).get_or_create_edge_service()
            self.assertEqual(edge.interval, seconds, value)
        for value in ('30', '5.5', '3s', '1m-', 'ten', '-30s', '30x'):  # a unit is required, and at least 5s
            with patch.dict(os.environ, {'FEATUREHUB_POLLING_INTERVAL': value}, clear=True):
                with self.assertRaises(ValueError, msg=value):
                    FeatureHubConfig("http://localhost/", ['ling*kwong'], self.mock_repo).get_or_create_edge_service()

    def test_the_1x_poll_interval_name_still_works_but_is_deprecated(self):
        with patch.dict(os.environ, {'FEATUREHUB_POLL_INTERVAL': '45'}, clear=True):
            with self.assertLogs('featurehub_sdk', level='WARNING') as logs:
                edge = FeatureHubConfig("http://localhost/", ['ling*kwong'], self.mock_repo).get_or_create_edge_service()
        self.assertEqual(edge.interval, 45)
        self.assertIn('FEATUREHUB_POLL_INTERVAL is deprecated', logs.output[0])
        with patch.dict(os.environ, {'FEATUREHUB_POLL_INTERVAL': '45', 'FEATUREHUB_POLLING_INTERVAL': '60s'}, clear=True):
            edge = FeatureHubConfig("http://localhost/", ['ling*kwong'], self.mock_repo).get_or_create_edge_service()
        self.assertEqual(edge.interval, 60)

    def test_use_polling_validates_the_interval_at_once(self):
        cfg = FeatureHubConfig("http://localhost/", ['ling*kwong'], self.mock_repo)
        for interval in (-1, 4):
            with self.assertRaises(ValueError):
                cfg.use_polling_edge_service(interval)
        with patch.dict(os.environ, {'FEATUREHUB_POLLING_INTERVAL': '2'}, clear=True):
            with self.assertRaises(ValueError):
                cfg.use_polling_edge_service()

    def test_use_polling_passes_headers(self):
        cfg = FeatureHubConfig("http://localhost/", ['ling*kwong'], self.mock_repo, headers={'X-Chago': 'orm'})
        cfg.use_polling_edge_service(0)
        edge = cfg.get_or_create_edge_service()
        self.assertIsInstance(edge, PollingEdgeService)
        self.assertEqual(edge._headers, {'X-Chago': 'orm'})


if __name__ == '__main__':
    unittest.main()
