import unittest

from featurehub_config import FeatureHubConfig


class FeatureHubConfigTest(unittest.TestCase):

    edge_url = 'http://localhost'
    client_eval_key = 'default/29517115-da60-4b64-99db-9da017561edd/7NZq23UuFEdmpcwxx7lkKSH0QH1EIS*dmGCHaOErbXyMLfzHCe0'
    server_eval_key = 'default/29517115-da60-4b64-99db-9da017561edd/a2eK0IJEeXdBrgiv3sLKaaxEZDy6uJ55F85RhIdK'
    another_client_key = 'default/29517115-da60-4b64-99db-9da017561edd/a2eK0IJEeXdBrgiv3sLKaaxEZDy6uJ55F85RhIdK*dmGCHaOErbXyMLfzHCe0'

    def test_featurehub_config_constructor(self):
        config = FeatureHubConfig(self.edge_url, self.client_eval_key)
        self.assertEqual(config._api_keys, ['default/29517115-da60-4b64-99db-9da017561edd/7NZq23UuFEdmpcwxx7lkKSH0QH1EIS*dmGCHaOErbXyMLfzHCe0'])
        self.assertEqual(config._client_eval, True)
        self.assertEqual(config._edge_url, 'http://localhost/')
        self.assertIsNotNone(config._repository)

    def test_featurehub_config_multi_api_keys(self):
        config = FeatureHubConfig(self.edge_url, self.client_eval_key, self.another_client_key)
        self.assertEqual(config._api_keys, ['default/29517115-da60-4b64-99db-9da017561edd/7NZq23UuFEdmpcwxx7lkKSH0QH1EIS*dmGCHaOErbXyMLfzHCe0',
                                            'default/29517115-da60-4b64-99db-9da017561edd/a2eK0IJEeXdBrgiv3sLKaaxEZDy6uJ55F85RhIdK*dmGCHaOErbXyMLfzHCe0'])

    def test_no_edge_url_provided(self):
        with self.assertRaises(TypeError):
            FeatureHubConfig("", self.client_eval_key)

    def test_no_key_provided(self):
        with self.assertRaises(TypeError):
            FeatureHubConfig("bla")
