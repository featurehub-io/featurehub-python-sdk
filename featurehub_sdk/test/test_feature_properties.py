import json
from unittest import TestCase

from unittest.mock import MagicMock

from featurehub_sdk.fh_state_base_holder import FeatureStateHolder

from featurehub_sdk.client_context import InternalFeatureRepository


class FeaturePropertiesTest(TestCase):
    repo: InternalFeatureRepository

    def setUp(self) -> None:
        self.repo = MagicMock()

    def test_feature_returns_empty_with_no_feature_state(self):
        fs = FeatureStateHolder('key', self.repo)

        self.assertEqual(fs.feature_properties, {})

    def test_feature_returns_empty_dict_with_no_value_in_feature_state(self):
        fs = FeatureStateHolder('key', self.repo)
        data = '''{
        "id": "227dc2e8-59e8-424a-b510-328ef52010f7",
        "key": "key",
        "l": true,
        "version": 28,
        "type": "STRING",
        "value": "orange"
        }'''
        json_data = json.loads(data)
        fs.set_feature_state(json_data)

        self.assertEqual(fs.feature_properties, {})

    def test_feature_returns_dict_when_properties_are_present(self):
        fs = FeatureStateHolder('key', self.repo)
        data = '''{
        "id": "227dc2e8-59e8-424a-b510-328ef52010f7",
        "key": "key",
        "l": true,
        "version": 28,
        "type": "STRING",
        "value": "orange",
        "fp": {"category": "shoes", "appName": "conga", "portfolio": "fish"}
        }'''
        json_data = json.loads(data)
        fs.set_feature_state(json_data)

        self.assertEqual(fs.feature_properties, {"category": "shoes", "appName": "conga", "portfolio": "fish"})
