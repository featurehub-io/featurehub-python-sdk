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
            cfg.use_polling_edge_service(30)
            edge = cfg.get_or_create_edge_service()
        self.assertIsInstance(edge, PollingEdgeService)
        self.assertEqual(edge.interval, 30)
        self.assertEqual(edge._request._headers, {'X-Chago': 'ling'})

    def test_reading_features_refreshes_the_edge_service(self):
        for keys in (['ling*kwong'], ['kornaphat']):
            cfg = FeatureHubConfig("http://localhost/", keys, self.mock_repo, lambda rep, k, url: self.mock_edge)
            cfg.new_context().feature('always_wonder')
        self.assertEqual(self.mock_edge.refresh_if_stale.call_count, 2)

    def test_use_polling_can_be_passive(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = FeatureHubConfig("http://localhost/", ['kornaphat'], self.mock_repo)
            cfg.use_polling_edge_service(60, passive=True)
            edge = cfg.get_or_create_edge_service()
        self.assertTrue(edge.passive)
        self.assertEqual(edge.interval, 60)

    def test_use_polling_validates_the_interval_at_once(self):
        cfg = FeatureHubConfig("http://localhost/", ['ling*kwong'], self.mock_repo)
        for interval in (-1, 4):
            with self.assertRaises(ValueError):
                cfg.use_polling_edge_service(interval)
        with patch.dict(os.environ, {'FEATUREHUB_CONNECT_INTERVAL': '2s'}, clear=True):
            with self.assertRaises(ValueError):
                cfg.use_polling_edge_service()


def _default_edge(env, keys=('ling*kwong',)):
    with patch.dict(os.environ, env, clear=True):
        return FeatureHubConfig("http://localhost/", list(keys), MagicMock(spec=InternalFeatureRepository),
                                headers={'X-Chago': 'orm'}).get_or_create_edge_service()


# featurehub-protocol.yaml conformance environment-mode-selection, environment-connect-interval,
# environment-legacy-names and environment-names
class EnvironmentModeSelectionTest(unittest.TestCase):
    def test_active_and_passive_poll_at_the_connect_interval(self):
        for keys in (['ling*kwong'], ['kornaphat']):
            for connect_type, passive in (('active', False), ('passive', True), ('ACTIVE', False), (' passive ', True)):
                edge = _default_edge({'FEATUREHUB_CONNECT_TYPE': connect_type,
                                      'FEATUREHUB_CONNECT_INTERVAL': '45s'}, keys)
                self.assertIsInstance(edge, PollingEdgeService, connect_type)
                self.assertEqual(edge.passive, passive, connect_type)
                self.assertEqual(edge.interval, 45)
                self.assertEqual(edge._request._headers, {'X-Chago': 'orm'})

    def test_active_or_passive_without_an_interval_is_an_error(self):
        for connect_type in ('active', 'passive'):
            with self.assertRaises(ValueError, msg=connect_type):
                _default_edge({'FEATUREHUB_CONNECT_TYPE': connect_type})

    def test_the_ignored_legacy_interval_is_named_in_the_error(self):
        with self.assertRaises(ValueError) as e:
            _default_edge({'FEATUREHUB_CONNECT_TYPE': 'passive', 'FEATUREHUB_POLL_INTERVAL': '45'})
        self.assertIn('FEATUREHUB_POLL_INTERVAL is ignored', str(e.exception))

    def test_streaming_ignores_the_interval(self):
        with self.assertLogs('featurehub_sdk', level='WARNING') as logs:
            edge = _default_edge({'FEATUREHUB_CONNECT_TYPE': 'Streaming', 'FEATUREHUB_CONNECT_INTERVAL': '45s'})
        self.assertIsInstance(edge, StreamingEdgeClient)
        self.assertIn('FEATUREHUB_CONNECT_INTERVAL is not used', logs.output[0])

    def test_streaming_a_server_evaluated_key_is_an_error(self):
        with self.assertRaises(ValueError):
            _default_edge({'FEATUREHUB_CONNECT_TYPE': 'streaming'}, ['kornaphat'])

    def test_any_other_connect_type_is_an_error(self):
        for value in ('polling', 'sse', 'actively'):
            with self.assertRaises(ValueError, msg=value):
                _default_edge({'FEATUREHUB_CONNECT_TYPE': value, 'FEATUREHUB_CONNECT_INTERVAL': '45s'})

    def test_the_interval_alone_is_active_polling(self):
        for keys in (['ling*kwong'], ['kornaphat']):
            edge = _default_edge({'FEATUREHUB_CONNECT_INTERVAL': '1m'}, keys)
            self.assertIsInstance(edge, PollingEdgeService)
            self.assertFalse(edge.passive)
            self.assertEqual(edge.interval, 60)

    def test_neither_streams_a_client_key_and_is_an_error_for_a_server_key(self):
        self.assertIsInstance(_default_edge({}), StreamingEdgeClient)
        with self.assertRaises(ValueError):
            _default_edge({}, ['kornaphat'])

    def test_empty_variables_are_not_set(self):
        self.assertIsInstance(_default_edge({'FEATUREHUB_CONNECT_TYPE': ' ', 'FEATUREHUB_CONNECT_INTERVAL': ''}),
                              StreamingEdgeClient)

    def test_a_mode_in_code_wins(self):
        env = {'FEATUREHUB_CONNECT_TYPE': 'streaming', 'FEATUREHUB_CONNECT_INTERVAL': '60s'}
        with patch.dict(os.environ, env, clear=True):
            cfg = FeatureHubConfig("http://localhost/", ['ling*kwong'], MagicMock())
            cfg.use_polling_edge_service(passive=True)  # the interval still comes from FEATUREHUB_CONNECT_INTERVAL
            edge = cfg.get_or_create_edge_service()
            self.assertTrue(edge.passive)
            self.assertEqual(edge.interval, 60)
            cfg.use_polling_edge_service(15)  # an interval in code wins too
            self.assertEqual(cfg.get_or_create_edge_service().interval, 15)
        with patch.dict(os.environ, {'FEATUREHUB_CONNECT_TYPE': 'active'}, clear=True):
            cfg = FeatureHubConfig("http://localhost/", ['ling*kwong'], MagicMock(),
                                   edge_provider=lambda repo, keys, url: StreamingEdgeClient(url, keys, repo))
            self.assertIsInstance(cfg.get_or_create_edge_service(), StreamingEdgeClient)

    def test_use_polling_without_an_interval_is_an_error(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = FeatureHubConfig("http://localhost/", ['kornaphat'], MagicMock())
            with self.assertRaises(ValueError):
                cfg.use_polling_edge_service()
            with self.assertRaises(ValueError):
                cfg.use_polling_edge_service(passive=True)

    def test_connect_interval_values(self):
        for value, seconds in (('0', 0), ('0s', 0), ('5s', 5), ('30s', 30), ('5000ms', 5), ('1.5m', 90),
                               ('1h', 3600), (' 30s ', 30)):
            self.assertEqual(_default_edge({'FEATUREHUB_CONNECT_INTERVAL': value}).interval, seconds, value)
        for value in ('30', '3s', '500ms', '1m30s', '-30s', '30 s', 'ten', '30S', '.5s'):
            with self.assertRaises(ValueError, msg=value):
                _default_edge({'FEATUREHUB_CONNECT_INTERVAL': value})

    def test_the_1x_poll_interval_is_read_by_use_polling_only_when_no_new_name_is_set(self):
        with patch.dict(os.environ, {'FEATUREHUB_POLL_INTERVAL': '45'}, clear=True):
            cfg = FeatureHubConfig("http://localhost/", ['kornaphat'], MagicMock())
            with self.assertLogs('featurehub_sdk', level='WARNING') as logs:
                cfg.use_polling_edge_service()
            self.assertEqual(cfg.get_or_create_edge_service().interval, 45)
            self.assertIn('FEATUREHUB_POLL_INTERVAL is deprecated', logs.output[0])
        with patch.dict(os.environ, {'FEATUREHUB_POLL_INTERVAL': '45', 'FEATUREHUB_CONNECT_INTERVAL': '60s'},
                        clear=True):
            cfg = FeatureHubConfig("http://localhost/", ['kornaphat'], MagicMock())
            cfg.use_polling_edge_service()
            self.assertEqual(cfg.get_or_create_edge_service().interval, 60)
        with patch.dict(os.environ, {'FEATUREHUB_POLL_INTERVAL': '45', 'FEATUREHUB_CONNECT_TYPE': 'passive'},
                        clear=True):
            cfg = FeatureHubConfig("http://localhost/", ['kornaphat'], MagicMock())
            with self.assertRaises(ValueError):
                cfg.use_polling_edge_service()
        # 1.x didn't use it to choose the mode, so nor does this
        with patch.dict(os.environ, {'FEATUREHUB_POLL_INTERVAL': '45'}, clear=True):
            with self.assertRaises(ValueError):
                FeatureHubConfig("http://localhost/", ['kornaphat'], MagicMock()).get_or_create_edge_service()

    def test_the_unreleased_polling_names_are_not_read(self):
        edge = _default_edge({'FEATUREHUB_POLLING_INTERVAL': '45s', 'FEATUREHUB_POLLING_PASSIVE': 'true'})
        self.assertIsInstance(edge, StreamingEdgeClient)


class EnvironmentConnectionTest(unittest.TestCase):
    def test_edge_url_and_keys_come_from_the_environment(self):
        with patch.dict(os.environ, {'FEATUREHUB_EDGE_URL': 'http://chago:8085', 'FEATUREHUB_CLIENT_API_KEY': 'ling*kwong',
                                     'FEATUREHUB_SERVER_API_KEY': 'kornaphat'}, clear=True):
            cfg = FeatureHubConfig()
        self.assertEqual(cfg.get_host(), 'http://chago:8085/')
        self.assertEqual(cfg.get_api_keys(), ['ling*kwong'])
        self.assertTrue(cfg.client_evaluated())

    def test_the_server_key_is_used_without_a_client_key(self):
        with patch.dict(os.environ, {'FEATUREHUB_EDGE_URL': 'http://chago', 'FEATUREHUB_CLIENT_API_KEY': ' ',
                                     'FEATUREHUB_SERVER_API_KEY': ' kornaphat '}, clear=True):
            cfg = FeatureHubConfig()
        self.assertEqual(cfg.get_api_keys(), ['kornaphat'])
        self.assertFalse(cfg.client_evaluated())

    def test_code_wins_setting_by_setting(self):
        with patch.dict(os.environ, {'FEATUREHUB_EDGE_URL': 'http://chago', 'FEATUREHUB_CLIENT_API_KEY': 'ling*kwong'},
                        clear=True):
            cfg = FeatureHubConfig("http://omu", None)
            self.assertEqual(cfg.get_host(), 'http://omu/')
            self.assertEqual(cfg.get_api_keys(), ['ling*kwong'])
            cfg = FeatureHubConfig(api_keys=['kornaphat'])
            self.assertEqual(cfg.get_host(), 'http://chago/')
            self.assertEqual(cfg.get_api_keys(), ['kornaphat'])

    def test_nothing_given_or_set_is_an_error(self):
        with patch.dict(os.environ, {'FEATUREHUB_EDGE_URL': 'http://chago'}, clear=True):
            self.assertRaises(TypeError, FeatureHubConfig)
        with patch.dict(os.environ, {'FEATUREHUB_CLIENT_API_KEY': 'ling*kwong'}, clear=True):
            self.assertRaises(TypeError, FeatureHubConfig)

    def test_a_host_with_a_query_string_keeps_it_after_the_path(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(FeatureHubConfig("http://chago/edge?shop=omu", ['kornaphat']).get_host(),
                             'http://chago/edge/?shop=omu')


class FeatureHubConfigUsePollingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_repo = MagicMock(spec=InternalFeatureRepository)

    def test_use_polling_passes_headers(self):
        cfg = FeatureHubConfig("http://localhost/", ['ling*kwong'], self.mock_repo, headers={'X-Chago': 'orm'})
        cfg.use_polling_edge_service(0)
        edge = cfg.get_or_create_edge_service()
        self.assertIsInstance(edge, PollingEdgeService)
        self.assertEqual(edge._request._headers, {'X-Chago': 'orm'})


if __name__ == '__main__':
    unittest.main()
