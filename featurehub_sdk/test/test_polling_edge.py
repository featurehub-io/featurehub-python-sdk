from unittest import TestCase
from unittest.mock import patch, MagicMock

from featurehub_sdk.featurehub_repository import FeatureHubRepository
from featurehub_sdk.polling_edge_service import PollingEdgeService

import asyncio
import unittest

class PollingEdgeServiceTest(TestCase):
    def test_success_base_case(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            http_mock = http_class_mock.return_value
            data_mock = MagicMock(name='data-mock')
            data_mock.decode.return_value = '[{"features":[{"a":1}]}]'
            resp = MagicMock(name="http-response")
            resp.status = 200
            resp.data = data_mock
            http_mock.request.return_value = resp
            repo = MagicMock(spec=FeatureHubRepository)

            poller = PollingEdgeService('http://localhost', ['123'], repo, 0)
            asyncio.run(poller.poll())
            repo.notify.assert_called_with('features', [{'a': 1}])
            self.assertFalse(poller.cancelled)

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


if __name__ == '__main__':
    unittest.main()