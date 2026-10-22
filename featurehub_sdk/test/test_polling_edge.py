from unittest import TestCase
from unittest.mock import patch, MagicMock

from featurehub_sdk.featurehub_repository import FeatureHubRepository
from featurehub_sdk.polling_edge_service import PollingEdgeService

import asyncio
import os
import threading
import time
import unittest
import urllib3

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
                                                          },
                                                 timeout=PollingEdgeService.TIMEOUT)
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
                                                          },
                                                 timeout=PollingEdgeService.TIMEOUT)

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

    def test_server_unavailable_keeps_polling(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            http_mock = http_class_mock.return_value
            http_mock.request.side_effect = urllib3.exceptions.MaxRetryError(None, 'http://localhost', 'refused')
            repo = MagicMock(spec=FeatureHubRepository)

            poller = PollingEdgeService('http://localhost', ['123'], repo, 30)
            asyncio.run(poller.poll())  # must not raise
            try:
                repo.notify.assert_not_called()
                self.assertFalse(poller.cancelled)
                self.assertIsNotNone(poller._worker)  # still polling
            finally:
                poller.close()

    def test_invalid_json_keeps_polling(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            http_mock = http_class_mock.return_value
            resp = MagicMock(name="http-response")
            resp.status = 200
            resp.headers = {}
            resp.data.decode.return_value = '<html>gateway error</html>'
            http_mock.request.return_value = resp
            repo = MagicMock(spec=FeatureHubRepository)

            poller = PollingEdgeService('http://localhost', ['123'], repo, 30)
            asyncio.run(poller.poll())  # must not raise
            try:
                repo.notify.assert_not_called()
                self.assertIsNotNone(poller._worker)
            finally:
                poller.close()

    def test_update_interval_restarts_closed_polling(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller, repo = self._poller_returning(http_class_mock, '[]')
            asyncio.run(poller.poll())
            worker = poller._worker
            poller.close()
            worker.join(1)
            self.assertIsNone(poller._worker)

            poller.update_interval(30)
            try:
                self.assertFalse(poller.cancelled)
                self.assertEqual(poller.interval, 30)
                self.assertIsNotNone(poller._worker)
            finally:
                poller.close()

    def _poller_returning(self, http_class_mock, body, status=200, headers=None, interval=30):
        resp = MagicMock(name="http-response")
        resp.status = status
        resp.headers = headers or {}
        resp.data.decode.return_value = body
        http_class_mock.return_value.request.return_value = resp
        repo = MagicMock(spec=FeatureHubRepository)
        return PollingEdgeService('http://localhost', ['123'], repo, interval), repo

    def test_unexpected_json_shape_keeps_polling(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller, repo = self._poller_returning(http_class_mock, '{"error": "x"}')
            asyncio.run(poller.poll())  # must not raise
            try:
                self.assertIsNotNone(poller._worker)
            finally:
                poller.close()

    def test_failing_listener_keeps_polling(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller, repo = self._poller_returning(http_class_mock, '[{"features":[{"a":1}]}]')
            repo.notify.side_effect = RuntimeError("listener failed")
            asyncio.run(poller.poll())  # must not raise
            try:
                self.assertIsNotNone(poller._worker)
            finally:
                poller.close()

    def test_etag_not_kept_when_body_is_invalid(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller, repo = self._poller_returning(http_class_mock, 'not json', headers={'etag': '"abc"'}, interval=0)
            asyncio.run(poller.poll())
            self.assertIsNone(poller._etag)

    def test_update_interval_does_not_restart_after_invalid_key(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller, repo = self._poller_returning(http_class_mock, '', status=404)
            asyncio.run(poller.poll())
            self.assertTrue(poller.cancelled)
            poller.update_interval(60)
            self.assertTrue(poller.cancelled)
            self.assertIsNone(poller._worker)
            asyncio.run(poller.poll())  # nor does a later poll
            self.assertEqual(http_class_mock.return_value.request.call_count, 1)

    def test_only_one_request_in_flight_across_threads(self):
        active = 0
        peak = 0
        threads = set()
        lock = threading.Lock()

        def slow_request(**kwargs):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
                threads.add(threading.current_thread().name)
            time.sleep(0.05)
            with lock:
                active -= 1
            resp = MagicMock(name="http-response")
            resp.status = 200
            resp.headers = {}
            resp.data.decode.return_value = '[]'
            return resp

        with patch("urllib3.PoolManager") as http_class_mock:
            http_class_mock.return_value.request.side_effect = slow_request
            poller = PollingEdgeService('http://localhost', ['123'], MagicMock(spec=FeatureHubRepository), 30)
            callers = [threading.Thread(target=lambda: asyncio.run(poller.poll())) for _ in range(3)]
            callers += [threading.Thread(target=lambda i=i: asyncio.run(poller.context_change(f"userkey={i}")))
                        for i in range(3)]
            for c in callers:
                c.start()
            for c in callers:
                c.join(5)
            # restarting while a fetch may still be running must reuse the worker, not start a second one
            poller.close()
            poller.update_interval(30)
            asyncio.run(poller.poll())
            poller.close()

        self.assertEqual(peak, 1)
        self.assertEqual(threads, {"polling-featurehub"})

    def test_callers_wait_for_a_fetch_made_after_their_request(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller, repo = self._poller_returning(http_class_mock, '[]')
            asyncio.run(poller.poll())
            asyncio.run(poller.context_change("userkey=a"))
            try:
                # the context change was fetched with the new context before context_change returned
                headers = http_class_mock.return_value.request.call_args.kwargs['headers']
                self.assertEqual(headers['x-featurehub'], 'userkey=a')
                self.assertEqual(http_class_mock.return_value.request.call_count, 2)
            finally:
                poller.close()

    def test_stale_environment_stops_further_requests(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller, repo = self._poller_returning(http_class_mock, '[]', status=236)
            asyncio.run(poller.poll())
            self.assertTrue(poller.stopped)
            asyncio.run(poller.poll())
            asyncio.run(poller.context_change("userkey=a"))
            poller.update_interval(30)
            self.assertEqual(http_class_mock.return_value.request.call_count, 1)
            self.assertIsNone(poller._worker)

    def test_close_after_invalid_key_does_not_resume_polling(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller, repo = self._poller_returning(http_class_mock, '', status=404)
            asyncio.run(poller.poll())
            poller.close()
            asyncio.run(poller.poll())
            poller.update_interval(30)
            self.assertIsNone(poller._worker)
            self.assertEqual(http_class_mock.return_value.request.call_count, 1)

    def test_update_interval_starts_polling_when_it_was_zero(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller, repo = self._poller_returning(http_class_mock, '[]', interval=0)
            asyncio.run(poller.poll())
            worker = poller._worker
            if worker:
                worker.join(1)
            self.assertIsNone(poller._worker)
            poller.update_interval(30)
            try:
                self.assertIsNotNone(poller._worker)
            finally:
                poller.close()

    def test_update_interval_shortens_the_running_wait(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller, repo = self._poller_returning(http_class_mock, '[]', interval=60)
            asyncio.run(poller.poll())
            try:
                poller.update_interval(0.05)
                deadline = time.monotonic() + 2
                while http_class_mock.return_value.request.call_count < 2 and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertGreaterEqual(http_class_mock.return_value.request.call_count, 2)
            finally:
                poller.close()

    def test_close_wakes_waiting_callers(self):
        started = threading.Event()
        release = threading.Event()

        def hung_request(**kwargs):
            started.set()
            release.wait(5)
            raise urllib3.exceptions.ReadTimeoutError(None, 'http://localhost', 'timed out')

        with patch("urllib3.PoolManager") as http_class_mock:
            http_class_mock.return_value.request.side_effect = hung_request
            poller = PollingEdgeService('http://localhost', ['123'], MagicMock(spec=FeatureHubRepository), 30)
            caller = threading.Thread(target=lambda: asyncio.run(poller.poll()))
            caller.start()
            self.assertTrue(started.wait(1))
            poller.close()
            caller.join(1)
            self.assertFalse(caller.is_alive())
            release.set()

    def test_timeout_can_be_overridden(self):
        with patch.dict(os.environ, {"FEATUREHUB_POLLING_TIMEOUT": "3"}):
            with patch("urllib3.PoolManager") as http_class_mock:
                poller, repo = self._poller_returning(http_class_mock, '[]', interval=0)
                asyncio.run(poller.poll())
        self.assertEqual(http_class_mock.return_value.request.call_args.kwargs['timeout'], 3.0)

if __name__ == '__main__':
    unittest.main()