from unittest import TestCase
from unittest.mock import patch, MagicMock

from featurehub_sdk.featurehub_repository import FeatureHubRepository
from featurehub_sdk import polling_edge_service
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
        data_mock.decode.return_value = '[]'
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

            poller = PollingEdgeService('http://localhost/', ['123'], repo, 30)
            asyncio.run(poller.poll())
            self.assertEqual(poller.interval, 20)
            resp.headers = {'cache-control': 'private, max-age=16'}
            resp.status = 236
            asyncio.run(poller.poll())
            repo.mark_environment_stale.assert_called_once_with()
            http_mock.request.assert_called_with(method='GET', url='http://localhost/features?apiKey=123&contextSha=0&sdk_version=2',
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
            http_mock.request.assert_called_with(method='GET', url='http://localhost/features?apiKey=123&contextSha=03ac674216f3e15c761ee1a5e255f067953623c8b388b4459e13f978d7c846f4&sdk_version=2',
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
            repo.mark_environment_stale.assert_called_once_with()
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
            self.assertIsNone(poller._request._etag)

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
            poller.update_interval(30)
            self.assertEqual(http_class_mock.return_value.request.call_count, 1)
            self.assertIsNone(poller._worker)

    def test_context_change_does_not_fetch_when_stale(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller, repo = self._poller_returning(http_class_mock, '[]', status=236)
            asyncio.run(poller.poll())
            # the environment will never change, so nothing more is requested and the last features are kept
            asyncio.run(poller.context_change("userkey=a"))
            self.assertEqual(http_class_mock.return_value.request.call_count, 1)
            worker = poller._worker
            if worker:
                worker.join(1)
            self.assertIsNone(poller._worker)  # and it doesn't go back to polling

    def test_context_change_after_close_fetches(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller, repo = self._poller_returning(http_class_mock, '[]')
            asyncio.run(poller.poll())
            poller.close()
            asyncio.run(poller.context_change("userkey=a"))
            try:
                self.assertEqual(http_class_mock.return_value.request.call_count, 2)
            finally:
                poller.close()

    def test_context_change_with_invalid_key_reports_failure(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller, repo = self._poller_returning(http_class_mock, '', status=404)
            asyncio.run(poller.poll())
            repo.reset_mock()
            asyncio.run(poller.context_change("userkey=a"))
            repo.notify.assert_called_once_with("failed", None)
            self.assertEqual(http_class_mock.return_value.request.call_count, 1)

    def test_response_after_close_is_ignored(self):
        def request_then_close(**kwargs):
            poller.close()
            resp = MagicMock(name="http-response")
            resp.status = 200
            resp.headers = {'etag': '"abc"'}
            resp.data.decode.return_value = '[{"features":[{"a":1}]}]'
            return resp

        with patch("urllib3.PoolManager") as http_class_mock:
            http_class_mock.return_value.request.side_effect = request_then_close
            repo = MagicMock(spec=FeatureHubRepository)
            poller = PollingEdgeService('http://localhost', ['123'], repo, 30)
            asyncio.run(poller.poll())
            repo.notify.assert_not_called()
            self.assertIsNone(poller._request._etag)

    def test_unexpected_status_is_logged(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller, repo = self._poller_returning(http_class_mock, '', status=502, interval=0)
            with self.assertLogs('featurehub_sdk', level='ERROR') as logs:
                asyncio.run(poller.poll())
            self.assertIn("unexpected status 502", logs.output[0])

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
                with patch.object(polling_edge_service, '_MIN_POLLING_INTERVAL', 0):
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
        with patch.dict(os.environ, {"FEATUREHUB_POLLING_REQ_TIMEOUT": "3s"}):
            with patch("urllib3.PoolManager") as http_class_mock:
                poller, repo = self._poller_returning(http_class_mock, '[]', interval=0)
                asyncio.run(poller.poll())
        self.assertEqual(http_class_mock.return_value.request.call_args.kwargs['timeout'], 3.0)


class PollingProtocolTest(TestCase):
    def _poller(self, http_class_mock, status=200, body='[]', headers=None, interval=30, extra_headers=None):
        resp = MagicMock(name="http-response")
        resp.status = status
        resp.headers = headers or {}
        resp.data.decode.return_value = body
        http_class_mock.return_value.request.return_value = resp
        repo = MagicMock(spec=FeatureHubRepository)
        return PollingEdgeService('http://localhost/', ['123'], repo, interval, extra_headers), repo

    def test_every_4xx_stops_polling_for_good(self):
        for status in (400, 401, 403, 404, 429):
            with patch("urllib3.PoolManager") as http_class_mock:
                poller, repo = self._poller(http_class_mock, status=status)
                asyncio.run(poller.poll())
                repo.notify.assert_called_once_with('failed', None)
                self.assertTrue(poller.cancelled, status)
                asyncio.run(poller.poll())
                self.assertEqual(http_class_mock.return_value.request.call_count, 1, status)

    def test_5xx_keeps_polling(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller, repo = self._poller(http_class_mock, status=502)
            asyncio.run(poller.poll())
            try:
                repo.notify.assert_not_called()
                self.assertIsNotNone(poller._worker)
            finally:
                poller.close()

    def test_not_modified_is_not_an_error(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller, repo = self._poller(http_class_mock, status=304, interval=0)
            with self.assertNoLogs('featurehub_sdk', level='ERROR'):
                asyncio.run(poller.poll())
            repo.notify.assert_not_called()

    def test_max_age_does_not_start_polling_with_an_interval_of_zero(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller, repo = self._poller(http_class_mock, headers={'cache-control': 'max-age=20'}, interval=0)
            asyncio.run(poller.poll())
            worker = poller._worker
            if worker:
                worker.join(1)
            self.assertEqual(poller.interval, 0)
            self.assertIsNone(poller._worker)
            self.assertEqual(http_class_mock.return_value.request.call_count, 1)

    def test_max_age_below_the_minimum_is_raised_to_it(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller, repo = self._poller(http_class_mock, headers={'cache-control': 'max-age=1'})
            asyncio.run(poller.poll())
            try:
                self.assertEqual(poller.interval, 5)
            finally:
                poller.close()

    def test_max_age_is_ignored_on_other_responses(self):
        for status in (304, 429, 502, 503):
            with patch("urllib3.PoolManager") as http_class_mock:
                poller, repo = self._poller(http_class_mock, status=status, headers={'cache-control': 'max-age=60'})
                asyncio.run(poller.poll())
                try:
                    self.assertEqual(poller.interval, 30, status)
                finally:
                    poller.close()

    def test_interval_validation(self):
        repo = MagicMock(spec=FeatureHubRepository)
        for interval in (-1, 4, 0.001, 'ling'):
            with self.assertRaises(ValueError, msg=interval):
                PollingEdgeService('http://localhost/', ['123'], repo, interval)
        for interval in (0, 5):
            PollingEdgeService('http://localhost/', ['123'], repo, interval)
        poller = PollingEdgeService('http://localhost/', ['123'], repo, 0)
        with self.assertRaises(ValueError):
            poller.update_interval(4)
        self.assertEqual(poller.interval, 0)

    def test_extra_headers_are_sent_and_x_featurehub_wins(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller, repo = self._poller(http_class_mock, interval=0,
                                        extra_headers={'X-Gateway': 'omu&co', 'X-FeatureHub': 'userkey=kwong'})
            asyncio.run(poller.poll())
            headers = http_class_mock.return_value.request.call_args.kwargs['headers']
            self.assertEqual(headers['X-Gateway'], 'omu&co')
            self.assertEqual(headers['x-featurehub'], 'userkey=kwong')  # no context yet, so it is sent as given
            asyncio.run(poller.context_change('userkey=orm'))
            headers = http_class_mock.return_value.request.call_args.kwargs['headers']
            self.assertEqual(headers['X-Gateway'], 'omu&co')
            self.assertEqual(headers.getlist('x-featurehub'), ['userkey=orm'])

    # featurehub-protocol.yaml conformance query-parameter-order and sdk-version
    def test_query_parameters_are_in_a_fixed_order(self):
        with patch("urllib3.PoolManager"):
            poller = PollingEdgeService('http://chago/edge/?shop=omu&contextSha=1', ['ling', 'orm'], MagicMock(), 0)
        self.assertEqual(poller._request.url('abc'),
                         'http://chago/edge/features?shop=omu&apiKey=ling&apiKey=orm&contextSha=abc&sdk_version=2')

    def test_an_empty_context_sends_a_zero_sha(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller, repo = self._poller(http_class_mock, interval=0)
            asyncio.run(poller.context_change('userkey=lingling'))
            asyncio.run(poller.context_change(''))
            request = http_class_mock.return_value.request.call_args.kwargs
            self.assertTrue(request['url'].endswith('&contextSha=0&sdk_version=2'))
            self.assertNotIn('x-featurehub', request['headers'])

    def test_several_environments_are_one_full_set(self):
        body = ('[{"id":"lingling","features":[{"key":"ling"}]},'
                '{"id":"ormkorn","features":[{"key":"orm"}]}, {"id":"chago","features":[]}]')
        with patch("urllib3.PoolManager") as http_class_mock:
            poller, repo = self._poller(http_class_mock, body=body, interval=0)
            asyncio.run(poller.poll())
            repo.notify.assert_called_once_with('features', [{'key': 'ling'}, {'key': 'orm'}])

    def test_a_body_that_is_not_a_list_of_environments_changes_nothing(self):
        for body in ('{"features":[]}', '[{"features":{"key":"ling"}}]', '["kwong pastry"]'):
            with patch("urllib3.PoolManager") as http_class_mock:
                poller, repo = self._poller(http_class_mock, body=body, interval=0)
                with self.assertLogs('featurehub_sdk', level='ERROR'):
                    asyncio.run(poller.poll())
                repo.notify.assert_not_called()

    def test_etag_is_sent_again_after_a_304(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller, repo = self._poller(http_class_mock, headers={'etag': '"lingorm"'}, interval=0)
            asyncio.run(poller.poll())
            resp = http_class_mock.return_value.request.return_value
            resp.status = 304
            resp.headers = {}
            for _ in range(2):  # nothing changed, so the etag is still current
                asyncio.run(poller.poll())
                headers = http_class_mock.return_value.request.call_args.kwargs['headers']
                self.assertEqual(headers['if-none-match'], '"lingorm"')
            resp.status = 502  # nor does an error clear it
            asyncio.run(poller.poll())
            asyncio.run(poller.poll())
            self.assertEqual(http_class_mock.return_value.request.call_args.kwargs['headers']['if-none-match'],
                             '"lingorm"')
            repo.notify.assert_called_once_with('features', [])

    def test_context_change_clears_the_etag(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller, repo = self._poller(http_class_mock, headers={'etag': '"always-wonder"'}, interval=0)
            asyncio.run(poller.context_change('userkey=ling'))
            self.assertEqual(poller._request._etag, '"always-wonder"')
            http_class_mock.return_value.request.return_value.headers = {}
            asyncio.run(poller.context_change('userkey=orm'))
            headers = http_class_mock.return_value.request.call_args.kwargs['headers']
            self.assertNotIn('if-none-match', headers)
            self.assertEqual(headers['x-featurehub'], 'userkey=orm')

    def test_etag_from_a_previous_context_is_not_kept(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            def respond(**kwargs):
                poller._request._context = 'userkey=orm'  # the context changed while the request was in flight
                resp = MagicMock(name="http-response")
                resp.status = 200
                resp.headers = {'etag': '"keep-silent"'}
                resp.data.decode.return_value = '[]'
                return resp

            http_class_mock.return_value.request.side_effect = respond
            poller = PollingEdgeService('http://localhost/', ['123'], MagicMock(spec=FeatureHubRepository), 0)
            asyncio.run(poller.context_change('userkey=ling'))
            self.assertIsNone(poller._request._etag)

    def test_context_change_after_close_fetches_once_and_stays_closed(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller, repo = self._poller(http_class_mock, interval=30)
            asyncio.run(poller.poll())
            poller.close()
            asyncio.run(poller.context_change('userkey=kornaphat'))
            worker = poller._worker
            if worker:
                worker.join(1)
            self.assertEqual(http_class_mock.return_value.request.call_count, 2)
            self.assertIsNone(poller._worker)
            self.assertTrue(poller.cancelled)
            repo.notify.assert_called_with('features', [])
            # and it can still be started again as before
            poller.update_interval(30)
            try:
                self.assertIsNotNone(poller._worker)
            finally:
                poller.close()

    def test_update_interval_does_not_start_polling_that_was_never_started(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller, repo = self._poller(http_class_mock, interval=0)
            poller.update_interval(30)
            self.assertIsNone(poller._worker)
            poller.close()
            poller.update_interval(60)
            self.assertIsNone(poller._worker)
            http_class_mock.return_value.request.assert_not_called()

    def test_a_context_change_starts_polling(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller, repo = self._poller(http_class_mock, interval=30)
            asyncio.run(poller.context_change('userkey=sirilak'))
            try:
                self.assertIsNotNone(poller._worker)
            finally:
                poller.close()


class PassivePollingTest(TestCase):
    def _poller(self, http_class_mock, interval=30, status=200):
        resp = MagicMock(name="http-response")
        resp.status = status
        resp.headers = {}
        resp.data.decode.return_value = '[{"id":"ling","features":[]}]'
        http_class_mock.return_value.request.return_value = resp
        return PollingEdgeService('http://localhost/', ['123'], MagicMock(spec=FeatureHubRepository), interval,
                                  passive=True)

    def _requests(self, http_class_mock):
        return http_class_mock.return_value.request.call_count

    def _settle(self, poller):
        worker = poller._worker
        if worker:
            worker.join(2)

    def test_first_poll_fetches_and_nothing_is_scheduled(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller = self._poller(http_class_mock)
            asyncio.run(poller.poll())
            self._settle(poller)
            self.assertEqual(self._requests(http_class_mock), 1)
            self.assertIsNone(poller._worker)  # no timer: the worker stops once the fetch is done
            self.assertTrue(poller.passive)

    def test_fresh_features_are_not_fetched_again(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller = self._poller(http_class_mock)
            asyncio.run(poller.poll())
            asyncio.run(poller.poll())
            poller.refresh_if_stale()
            self._settle(poller)
            self.assertEqual(self._requests(http_class_mock), 1)

    def test_features_older_than_the_interval_are_fetched_when_read(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller = self._poller(http_class_mock)
            asyncio.run(poller.poll())
            self._settle(poller)
            poller._last_fetch -= 31  # the last fetch was longer ago than the interval
            poller.refresh_if_stale()  # doesn't wait for it
            self._settle(poller)
            self.assertEqual(self._requests(http_class_mock), 2)
            poller.refresh_if_stale()  # and the features are fresh again
            self._settle(poller)
            self.assertEqual(self._requests(http_class_mock), 2)

    def test_a_poll_with_stale_features_waits_for_the_fetch(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller = self._poller(http_class_mock)
            asyncio.run(poller.poll())
            self._settle(poller)
            poller._last_fetch -= 31
            asyncio.run(poller.poll())
            self.assertEqual(self._requests(http_class_mock), 2)

    def test_a_failed_fetch_is_not_retried_before_the_interval(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller = self._poller(http_class_mock, status=503)
            asyncio.run(poller.poll())
            self._settle(poller)
            poller.refresh_if_stale()
            self._settle(poller)
            self.assertEqual(self._requests(http_class_mock), 1)

    def test_an_interval_of_zero_fetches_once(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller = self._poller(http_class_mock, interval=0)
            asyncio.run(poller.poll())
            self._settle(poller)
            poller._last_fetch -= 3600
            poller.refresh_if_stale()
            asyncio.run(poller.poll())
            self._settle(poller)
            self.assertEqual(self._requests(http_class_mock), 1)

    def test_nothing_is_fetched_before_it_is_started(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller = self._poller(http_class_mock)
            poller.refresh_if_stale()
            poller.update_interval(60)
            self._settle(poller)
            self.assertEqual(self._requests(http_class_mock), 0)

    def test_a_context_change_always_fetches(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller = self._poller(http_class_mock)
            asyncio.run(poller.poll())
            asyncio.run(poller.context_change('userkey=orm'))
            self.assertEqual(self._requests(http_class_mock), 2)
            self.assertEqual(http_class_mock.return_value.request.call_args.kwargs['headers']['x-featurehub'],
                             'userkey=orm')

    def test_update_interval_does_not_start_a_timer(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller = self._poller(http_class_mock)
            asyncio.run(poller.poll())
            self._settle(poller)
            poller.update_interval(5)
            self.assertIsNone(poller._worker)
            self.assertEqual(poller.interval, 5)

    def test_closed_passive_polling_fetches_nothing_when_read(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller = self._poller(http_class_mock)
            asyncio.run(poller.poll())
            self._settle(poller)
            poller.close()
            poller._last_fetch -= 31
            poller.refresh_if_stale()
            self._settle(poller)
            self.assertEqual(self._requests(http_class_mock), 1)

    def test_active_polling_ignores_refresh_if_stale(self):
        with patch("urllib3.PoolManager") as http_class_mock:
            poller = PollingEdgeService('http://localhost/', ['123'], MagicMock(spec=FeatureHubRepository), 0)
            asyncio.run(poller.poll())
            self._settle(poller)
            poller.refresh_if_stale()
            self._settle(poller)
            self.assertEqual(self._requests(http_class_mock), 1)


if __name__ == '__main__':
    unittest.main()