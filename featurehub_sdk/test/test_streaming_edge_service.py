import os
from unittest import TestCase
from unittest.mock import MagicMock, patch, call as unittest_call

import asyncio
import threading
import urllib3

from featurehub_sdk.streaming_edge_service import _StreamingThread, StreamingEdgeClient


def _thread() -> _StreamingThread:
    return _StreamingThread("http://localhost/", ["key"], MagicMock())


class StreamingRetryDelayTest(TestCase):
    def test_defaults_when_env_not_set(self):
        with patch.dict(os.environ, {}, clear=True):
            thread = _thread()
        self.assertEqual(thread._initial_retry_delay, _StreamingThread.INITIAL_RETRY_DELAY)
        self.assertEqual(thread._max_retry_delay, _StreamingThread.MAX_RETRY_DELAY)

    def test_env_overrides(self):
        with patch.dict(os.environ, {"FEATUREHUB_SSE_INITIAL_RETRY_DELAY": "0.5s",
                                     "FEATUREHUB_SSE_MAX_RETRY_DELAY": "120s"}, clear=True):
            thread = _thread()
        self.assertEqual(thread._initial_retry_delay, 0.5)
        self.assertEqual(thread._max_retry_delay, 120.0)

    def test_go_durations_are_accepted(self):
        with patch.dict(os.environ, {"FEATUREHUB_SSE_INITIAL_RETRY_DELAY": "500ms",
                                     "FEATUREHUB_SSE_MAX_RETRY_DELAY": "2m",
                                     "FEATUREHUB_SSE_READ_TIMEOUT": "1m30s"}, clear=True):
            thread = _thread()
        self.assertEqual(thread._initial_retry_delay, 0.5)
        self.assertEqual(thread._max_retry_delay, 120.0)
        self.assertEqual(thread._timeout.read_timeout, 90.0)

    def test_durations_without_a_unit_are_invalid(self):
        with patch.dict(os.environ, {"FEATUREHUB_SSE_INITIAL_RETRY_DELAY": "2",
                                     "FEATUREHUB_SSE_READ_TIMEOUT": "90"}, clear=True):
            with self.assertLogs('featurehub_sdk', level='WARNING'):
                thread = _thread()
        self.assertEqual(thread._initial_retry_delay, _StreamingThread.INITIAL_RETRY_DELAY)
        self.assertEqual(thread._timeout.read_timeout, _StreamingThread.READ_TIMEOUT)

    def test_invalid_env_values_fall_back_to_defaults(self):
        with patch.dict(os.environ, {"FEATUREHUB_SSE_INITIAL_RETRY_DELAY": "soon",
                                     "FEATUREHUB_SSE_MAX_RETRY_DELAY": "-5"}, clear=True):
            thread = _thread()
        self.assertEqual(thread._initial_retry_delay, _StreamingThread.INITIAL_RETRY_DELAY)
        self.assertEqual(thread._max_retry_delay, _StreamingThread.MAX_RETRY_DELAY)

    def test_infinite_or_huge_values_are_ignored_or_capped(self):
        with patch.dict(os.environ, {"FEATUREHUB_SSE_INITIAL_RETRY_DELAY": "inf",
                                     "FEATUREHUB_SSE_MAX_RETRY_DELAY": "100000000000h"}, clear=True):
            thread = _thread()
        self.assertEqual(thread._initial_retry_delay, _StreamingThread.INITIAL_RETRY_DELAY)
        self.assertEqual(thread._max_retry_delay, threading.TIMEOUT_MAX)

    def test_max_is_never_below_initial(self):
        with patch.dict(os.environ, {"FEATUREHUB_SSE_INITIAL_RETRY_DELAY": "60s",
                                     "FEATUREHUB_SSE_MAX_RETRY_DELAY": "10s"}, clear=True):
            thread = _thread()
        self.assertEqual(thread._initial_retry_delay, 60.0)
        self.assertEqual(thread._max_retry_delay, 60.0)


def _sse_response(body: bytes):
    resp = MagicMock(name="sse-response")
    resp.status = 200
    resp.headers = urllib3.HTTPHeaderDict({'Content-Type': 'text/event-stream; charset=utf-8'})
    resp.__iter__.return_value = iter([body] if body else [])
    return resp


def _status_response(status: int, content_type: str = 'text/plain'):
    resp = MagicMock(name=f"status-{status}")
    resp.status = status
    resp.headers = urllib3.HTTPHeaderDict({'Content-Type': content_type})
    return resp


def _non_bye_calls(repo):
    return [c for c in repo.notify.call_args_list if c.args[0] != 'bye']


def _run_until_waits(thread: _StreamingThread, responses, waits: int):
    """runs the streaming loop synchronously, recording each reconnect delay and cancelling after `waits` of them"""
    thread._http = MagicMock()
    thread._http.request.side_effect = responses
    delays = []

    def wait(delay):
        delays.append(delay)
        if len(delays) >= waits:
            thread.cancel()

    thread._wakeup = MagicMock()
    thread._wakeup.wait.side_effect = wait
    thread.run()
    return delays


class StreamingReconnectTest(TestCase):
    def test_stream_that_closes_immediately_keeps_backing_off(self):
        with patch.dict(os.environ, {}, clear=True):
            thread = _thread()
        delays = _run_until_waits(thread, [_sse_response(b"") for _ in range(3)], 3)
        self.assertEqual(delays, [1.0, 2.0, 4.0])

    def test_bad_events_do_not_stop_the_stream(self):
        def notify(status, data):
            if status == 'features':
                raise RuntimeError("listener failed")

        repo = MagicMock()
        repo.notify.side_effect = notify
        with patch.dict(os.environ, {}, clear=True):
            thread = _StreamingThread("http://localhost/", ["key"], repo)
        body = (b"event: config\ndata: {}\n\n"
                b"event: features\ndata: [{\"id\":\"1\"}]\n\n"
                b"event: feature\ndata: {\"id\":\"2\"}\n\n")
        delays = _run_until_waits(thread, [_sse_response(b""), _sse_response(body)], 2)
        self.assertFalse(thread.stopped)
        self.assertEqual(len(_non_bye_calls(repo)), 2)
        # the second stream delivered the features, so the delay was reset rather than grown to 2
        self.assertEqual(delays, [1.0, 1.0])

    def test_unexpected_exception_does_not_kill_thread(self):
        with patch.dict(os.environ, {}, clear=True):
            thread = _thread()
        delays = _run_until_waits(thread, [RuntimeError("boom"), RuntimeError("boom")], 2)
        self.assertEqual(delays, [1.0, 2.0])

    def test_bye_and_error_do_not_reset_the_delay(self):
        with patch.dict(os.environ, {}, clear=True):
            thread = _thread()
        body = b"event: error\ndata: {}\n\nevent: bye\ndata: {}\n\n"
        delays = _run_until_waits(thread, [_sse_response(body) for _ in range(3)], 3)
        self.assertEqual(delays, [1.0, 2.0, 4.0])

    def test_responses_are_released(self):
        with patch.dict(os.environ, {}, clear=True):
            thread = _thread()
        failed = MagicMock(name="failed-response")
        failed.status = 500
        streamed = _sse_response(b"event: features\ndata: []\n\n")
        _run_until_waits(thread, [failed, streamed], 2)
        for resp in (failed, streamed):
            resp.close.assert_called()
            resp.release_conn.assert_called()

    def test_invalid_key_stops_for_good(self):
        not_found = MagicMock(name="not-found")
        not_found.status = 404
        with patch.dict(os.environ, {}, clear=True):
            thread = _thread()
        thread._http = MagicMock()
        thread._http.request.return_value = not_found
        thread.run()
        self.assertTrue(thread.invalid_key)
        thread._repository.notify.assert_called_once_with("failed", None)

    def test_stale_environment_stops_reading_the_stream(self):
        repo = MagicMock()
        with patch.dict(os.environ, {}, clear=True):
            thread = _StreamingThread("http://localhost/", ["key"], repo)
        body = (b"event: config\ndata: {\"edge.stale\": true}\n\n"
                b"event: features\ndata: []\n\n")
        thread._http = MagicMock()
        thread._http.request.return_value = _sse_response(body)
        thread.run()
        self.assertTrue(thread.stopped)
        repo.notify.assert_not_called()
        repo.mark_environment_stale.assert_called_once_with()

    def test_requests_use_timeouts(self):
        with patch.dict(os.environ, {"FEATUREHUB_SSE_READ_TIMEOUT": "90s"}, clear=True):
            thread = _thread()
        _run_until_waits(thread, [_sse_response(b"")], 1)
        timeout = thread._http.request.call_args.kwargs['timeout']
        self.assertEqual(timeout.connect_timeout, _StreamingThread.CONNECT_TIMEOUT)
        self.assertEqual(timeout.read_timeout, 90.0)

    def test_closed_while_connecting_does_not_read_the_stream(self):
        repo = MagicMock()
        with patch.dict(os.environ, {}, clear=True):
            thread = _StreamingThread("http://localhost/", ["key"], repo)
        resp = _sse_response(b"event: features\ndata: []\n\n")

        def connect(*args, **kwargs):
            thread.close()
            return resp

        thread._http = MagicMock()
        thread._http.request.side_effect = connect
        thread.run()
        repo.notify.assert_not_called()
        resp.release_conn.assert_called()

    def test_no_events_are_applied_once_closed(self):
        repo = MagicMock()
        with patch.dict(os.environ, {}, clear=True):
            thread = _StreamingThread("http://localhost/", ["key"], repo)

        def chunks():
            yield b"event: features\ndata: []\n\n"
            thread._cancel = True  # closed while the next event was being read
            yield b"event: feature\ndata: {\"id\":\"1\"}\n\n"

        resp = _sse_response(b"")
        resp.__iter__.return_value = chunks()
        thread._http = MagicMock()
        thread._http.request.return_value = resp
        thread.run()
        self.assertEqual(repo.notify.call_count, 1)

    def test_close_does_not_close_a_finished_connection(self):
        with patch.dict(os.environ, {}, clear=True):
            thread = _thread()
        _run_until_waits(thread, [_sse_response(b"event: features\ndata: []\n\n")], 1)
        self.assertIsNone(thread._client)


class StreamingEdgeClientTest(TestCase):
    def _client(self):
        client = StreamingEdgeClient("http://localhost/", ["key*ormkorn"], MagicMock())
        return client

    def test_poll_after_close_starts_a_new_thread(self):
        client = self._client()
        with patch.object(_StreamingThread, "run"):
            asyncio.run(client.poll())
            first = client._streaming_thread
            first.join(1)
            client.close()
            asyncio.run(client.poll())  # must not raise RuntimeError for starting a thread twice
            self.assertIsNot(client._streaming_thread, first)
            client._streaming_thread.join(1)

    def test_poll_while_closed_thread_is_still_exiting_starts_a_new_thread(self):
        client = self._client()
        release = threading.Event()
        with patch.object(_StreamingThread, "run", lambda t: release.wait(5)):
            asyncio.run(client.poll())
            first = client._streaming_thread
            client.close()
            asyncio.run(client.poll())  # the closed thread hasn't exited yet
            try:
                self.assertIsNot(client._streaming_thread, first)
                self.assertTrue(client._streaming_thread.is_alive())
            finally:
                release.set()

    def test_poll_does_not_restart_after_invalid_key_or_stale(self):
        for flag in ("_failed", "_stopped"):
            client = self._client()
            with patch.object(_StreamingThread, "run"):
                asyncio.run(client.poll())
                first = client._streaming_thread
                first.join(1)
                setattr(first, flag, True)
                asyncio.run(client.poll())
                self.assertIs(client._streaming_thread, first)

    def test_server_evaluated_key_is_rejected(self):
        # the context isn't sent over streaming, so FeatureHub would evaluate without it
        with self.assertRaises(ValueError):
            StreamingEdgeClient("http://localhost/", ["kornaphat-server-key"], MagicMock())

    def test_headers_are_passed_to_new_threads(self):
        client = StreamingEdgeClient("http://localhost/", ["key*ormkorn"], MagicMock(), {"X-Chago": "orm"})
        self.assertEqual(client._streaming_thread._headers, {"X-Chago": "orm"})
        with patch.object(_StreamingThread, "run"):
            asyncio.run(client.poll())
            client._streaming_thread.join(1)
            client.close()
            asyncio.run(client.poll())
            client._streaming_thread.join(1)
        self.assertEqual(client._streaming_thread._headers, {"X-Chago": "orm"})


class StreamingProtocolTest(TestCase):
    def test_every_4xx_stops_for_good(self):
        for status in (400, 401, 403, 429):
            with patch.dict(os.environ, {}, clear=True):
                thread = _thread()
            thread._http = MagicMock()
            thread._http.request.return_value = _status_response(status)
            thread.run()
            self.assertTrue(thread.failed, status)
            self.assertEqual(thread._http.request.call_count, 1, status)
            thread._repository.notify.assert_called_once_with("failed", None)

    def test_5xx_1xx_and_3xx_are_retried_with_bye(self):
        repo = MagicMock()
        with patch.dict(os.environ, {}, clear=True):
            thread = _StreamingThread("http://localhost/", ["key"], repo)
        delays = _run_until_waits(thread, [_status_response(503), _status_response(101), _status_response(302)], 3)
        self.assertEqual(delays, [1.0, 2.0, 4.0])
        self.assertFalse(thread.failed)
        self.assertEqual(repo.notify.call_args_list, [unittest_call("bye", None)] * 3)

    def test_failure_event_stops_for_good(self):
        repo = MagicMock()
        with patch.dict(os.environ, {}, clear=True):
            thread = _StreamingThread("http://localhost/", ["key"], repo)
        body = (b"event: features\ndata: []\n\n"
                b"event: failure\ndata: {}\n\n"
                b"event: feature\ndata: {\"id\":\"1\"}\n\n")
        thread._http = MagicMock()
        thread._http.request.return_value = _sse_response(body)
        thread.run()
        self.assertTrue(thread.failed)
        self.assertEqual(thread._http.request.call_count, 1)
        self.assertEqual(repo.notify.call_args_list, [unittest_call("features", []), unittest_call("failed", None)])

    def test_any_edge_stale_value_means_stale(self):
        for value in (b"true", b"false", b"null", b"\"always wonder\""):
            repo = MagicMock()
            with patch.dict(os.environ, {}, clear=True):
                thread = _StreamingThread("http://localhost/", ["key"], repo)
            thread._http = MagicMock()
            thread._http.request.return_value = _sse_response(b"event: config\ndata: {\"edge.stale\": " + value + b"}\n\n")
            thread.run()
            self.assertTrue(thread.stopped, value)
            repo.mark_environment_stale.assert_called_once_with()
            self.assertEqual(thread._http.request.call_count, 1)

    def test_a_response_that_is_not_an_event_stream_is_a_failed_connection(self):
        repo = MagicMock()
        with patch.dict(os.environ, {}, clear=True):
            thread = _StreamingThread("http://localhost/", ["key"], repo)
        html = _status_response(200, 'text/html')
        html.__iter__.return_value = iter([b"event: features\ndata: []\n\n"])
        delays = _run_until_waits(thread, [html, _status_response(200, 'text/html')], 2)
        self.assertEqual(delays, [1.0, 2.0])
        self.assertEqual(repo.notify.call_args_list, [unittest_call("bye", None)] * 2)

    def test_closed_just_after_connecting_does_not_read_the_stream(self):
        repo = MagicMock()
        with patch.dict(os.environ, {}, clear=True):
            thread = _StreamingThread("http://localhost/", ["ling*kwong"], repo)
        resp = _sse_response(b"event: features\ndata: []\n\n")
        thread._http = MagicMock()
        thread._http.request.return_value = resp

        def client(r):
            thread.close()  # close() lands before the client is stored, so it has nothing to close
            return MagicMock(name="sse-client")

        with patch("featurehub_sdk.streaming_edge_service.sseclient.SSEClient", side_effect=client) as sse:
            thread.run()
        sse.return_value.events.assert_not_called()
        repo.notify.assert_not_called()
        resp.release_conn.assert_called()

    def test_every_featurehub_event_resets_the_delay(self):
        for event in (b"ack", b"features", b"feature", b"delete_feature", b"deleteFeature", b"config"):
            with patch.dict(os.environ, {}, clear=True):
                thread = _thread()
            body = b"event: " + event + b"\ndata: {}\n\n"
            delays = _run_until_waits(thread, [_sse_response(b""), _sse_response(body), _sse_response(b"")], 3)
            self.assertEqual(delays, [1.0, 1.0, 2.0], event)

    def test_extra_headers_are_sent_and_the_sdk_headers_win(self):
        with patch.dict(os.environ, {}, clear=True):
            thread = _StreamingThread("http://localhost/", ["key"], MagicMock(),
                                      {"X-Chago": "lingling kwong", "accept": "text/html"})
        _run_until_waits(thread, [_sse_response(b"id: 7\nevent: features\ndata: []\n\n"), _sse_response(b"")], 2)
        for request in thread._http.request.call_args_list:
            headers = request.kwargs['headers']
            self.assertEqual(headers['X-Chago'], 'lingling kwong')
            self.assertEqual(headers['Accept'], 'text/event-stream')
            self.assertEqual(len(headers.getlist('accept')), 1)
        self.assertEqual(thread._http.request.call_args.kwargs['headers']['Last-Event-Id'], '7')


class StreamingBackoffTest(TestCase):
    def test_multiplier_can_be_configured(self):
        with patch.dict(os.environ, {"FEATUREHUB_SSE_BACKOFF_MULTIPLIER": "3"}, clear=True):
            thread = _thread()
        delays = _run_until_waits(thread, [_sse_response(b"") for _ in range(4)], 4)
        self.assertEqual(delays, [1.0, 3.0, 9.0, 27.0])

    def test_waits_never_exceed_the_maximum(self):
        with patch.dict(os.environ, {"FEATUREHUB_SSE_MAX_RETRY_DELAY": "5s"}, clear=True):
            thread = _thread()
        delays = _run_until_waits(thread, [_sse_response(b"") for _ in range(5)], 5)
        self.assertEqual(delays, [1.0, 2.0, 4.0, 5.0, 5.0])

    def test_multiplier_below_one_is_ignored(self):
        with patch.dict(os.environ, {"FEATUREHUB_SSE_BACKOFF_MULTIPLIER": "0.5"}, clear=True):
            thread = _thread()
        self.assertEqual(thread._backoff_multiplier, _StreamingThread.BACKOFF_MULTIPLIER)

    def test_delay_is_never_below_100ms(self):
        with patch.dict(os.environ, {"FEATUREHUB_SSE_INITIAL_RETRY_DELAY": "1ms",
                                     "FEATUREHUB_SSE_MAX_RETRY_DELAY": "1ms"}, clear=True):
            thread = _thread()
        self.assertEqual(thread._initial_retry_delay, 0.1)
        self.assertEqual(thread._max_retry_delay, 0.1)
