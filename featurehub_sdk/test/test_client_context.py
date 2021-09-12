import unittest
from unittest import TestCase
from unittest.mock import patch

from featurehub_sdk.client_context import ClientContext
from featurehub_sdk.fh_state_base_holder import FeatureStateBaseHolder


class ClientContextTest(TestCase):

    @patch('featurehub_repository.FeatureHubRepository')
    @patch('edge_service.EdgeService')
    def test_get_number(self, mock_repo, edge_service):
        var = FeatureStateBaseHolder({'id': '123', 'key': 'FEATURE_TITLE_TO_UPPERCASE',
                                      'l': True, 'version': 1, 'type': 'NUMBER', 'value': 3, 'strategies': []}, )

        mock_repo.feature.return_value = var
        client_context = ClientContext(mock_repo, edge_service)
        result = client_context.get_number("bla")
        self.assertEqual(result, 3)

    @patch('featurehub_repository.FeatureHubRepository')
    @patch('edge_service.EdgeService')
    def test_get_number_when_not_number(self, mock_repo, mock_edge):
        var = FeatureStateBaseHolder({'id': '123', 'key': 'FEATURE_TITLE_TO_UPPERCASE',
                                      'l': True, 'version': 1, 'type': 'BOOLEAN', 'value': 'true', 'strategies': []}, )

        mock_repo.feature.return_value = var
        client_context = ClientContext(mock_repo, mock_edge)
        result = client_context.get_number("bla")
        self.assertEqual(result, None)

    @patch('featurehub_repository.FeatureHubRepository')
    @patch('edge_service.EdgeService')
    def test_get_number_when_feature_is_none(self, mock_repo, mock_edge):
        mock_repo.feature.return_value = None
        client_context = ClientContext(mock_repo, mock_edge)
        result = client_context.get_number("bla")
        self.assertEqual(result, None)


if __name__ == '__main__':
    unittest.main()
