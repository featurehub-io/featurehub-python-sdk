import unittest
from unittest import TestCase

import featurehub_repository
from fh_state_base_holder import FeatureStateBaseHolder


class FeatureHubRepositoryTest(unittest.TestCase):
    repo: featurehub_repository.FeatureHubRepository

    def setUp(self):
        self.repo = featurehub_repository.FeatureHubRepository()

    def tearDown(self):
        self.repo.features.clear()

    def test_notify_func(self):
        self.repo.notify('FEATURES',
                    [{'features': [{'id': '123', 'key': 'FEATURE_TITLE_TO_UPPERCASE',
                                    'l': True, 'version': 1, 'type': 'BOOLEAN', 'value': False, 'strategies': []}]}])
        self.assertTrue(self.repo.ready)

        expected = FeatureStateBaseHolder(
            {'id': '123', 'key': 'FEATURE_TITLE_TO_UPPERCASE',
             'l': True, 'version': 1, 'type': 'BOOLEAN', 'value': False, 'strategies': []}, )

        self.assertEqual(self.repo.features, self.repo.features | {'FEATURE_TITLE_TO_UPPERCASE': expected}, self.repo.features)

    def test_notify_func_update_version(self):
        self.repo.notify('FEATURES',
                    [{'features': [{'id': '123', 'key': 'FEATURE_TITLE_TO_UPPERCASE',
                                    'l': True, 'version': 1, 'type': 'BOOLEAN', 'value': False, 'strategies': []}]}])
        self.assertTrue(self.repo.ready)

        expected = FeatureStateBaseHolder(
            {'id': '123', 'key': 'FEATURE_TITLE_TO_UPPERCASE',
             'l': True, 'version': 1, 'type': 'BOOLEAN', 'value': False, 'strategies': []}, )

        self.assertEqual(self.repo.features, self.repo.features | {'FEATURE_TITLE_TO_UPPERCASE': expected}, self.repo.features)

        self.repo.notify('FEATURES',
                    [{'features': [{'id': '123', 'key': 'FEATURE_TITLE_TO_UPPERCASE',
                                    'l': True, 'version': 2, 'type': 'BOOLEAN', 'value': True, 'strategies': []}]}])

        expected2 = FeatureStateBaseHolder(
            {'id': '123', 'key': 'FEATURE_TITLE_TO_UPPERCASE',
             'l': True, 'version': 2, 'type': 'BOOLEAN', 'value': True, 'strategies': []}, )

        self.assertEqual(self.repo.features, self.repo.features | {'FEATURE_TITLE_TO_UPPERCASE': expected2}, self.repo.features)

    def test_notify_func_add_new_feature(self):
        self.repo.notify('FEATURES',
                    [{'features': [{'id': '123', 'key': 'FEATURE_TITLE_TO_UPPERCASE',
                                    'l': True, 'version': 1, 'type': 'BOOLEAN', 'value': False, 'strategies': []}]}])
        self.assertTrue(self.repo.ready)

        expected = FeatureStateBaseHolder(
            {'id': '123', 'key': 'FEATURE_TITLE_TO_UPPERCASE',
             'l': True, 'version': 1, 'type': 'BOOLEAN', 'value': False, 'strategies': []}, )

        self.assertEqual(self.repo.features, self.repo.features | {'FEATURE_TITLE_TO_UPPERCASE': expected}, self.repo.features)

        self.repo.notify('FEATURES', [{'features': [{'id': '123', 'key': 'FEATURE_NEW',
                                                'l': True, 'version': 1, 'type': 'BOOLEAN', 'value': True,
                                                'strategies': []}]}])

        expected2 = FeatureStateBaseHolder({'id': '123', 'key': 'FEATURE_NEW',
                                            'l': True, 'version': 1, 'type': 'BOOLEAN', 'value': True,
                                            'strategies': []}, )

        self.assertEqual(self.repo.features, self.repo.features | {'FEATURE_NEW': expected2}, self.repo.features)

    def test_notify_func_no_features(self):
        self.repo.notify('FAILED', None)
        self.assertFalse(self.repo.ready)
        self.assertEqual(self.repo.features, self.repo.features | {}, self.repo.features)

    def test_feature(self):
        self.repo.notify('FEATURES',
                    [{'features': [{'id': '123', 'key': 'bla',
                                    'l': True, 'version': 1, 'type': 'BOOLEAN', 'value': False, 'strategies': []}]}])
        feature = self.repo.feature('bla')
        self.assertIsNotNone(feature)

    def test_feature_none(self):
        feature = self.repo.feature('bla')
        self.assertIsNone(feature)


if __name__ == '__main__':
    unittest.main()
