import unittest
from unittest import TestCase
from unittest.mock import MagicMock

from featurehub_sdk.client_context import ClientContext

class ClientContextTest(TestCase):

    def setUp(self) -> None:
        self.mock_repo = MagicMock()
        self.mock_feature = MagicMock()

    def test_get_number(self):
        self.mock_repo.feature.return_value = self.mock_feature
        client_context = ClientContext(self.mock_repo)

        client_context.get_number('angel')
        self.mock_repo.feature.assert_called_with('angel')
        self.mock_feature.get_number.assert_called_once_with()
        self.mock_feature.get_boolean.assert_not_called()

    # def test_get_number_when_not_number(self):
    #     var = FeatureStateHolder('FEATURE_TITLE_TO_UPPERCASE', {'id': '123', 'key': 'FEATURE_TITLE_TO_UPPERCASE',
    #                                   'l': True, 'version': 1, 'type': 'BOOLEAN', 'value': 'true', 'strategies': []}, )
    #
    #     self.mock_repo.feature.return_value = var
    #     client_context = ClientContext(self.mock_repo)
    #     result = client_context.get_number("bla")
    #     self.assertEqual(result, None)
    #
    # def test_get_number_when_feature_is_none(self):
    #     var = FeatureStateHolder('FEATURE_TITLE_TO_UPPERCASE')
    #     self.mock_repo.feature.return_value = var
    #     client_context = ClientContext(self.mock_repo)
    #     result = client_context.get_number("bla")
    #     self.assertEqual(result, None)


if __name__ == '__main__':
    unittest.main()
