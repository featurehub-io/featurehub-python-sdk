import os
import unittest
from unittest.mock import MagicMock, patch

import urllib3

from featurehub_sdk.featurehub_repository import FeatureHubRepository
from featurehub_sdk.polling_request import FetchOutcome, PollingRequest


def _response(status=200, body='[]', headers=None):
    resp = MagicMock(name=f"http-{status}")
    resp.status = status
    resp.headers = headers or {}
    resp.data.decode.return_value = body
    return resp


# the request on its own: no worker thread, no schedule
class PollingRequestTest(unittest.TestCase):
    def setUp(self):
        patcher = patch("urllib3.PoolManager")
        self.http = patcher.start().return_value
        self.addCleanup(patcher.stop)
        self.repo = MagicMock(spec=FeatureHubRepository)
        with patch.dict(os.environ, {}, clear=True):
            self.request = PollingRequest('http://chago/', ['ling', 'orm'], self.repo, {'X-Shop': 'omu&co'})

    def _fetch(self, resp, wanted=True):
        self.http.request.return_value = resp
        return self.request.fetch(lambda: wanted)

    def test_features_from_every_environment_are_one_set(self):
        result = self._fetch(_response(body='[{"features":[{"key":"keep_silent"}]},{"features":[{"key":"chago"}]}]'))
        self.assertEqual(result.outcome, FetchOutcome.FEATURES)
        self.repo.notify.assert_called_once_with('features', [{'key': 'keep_silent'}, {'key': 'chago'}])

    def test_outcomes_by_status(self):
        for status, outcome in ((236, FetchOutcome.STALE), (304, FetchOutcome.UNCHANGED), (401, FetchOutcome.REJECTED),
                                (429, FetchOutcome.REJECTED), (503, FetchOutcome.FAILED), (502, FetchOutcome.FAILED)):
            result = self._fetch(_response(status))
            self.assertEqual(result.outcome, outcome, status)
            self.assertEqual(result.status, status)

    def test_a_bad_body_or_network_error_is_a_temporary_failure(self):
        for body in ('not json', '{"features":[]}', '[{"features":"always wonder"}]'):
            self.assertEqual(self._fetch(_response(body=body, headers={'etag': '"x"'})).outcome, FetchOutcome.FAILED)
        self.assertIsNone(self.request._etag)
        self.http.request.side_effect = urllib3.exceptions.NewConnectionError(None, "refused")
        self.assertEqual(self.request.fetch(lambda: True).outcome, FetchOutcome.FAILED)

    def test_a_response_no_longer_wanted_applies_nothing(self):
        result = self._fetch(_response(headers={'etag': '"x"'}), wanted=False)
        self.assertEqual(result.outcome, FetchOutcome.DISCARDED)
        self.repo.notify.assert_not_called()
        self.assertIsNone(self.request._etag)

    def test_the_max_age_is_reported(self):
        result = self._fetch(_response(headers={'cache-control': 'private, max-age=20'}))
        self.assertEqual(result.max_age, 20)
        self.assertIsNone(self._fetch(_response(headers={'cache-control': 'no-store'})).max_age)

    def test_the_etag_is_sent_until_the_context_changes(self):
        self._fetch(_response(headers={'etag': '"lingorm"'}))
        self._fetch(_response(304))
        self.assertEqual(self.http.request.call_args.kwargs['headers']['if-none-match'], '"lingorm"')
        self.assertTrue(self.request.change_context('userkey=kornaphat'))
        self.assertFalse(self.request.change_context('userkey=kornaphat'))
        self._fetch(_response(304))
        headers = self.http.request.call_args.kwargs['headers']
        self.assertNotIn('if-none-match', headers)
        self.assertEqual(headers['x-featurehub'], 'userkey=kornaphat')
        self.assertEqual(headers['X-Shop'], 'omu&co')
        self.assertIn('&contextSha=', self.http.request.call_args.kwargs['url'])
        self.assertTrue(self.http.request.call_args.kwargs['url'].endswith('&sdk_version=2'))

    def test_the_url_has_its_parameters_in_order(self):
        self.assertEqual(self.request.url(), 'http://chago/features?apiKey=ling&apiKey=orm&contextSha=0&sdk_version=2')


if __name__ == '__main__':
    unittest.main()
