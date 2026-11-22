import unittest
from unittest.mock import MagicMock

from featurehub_sdk.client_context import Readiness
from featurehub_sdk.featurehub_repository import FeatureHubRepository
from featurehub_sdk.interceptors import InterceptorValue, ValueInterceptor


class FeatureHubRepositoryTest(unittest.TestCase):
    repo: FeatureHubRepository

    def setUp(self):
        self.repo = FeatureHubRepository()

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

        self.assertEqual(self.repo.feature(key).get_version, 1)
        self.assertEqual(self.repo.feature(key).get_boolean, False)
        self.assertEqual(self.repo.feature(key).get_number, None)

        features = [{'id': '123', 'key': key,
                     'l': True, 'version': 2, 'type': 'BOOLEAN', 'value': True, 'strategies': []}]

        self.repo.notify('features', features)
        self.assertEqual(self.repo.feature(key).get_version, 2)
        self.assertEqual(self.repo.feature(key).get_boolean, True)
        self.assertEqual(self.repo.feature(key).get_number, None)

        self.repo.notify('features', features)
        self.assertEqual(self.repo.feature(key).get_version, 2)

        self.assertEqual(self.repo.extract_feature_state(), features)

    def test_notify_func_add_new_feature(self):
        key = 'FEATURE_TITLE_TO_UPPERCASE'
        features = [{'id': '123', 'key': key,
                     'l': True, 'version': 1, 'type': 'BOOLEAN', 'value': False, 'strategies': []}]

        self.repo.notify('features', features)
        self.assertTrue(self.repo.is_ready(), True)
        self.assertEqual(self.repo.feature(key).get_version, 1)

        # now ask for the feature before it exists, this tests to ensure that the self.repository creates a placeholder for it
        new_key = 'FEATURE_STAFF_PHOTOS'
        feature = self.repo.feature(new_key)
        # and the placeholder returns a -1 for the version because there is no data, which ensures any new feature from
        # the server will replace it
        self.assertEqual(feature.get_version, -1)
        new_features = [{'id': '1234', 'key': new_key,
                     'l': False, 'version': 2, 'type': 'NUMBER', 'value': 123.78, 'strategies': []}]
        self.repo.notify('features', new_features)
        # now make sure the feature we already refer to has been updated
        self.assertEqual(feature.get_version, 2)
        self.assertEqual(feature.get_number, 123.78)

        # now we need to just update a single feature
        single_feature = {'id': '1234', 'key': new_key,
                          'l': False, 'version': 3, 'type': 'NUMBER', 'value': 128, 'strategies': []}
        self.repo.notify('feature', single_feature)

        self.assertEqual(feature.get_version, 3)
        self.assertEqual(feature.get_number, 128)

        # now we send through a delete for that feature
        delete_feature =  {'id': '123', 'key': new_key}
        self.repo.notify('delete_feature', delete_feature)
        self.assertEqual(feature.get_version, -1)

    def test_update_holder_feature(self):
        key = 'FEATURE_TITLE_TO_UPPERCASE'
        feat = self.repo.feature(key)
        self.assertFalse(feat.exists)
        feature = {'id': '123', 'key': key,
                     'l': True, 'version': 1, 'type': 'BOOLEAN', 'value': False, 'strategies': []}
        self.repo.notify('feature', feature)
        self.assertTrue(feat.exists)

    def test_non_invalid_feature_states_ignored(self):
        features = [None, {id: 'fred'}]
        self.repo.notify('features', features)
        self.assertEqual(len(self.repo.extract_feature_state()), 0)

    def test_update_feature_older_version(self):
        new_key = 'FEATURE_STAFF_PHOTOS'
        repo_feature = self.repo.feature(new_key)
        new_features = [{'id': '1234', 'key': new_key,
                         'l': False, 'version': 2, 'type': 'NUMBER', 'value': 123.78, 'strategies': []}]
        self.repo.notify('features', new_features)
        self.assertEqual(repo_feature.get_version, 2)

        self.repo.not_ready()
        self.assertEqual(self.repo.readiness, Readiness.Stale)

        lesser_features = [{'id': '1234', 'key': new_key,
                         'l': False, 'version': 1, 'type': 'NUMBER', 'value': 123.78, 'strategies': []}]
        self.repo.notify('features', lesser_features)
        self.assertEqual(self.repo.is_ready(), True)

        self.assertEqual(repo_feature.get_version, 2)

    def test_notify_func_no_features(self):
        self.repo.notify('failed', None)
        self.assertFalse(self.repo.is_ready())
        self.assertEqual(self.repo.readiness, Readiness.Failed)
        self.assertEqual(len(self.repo.extract_feature_state()), 0)

    def test_add_interceptor(self):
        mock_interceptor = MagicMock()
        mock_interceptor.intercepted_value = lambda key: InterceptorValue(345)
        self.repo.register_interceptor(mock_interceptor)
        found = self.repo.find_interceptor('key')
        # meth.assert_called_once()
        self.assertNotEqual(found, None)
        self.assertEqual(found.cast('NUMBER'), 345)
        self.assertEqual(found.cast('STRING'), '345')


def _feature(key='ling', fid='lingling', version=1, value=True, ftype='BOOLEAN', v=None):
    f = {'id': fid, 'key': key, 'l': False, 'version': version, 'type': ftype, 'value': value}
    if v is not None:
        f['v'] = v
    return f


class FeatureHubRepositoryReadinessTest(unittest.TestCase):
    def setUp(self):
        self.repo = FeatureHubRepository()

    def test_starts_not_ready(self):
        self.assertEqual(self.repo.readiness, Readiness.NotReady)
        self.assertFalse(self.repo.is_ready())

    def test_failure_after_features_is_stale_and_keeps_the_features(self):
        self.repo.notify('features', [_feature()])
        for name in ('failure', 'failed'):
            self.repo.notify(name, None)
            self.assertEqual(self.repo.readiness, Readiness.Stale)
        self.assertTrue(self.repo.is_ready())
        self.assertTrue(self.repo.connection_failed)
        self.assertTrue(self.repo.feature('ling').get_boolean)

    def test_environment_stale_after_features(self):
        self.repo.notify('features', [_feature()])
        self.repo.mark_environment_stale()
        self.assertTrue(self.repo.environment_stale)
        self.assertEqual(self.repo.readiness, Readiness.Stale)
        self.assertTrue(self.repo.feature('ling').get_boolean)

    def test_environment_stale_before_features_stays_not_ready(self):
        self.repo.mark_environment_stale()
        self.assertTrue(self.repo.environment_stale)
        self.assertEqual(self.repo.readiness, Readiness.NotReady)

    def test_stale_is_final_but_features_still_apply(self):
        self.repo.notify('features', [_feature()])
        self.repo.mark_environment_stale()
        self.repo.notify('features', [_feature(version=2, value=False)])
        self.repo.not_ready()
        self.assertEqual(self.repo.readiness, Readiness.Stale)
        self.assertFalse(self.repo.feature('ling').get_boolean)

    def test_bye_changes_nothing(self):
        self.repo.notify('bye', None)
        self.assertEqual(self.repo.readiness, Readiness.NotReady)
        self.repo.notify('features', [_feature()])
        self.repo.notify('bye', None)
        self.assertEqual(self.repo.readiness, Readiness.Ready)
        self.assertTrue(self.repo.feature('ling').get_boolean)

    def test_a_single_feature_does_not_make_it_ready(self):
        self.repo.notify('feature', _feature())
        self.assertEqual(self.repo.readiness, Readiness.NotReady)
        self.assertTrue(self.repo.feature('ling').get_boolean)

    def test_failure_after_a_context_change_reset_is_still_stale(self):
        self.repo.notify('features', [_feature()])
        self.repo.not_ready()  # a server evaluated context change is being fetched
        self.repo.notify('failed', None)
        self.assertEqual(self.repo.readiness, Readiness.Stale)
        self.assertTrue(self.repo.connection_failed)
        self.assertTrue(self.repo.feature('ling').get_boolean)
        self.repo.notify('features', [_feature()])  # nothing will bring it up to date now
        self.assertEqual(self.repo.readiness, Readiness.Stale)

    def test_features_that_are_not_a_list_change_nothing(self):
        self.repo.notify('features', [_feature()])
        self.repo.not_ready()
        for data in ('keep silent', {'error': 'chago'}, 7):
            self.repo.notify('features', data)
            self.assertTrue(self.repo.feature('ling').get_boolean)
            self.assertEqual(self.repo.readiness, Readiness.Stale)

    def test_context_change_is_stale_until_its_features_arrive(self):
        self.repo.notify('features', [_feature()])
        self.repo.not_ready()
        self.assertEqual(self.repo.readiness, Readiness.Stale)
        self.assertTrue(self.repo.is_ready())  # the old features are still served
        self.assertFalse(self.repo.connection_failed)
        self.repo.notify('features', [_feature(version=2, value=False)])
        self.assertEqual(self.repo.readiness, Readiness.Ready)
        self.assertFalse(self.repo.feature('ling').get_boolean)

    def test_connection_failed_is_raised_once_and_kept(self):
        self.assertFalse(self.repo.connection_failed)
        self.repo.notify('failure', None)
        self.assertTrue(self.repo.connection_failed)
        self.assertEqual(self.repo.readiness, Readiness.Failed)
        self.repo.notify('failure', None)
        self.repo.notify('features', [_feature()])  # Failed is final
        self.assertEqual(self.repo.readiness, Readiness.Failed)

    def test_failure_before_features_after_a_context_change_is_failed(self):
        self.repo.not_ready()  # nothing held yet, so nothing changes
        self.assertEqual(self.repo.readiness, Readiness.NotReady)
        self.repo.notify('failed', None)
        self.assertEqual(self.repo.readiness, Readiness.Failed)

    def test_not_ready_only_changes_ready(self):
        self.repo.notify('failed', None)
        self.repo.not_ready()
        self.assertEqual(self.repo.readiness, Readiness.Failed)


class FeatureHubRepositoryUpdateTest(unittest.TestCase):
    def setUp(self):
        self.repo = FeatureHubRepository()

    def test_a_full_set_removes_features_not_in_it(self):
        self.repo.notify('features', [_feature('ling', 'lingling'), _feature('orm', 'ormkorn')])
        orm = self.repo.feature('orm')
        asked_for = self.repo.feature('chago')  # only asked for by code, never a feature
        self.repo.notify('features', [_feature('ling', 'lingling')])
        self.assertTrue(self.repo.feature('ling').exists)
        self.assertFalse(orm.exists)
        self.assertIsNone(orm.get_boolean)
        self.assertIs(self.repo.feature('chago'), asked_for)
        self.assertEqual([f['key'] for f in self.repo.extract_feature_state()], ['ling'])

    def test_an_empty_full_set_removes_everything(self):
        self.repo.notify('features', [_feature()])
        self.repo.notify('features', [])
        self.assertFalse(self.repo.feature('ling').exists)
        self.assertEqual(self.repo.readiness, Readiness.Ready)

    def test_same_version_with_a_different_strategy_is_replaced(self):
        self.repo.notify('features', [_feature(ftype='STRING', value='keep silent', v='always-wonder')])
        self.repo.notify('features', [_feature(ftype='STRING', value='keep silent', v=None)])
        self.assertIsNone(self.repo.feature('ling').internal_feature_state.get('v'))

    def test_same_version_with_a_different_id_or_type_is_replaced(self):
        self.repo.notify('features', [_feature(fid='lingling', value='kwong pastry', ftype='STRING')])
        self.repo.notify('features', [_feature(fid='sirilak', value='kwong pastry', ftype='STRING')])
        self.assertEqual(self.repo.feature('ling').id, 'sirilak')
        self.repo.notify('features', [_feature(fid='sirilak', value='kwong pastry', ftype='JSON')])
        self.assertEqual(self.repo.feature('ling').feature_type, 'JSON')

    def test_same_version_and_same_content_is_not_replaced(self):
        first = _feature()
        self.repo.notify('features', [first])
        self.repo.notify('features', [_feature()])
        self.assertIs(self.repo.feature('ling').internal_feature_state, first)

    def test_older_version_is_rejected(self):
        self.repo.notify('features', [_feature(version=3)])
        self.repo.notify('feature', _feature(version=2, value=False))
        self.assertTrue(self.repo.feature('ling').get_boolean)

    def test_a_number_version_is_truncated(self):
        self.repo.notify('features', [_feature(version=2.7)])
        self.assertEqual(self.repo.feature('ling').get_version, 2)

    def test_a_feature_without_a_version_or_type_is_ignored(self):
        for field in ('version', 'type'):
            self.repo.notify('features', [_feature('orm', 'ormkorn')])
            f = _feature()
            del f[field]
            self.repo.notify('features', [f, _feature('orm', 'ormkorn')])
            self.assertFalse(self.repo.feature('ling').exists, field)
            self.assertTrue(self.repo.feature('orm').exists, field)

    def test_delete_feature_by_either_name(self):
        for name in ('delete_feature', 'deleteFeature'):
            self.repo.notify('features', [_feature()])
            self.repo.notify(name, {'id': 'lingling', 'key': 'ling'})
            self.assertFalse(self.repo.feature('ling').exists)


class FeatureHubRepositoryListenerTest(unittest.TestCase):
    def setUp(self):
        self.repo = FeatureHubRepository()
        self.readiness = []
        self.repo.register_readiness_listener(self.readiness.append)

    def test_readiness_listener_gets_the_current_readiness_at_once(self):
        self.assertEqual(self.readiness, [Readiness.NotReady])

    def test_every_full_set_that_leaves_it_ready_is_broadcast(self):
        self.repo.notify('features', [_feature()])
        self.repo.notify('features', [_feature()])
        self.assertEqual(self.readiness, [Readiness.NotReady, Readiness.Ready, Readiness.Ready])

    def test_single_features_bye_and_invalid_payloads_are_not_broadcast(self):
        self.repo.notify('features', [_feature()])
        self.repo.notify('feature', _feature(version=2))
        self.repo.notify('delete_feature', {'id': 'lingling', 'key': 'ling'})
        self.repo.notify('bye', None)
        self.repo.notify('features', 'keep silent')
        self.assertEqual(self.readiness, [Readiness.NotReady, Readiness.Ready])

    def test_context_change_broadcasts_stale_then_ready(self):
        self.repo.notify('features', [_feature()])
        self.repo.not_ready()
        self.repo.not_ready()  # already Stale, so nothing more
        self.repo.notify('features', [_feature(version=2)])
        self.assertEqual(self.readiness, [Readiness.NotReady, Readiness.Ready, Readiness.Stale, Readiness.Ready])

    def test_connection_failed_is_its_own_event_raised_once(self):
        failed = []
        self.repo.register_connection_failed_listener(lambda: failed.append(self.repo.readiness))
        self.repo.notify('features', [_feature()])
        self.repo.notify('failure', None)
        self.repo.notify('failed', None)
        # raised once, after the repository's state has changed
        self.assertEqual(failed, [Readiness.Stale])
        self.assertEqual(self.readiness, [Readiness.NotReady, Readiness.Ready, Readiness.Stale])
        # a full set after it is applied, but readiness stays Stale and isn't broadcast
        self.repo.notify('features', [_feature(version=2)])
        self.assertEqual(self.readiness, [Readiness.NotReady, Readiness.Ready, Readiness.Stale])

    def test_connection_failed_before_features_is_failed(self):
        failed = []
        self.repo.register_connection_failed_listener(lambda: failed.append(True))
        self.repo.notify('failure', None)
        self.assertEqual(failed, [True])
        self.assertEqual(self.readiness, [Readiness.NotReady, Readiness.Failed])

    def test_environment_stale_is_its_own_event_raised_once(self):
        stale = []
        self.repo.register_environment_stale_listener(lambda: stale.append(self.repo.readiness))
        self.repo.notify('features', [_feature()])
        self.repo.mark_environment_stale()
        self.repo.mark_environment_stale()
        self.assertEqual(stale, [Readiness.Stale])
        self.assertEqual(self.readiness, [Readiness.NotReady, Readiness.Ready, Readiness.Stale])

    def test_environment_stale_before_features_does_not_change_readiness(self):
        stale = []
        self.repo.register_environment_stale_listener(lambda: stale.append(True))
        self.repo.mark_environment_stale()
        self.assertEqual(stale, [True])
        self.assertEqual(self.readiness, [Readiness.NotReady])

    def test_late_listeners_hear_about_events_that_already_happened(self):
        self.repo.notify('features', [_feature()])
        self.repo.mark_environment_stale()
        self.repo.notify('failure', None)
        heard = []
        self.repo.register_environment_stale_listener(lambda: heard.append('always wonder'))
        self.repo.register_connection_failed_listener(lambda: heard.append('chago'))
        late_readiness = []
        self.repo.register_readiness_listener(late_readiness.append)
        self.assertEqual(heard, ['always wonder', 'chago'])
        self.assertEqual(late_readiness, [Readiness.Stale])

    def test_removed_listeners_are_not_called(self):
        heard = []
        remove = self.repo.register_readiness_listener(heard.append)
        remove_failed = self.repo.register_connection_failed_listener(lambda: heard.append('failed'))
        remove()
        remove()  # removing twice is harmless
        remove_failed()
        self.repo.notify('features', [_feature()])
        self.repo.notify('failure', None)
        self.assertEqual(heard, [Readiness.NotReady])

    def test_a_failing_listener_does_not_stop_the_others(self):
        def boom(readiness):
            if readiness == Readiness.Ready:
                raise RuntimeError("kwong pastry burnt")

        self.repo.register_readiness_listener(boom)
        heard = []
        self.repo.register_readiness_listener(heard.append)
        with self.assertLogs('featurehub_sdk', level='ERROR'):
            self.repo.notify('features', [_feature()])
        self.assertEqual(heard, [Readiness.NotReady, Readiness.Ready])
        self.assertTrue(self.repo.feature('ling').get_boolean)

    def test_a_listener_can_remove_itself(self):
        heard = []

        def once(readiness):
            heard.append(readiness)
            if readiness == Readiness.Ready:
                remove()

        remove = self.repo.register_readiness_listener(once)
        self.repo.notify('features', [_feature()])
        self.repo.notify('features', [_feature()])
        self.assertEqual(heard, [Readiness.NotReady, Readiness.Ready])

    def test_listeners_are_called_outside_the_lock(self):
        # a listener on another thread's notification can read the repository without deadlocking
        import threading
        seen = []
        self.repo.register_readiness_listener(lambda r: seen.append(self.repo.feature('ling').get_boolean))
        t = threading.Thread(target=lambda: self.repo.notify('features', [_feature()]))
        t.start()
        t.join(2)
        self.assertFalse(t.is_alive())
        self.assertEqual(seen, [None, True])


if __name__ == '__main__':
    unittest.main()
