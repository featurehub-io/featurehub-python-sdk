

import unittest
from unittest import TestCase
from unittest.mock import MagicMock

from featurehub_sdk.client_context import Applied
from featurehub_sdk.fh_state_base_holder import FeatureStateHolder
from featurehub_sdk.interceptors import InterceptorValue


class FeatureStateHolderTest(TestCase):

    def setUp(self) -> None:
        self._repo = MagicMock()
        self._repo.find_interceptor.return_value = None


    def feature(self, feature_type, val) -> dict:
        result = {
            'id': '1',
            'version': 1,
            'l': False,
            'type': feature_type
        }

        if val is not None:
            result['value'] = val

        return result

    def test_empty(self):
        key = 'E'
        fh = FeatureStateHolder(key, self._repo)
        self.assertEquals(fh.get_version, -1)
        self.assertIsNone(fh.id)
        self.assertFalse(fh.locked)
        self.assertFalse(fh.is_set)

    def test_basic_boolean(self):
        key = 'F'
        f = self.feature('BOOLEAN', False)
        fh = FeatureStateHolder(key, self._repo, f)
        self.assertEquals(fh.get_version, 1)
        self.assertEquals(fh.id, '1')
        self.assertFalse(fh.locked)
        self.assertTrue(fh.is_set)

        self.assertFalse(fh.get_boolean)
        self.assertFalse(fh.get_flag)
        self.assertFalse(fh.is_enabled)
        f['value'] = True
        self.assertTrue(fh.get_boolean)
        self.assertTrue(fh.get_flag)
        self.assertTrue(fh.is_enabled)

        self.assertIsNone(fh.get_raw_json)
        self.assertIsNone(fh.get_number)
        self.assertIsNone(fh.get_string)

    def test_basic_number(self):
        key = 'N'
        f = self.feature('NUMBER', 24.6)
        fh = FeatureStateHolder(key, self._repo, f)
        self.assertEquals(fh.get_version, 1)
        self.assertEquals(fh.id, '1')
        self.assertFalse(fh.locked)
        self.assertTrue(fh.is_set)

        self.assertIsNone(fh.get_raw_json)
        self.assertIsNone(fh.get_boolean)
        self.assertIsNone(fh.get_flag)
        self.assertIsNone(fh.get_string)

        self.assertEquals(fh.get_number, 24.6)

    def test_basic_string(self):
        key = 'S'
        f = self.feature('STRING', 'hoolah')
        fh = FeatureStateHolder(key, self._repo, f)
        self.assertEquals(fh.get_version, 1)
        self.assertEquals(fh.id, '1')
        self.assertFalse(fh.locked)
        self.assertTrue(fh.is_set)

        f['l'] = True
        self.assertTrue(fh.locked)

        self.assertIsNone(fh.get_raw_json)
        self.assertIsNone(fh.get_boolean)
        self.assertIsNone(fh.get_flag)
        self.assertIsNone(fh.get_number)
        self.assertEquals(fh.get_string, 'hoolah')

    def test_basic_json(self):
        key = 'S'
        f = self.feature('JSON', 'hoolah')
        fh = FeatureStateHolder(key, self._repo, f)
        self.assertEquals(fh.get_version, 1)
        self.assertEquals(fh.id, '1')
        self.assertFalse(fh.locked)
        self.assertTrue(fh.is_set)

        self.assertIsNone(fh.get_string)
        self.assertIsNone(fh.get_boolean)
        self.assertIsNone(fh.get_flag)
        self.assertIsNone(fh.get_number)
        self.assertEquals(fh.get_raw_json, 'hoolah')

        self._repo.find_interceptor.assert_called()

    def test_interceptor_not_called_if_locked(self):
        key = 'L'
        f = self.feature('BOOLEAN', False)
        fh = FeatureStateHolder(key, self._repo, f)
        f['l'] = True
        self.assertTrue(fh.locked)
        self.assertFalse(fh.get_flag)
        self._repo.find_interceptor.assert_not_called()

    def test_ensure_interceptor_value_used(self):
        key = 'L'
        f = self.feature('BOOLEAN', False)
        fh = FeatureStateHolder(key, self._repo, f)
        self.assertFalse(fh.get_flag)
        self._repo.find_interceptor.return_value = InterceptorValue('true')
        self.assertTrue(fh.get_flag)

    def test_context_evaluation_triggered(self):
        key = 'L'
        f = self.feature('BOOLEAN', False)
        ctx = MagicMock()
        fh = FeatureStateHolder(key, self._repo, f)
        self.assertFalse(fh.get_flag)
        fh_ctx = fh.with_context(ctx)
        self._repo.apply.return_value = Applied(True, "true")
        self.assertFalse(fh.get_flag)
        self.assertTrue(fh_ctx.get_flag)
        self._repo.apply.assert_called_once()

        self.assertFalse(fh.get_value)
        self.assertTrue(fh_ctx.get_value)

        self.assertEquals(fh.key, key)

if __name__ == '__main__':
    unittest.main()