from unittest import TestCase
from unittest.mock import patch, MagicMock

from featurehub_sdk.featurehub_repository import FeatureHubRepository
from featurehub_sdk.polling_edge_service import PollingEdgeService

import asyncio
import unittest

from featurehub_sdk.version import sdk_version


class PollingEdgeServiceTest(TestCase):
    def test_success_base_case(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            http_mock = http_class_mock.return_value
            data_mock = MagicMock(name='data-mock')
            data_mock.decode.return_value = '[{"features":[{"a":1}]}]'
            resp = MagicMock(name="http-response")
            resp.status = 200
            resp.headers = {}
            resp.data = data_mock
            http_mock.request.return_value = resp
            repo = MagicMock(spec=FeatureHubRepository)

            poller = PollingEdgeService('http://localhost', ['123'], repo, 0)
            asyncio.run(poller.poll())
            repo.notify.assert_called_with('features', [{'a': 1}])
            self.assertFalse(poller.cancelled)

    def _data_mock(self):
        data_mock = MagicMock(name='data-mock')
        data_mock.decode.return_value = '{}'
        return data_mock

    def test_success_has_cache_control(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            http_mock = http_class_mock.return_value
            resp = MagicMock(name="http-response")
            resp.status = 200
            resp.headers = {'cache-control': 'private, max-age=20', 'etag': 'abcde'}
            resp.data = self._data_mock()
            http_mock.request.return_value = resp
            repo = MagicMock(spec=FeatureHubRepository)

            poller = PollingEdgeService('http://localhost/', ['123'], repo, 0)
            asyncio.run(poller.poll())
            self.assertEqual(poller.interval, 20)
            resp.headers = {'cache-control': 'private, max-age=16'}
            resp.status = 236
            asyncio.run(poller.poll())
            http_mock.request.assert_called_with(method='GET', url='http://localhost/features?apiKey=123&contextSha=0',
                                                 headers={'X-SDK': 'Python',
                                                          'X-SDK-Version': sdk_version,
                                                          'if-none-match': 'abcde'
                                                          })
            self.assertEqual(poller.interval, 16)
            self.assertTrue(poller.stopped)

    def test_poller_uses_server_eval_key(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            http_mock = http_class_mock.return_value
            resp = MagicMock(name="http-response")
            resp.status = 200
            resp.headers = {}
            resp.data = self._data_mock()
            http_mock.request.return_value = resp
            repo = MagicMock(spec=FeatureHubRepository)

            poller = PollingEdgeService('http://localhost/', ['123'], repo, 0)
            asyncio.run(poller.context_change('1234'))
            http_mock.request.assert_called_with(method='GET', url='http://localhost/features?apiKey=123&contextSha=03ac674216f3e15c761ee1a5e255f067953623c8b388b4459e13f978d7c846f4',
                                                 headers={'X-SDK': 'Python',
                                                          'X-SDK-Version': sdk_version,
                                                          'x-featurehub': '1234'
                                                          })

    def test_with_failure(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            http_mock = http_class_mock.return_value
            resp = MagicMock(name="http-response")
            resp.status = 404
            http_mock.request.return_value = resp
            repo = MagicMock(spec=FeatureHubRepository)
            poller = PollingEdgeService('http://localhost', ['123'], repo, 0)
            asyncio.run(poller.poll())
            repo.notify.assert_called_with('failed', None)
            self.assertTrue(poller.cancelled)

    def test_with_dacha_not_ready(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            http_mock = http_class_mock.return_value
            resp = MagicMock(name="http-response")
            resp.status = 503
            http_mock.request.return_value = resp
            repo = MagicMock(spec=FeatureHubRepository)
            poller = PollingEdgeService('http://localhost', ['123'], repo, 0)
            asyncio.run(poller.poll())
            repo.notify.assert_not_called()
            self.assertFalse(poller.cancelled)

    def test_with_environment_stale(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            http_mock = http_class_mock.return_value
            resp = MagicMock(name="http-response")
            resp.status = 236
            resp.headers = {}
            data_mock = MagicMock(name='data-mock')
            data_mock.decode.return_value = '[{"features":[{"a":1}]}]'

            resp.data = data_mock
            http_mock.request.return_value = resp
            repo = MagicMock(spec=FeatureHubRepository)

            poller = PollingEdgeService('http://localhost', ['123'], repo, 0)
            asyncio.run(poller.poll())
            repo.notify.assert_called_with('features', [{'a': 1}])
            self.assertFalse(poller.cancelled)
            self.assertTrue(poller.stopped)

if __name__ == '__main__':
    unittest.main()