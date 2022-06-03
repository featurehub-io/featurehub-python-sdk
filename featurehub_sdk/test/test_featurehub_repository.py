import unittest
from unittest.mock import MagicMock

from featurehub_sdk import featurehub_repository
from featurehub_sdk.fh_state_base_holder import FeatureStateHolder
from featurehub_sdk.interceptors import InterceptorValue


class FeatureHubRepositoryTest(unittest.TestCase):
    repo: featurehub_repository.FeatureHubRepository

    def setUp(self):
        self.repo = featurehub_repository.FeatureHubRepository()

    def tearDown(self):
        self.repo.features.clear()

    def test_notify_func(self):
        features = [{'id': '123', 'key': 'FEATURE_TITLE_TO_UPPERCASE',
                     'l': True, 'version': 1, 'type': 'BOOLEAN', 'value': False, 'strategies': []}]

        self.repo.notify('features', features)

        self.assertTrue(self.repo.is_ready())

        self.assertEqual(self.repo.extract_feature_state(), features)

    def test_notify_func_update_version(self):
        key = 'FEATURE_TITLE_TO_UPPERCASE'
        features = [{'id': '123', 'key': key,
                     'l': True, 'version': 1, 'type': 'BOOLEAN', 'value': False, 'strategies': []}]

        self.repo.notify('features', features)

        self.assertEquals(self.repo.feature(key).get_version(), 1)
        self.assertEquals(self.repo.feature(key).get_boolean(), False)
        self.assertEquals(self.repo.feature(key).get_number(), None)

        features = [{'id': '123', 'key': key,
                     'l': True, 'version': 2, 'type': 'BOOLEAN', 'value': True, 'strategies': []}]

        self.repo.notify('features', features)
        self.assertEquals(self.repo.feature(key).get_version(), 2)
        self.assertEquals(self.repo.feature(key).get_boolean(), True)
        self.assertEquals(self.repo.feature(key).get_number(), None)

        self.repo.notify('features', features)
        self.assertEquals(self.repo.feature(key).get_version(), 2)

        self.assertEqual(self.repo.extract_feature_state(), features)

    def test_notify_func_add_new_feature(self):
        key = 'FEATURE_TITLE_TO_UPPERCASE'
        features = [{'id': '123', 'key': key,
                     'l': True, 'version': 1, 'type': 'BOOLEAN', 'value': False, 'strategies': []}]

        self.repo.notify('features', features)
        self.assertTrue(self.repo.is_ready(), True)
        self.assertEquals(self.repo.feature(key).get_version(), 1)

        # now ask for the feature before it exists, this tests to ensure that the repository creates a placeholder for it
        new_key = 'FEATURE_STAFF_PHOTOS'
        repo_feature = self.repo.feature(new_key)
        # and the placeholder returns a -1 for the version because there is no data, which ensures any new feature from
        # the server will replace it
        self.assertEquals(repo_feature.get_version(), -1)
        new_features = [{'id': '1234', 'key': new_key,
                     'l': False, 'version': 2, 'type': 'NUMBER', 'value': 123.78, 'strategies': []}]
        self.repo.notify('features', new_features)
        # now make sure the feature we already refer to has been updated
        self.assertEquals(repo_feature.get_version(), 2)
        self.assertEquals(repo_feature.get_number(), 123.78)

        # now we need to just update a single feature
        single_feature = {'id': '1234', 'key': new_key,
                          'l': False, 'version': 3, 'type': 'NUMBER', 'value': 128, 'strategies': []}
        self.repo.notify('feature', single_feature)

        self.assertEquals(repo_feature.get_version(), 3)
        self.assertEquals(repo_feature.get_number(), 128)

        # now we send through a delete for that feature
        delete_feature =  {'id': '123', 'key': new_key}
        self.repo.notify('delete_feature', delete_feature)
        self.assertEquals(repo_feature.get_version(), -1)

    def test_non_invalid_feature_states_ignored(self):
        features = [None, {id: 'fred'}]
        self.repo.notify('features', features)
        self.assertEquals(len(self.repo.extract_feature_state()), 0)

    def test_update_feature_older_version(self):
        new_key = 'FEATURE_STAFF_PHOTOS'
        repo_feature = self.repo.feature(new_key)
        new_features = [{'id': '1234', 'key': new_key,
                         'l': False, 'version': 2, 'type': 'NUMBER', 'value': 123.78, 'strategies': []}]
        self.repo.notify('features', new_features)
        self.assertEquals(repo_feature.get_version(), 2)

        self.repo.not_ready()
        self.assertEquals(self.repo.is_ready(), False)

        lesser_features = [{'id': '1234', 'key': new_key,
                         'l': False, 'version': 1, 'type': 'NUMBER', 'value': 123.78, 'strategies': []}]
        self.repo.notify('features', lesser_features)
        self.assertEquals(self.repo.is_ready(), True)

        self.assertEquals(repo_feature.get_version(), 2)

    def test_notify_func_no_features(self):
        self.repo.notify('failed', None)
        self.assertFalse(self.repo.is_ready())
        self.assertEquals(len(self.repo.extract_feature_state()), 0)

    def test_add_interceptor(self):
        mock_interceptor = MagicMock()
        mock_interceptor.intercepted_value = lambda key: InterceptorValue(345)
        self.repo.register_interceptor(mock_interceptor)
        found = self.repo.find_interceptor('key')
        self.assertNotEqual(found, None)
        self.assertEquals(found.cast('NUMBER'), 345)
        self.assertEquals(found.cast('STRING'), '345')


if __name__ == '__main__':
    unittest.main()
