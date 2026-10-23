import os
from unittest import TestCase
from unittest.mock import MagicMock, patch

import asyncio
import threading

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
        with patch.dict(os.environ, {"FEATUREHUB_STREAMING_INITIAL_RETRY_DELAY": "0.5",
                                     "FEATUREHUB_STREAMING_MAX_RETRY_DELAY": "120"}, clear=True):
            thread = _thread()
        self.assertEqual(thread._initial_retry_delay, 0.5)
        self.assertEqual(thread._max_retry_delay, 120.0)

    def test_invalid_env_values_fall_back_to_defaults(self):
        with patch.dict(os.environ, {"FEATUREHUB_STREAMING_INITIAL_RETRY_DELAY": "soon",
                                     "FEATUREHUB_STREAMING_MAX_RETRY_DELAY": "-5"}, clear=True):
            thread = _thread()
        self.assertEqual(thread._initial_retry_delay, _StreamingThread.INITIAL_RETRY_DELAY)
        self.assertEqual(thread._max_retry_delay, _StreamingThread.MAX_RETRY_DELAY)

    def test_infinite_or_huge_values_are_ignored_or_capped(self):
        with patch.dict(os.environ, {"FEATUREHUB_STREAMING_INITIAL_RETRY_DELAY": "inf",
                                     "FEATUREHUB_STREAMING_MAX_RETRY_DELAY": "1e300"}, clear=True):
            thread = _thread()
        self.assertEqual(thread._initial_retry_delay, _StreamingThread.INITIAL_RETRY_DELAY)
        self.assertEqual(thread._max_retry_delay, threading.TIMEOUT_MAX)

    def test_max_is_never_below_initial(self):
        with patch.dict(os.environ, {"FEATUREHUB_STREAMING_INITIAL_RETRY_DELAY": "60",
                                     "FEATUREHUB_STREAMING_MAX_RETRY_DELAY": "10"}, clear=True):
            thread = _thread()
        self.assertEqual(thread._initial_retry_delay, 60.0)
        self.assertEqual(thread._max_retry_delay, 60.0)


def _sse_response(body: bytes):
    resp = MagicMock(name="sse-response")
    resp.status = 200
    resp.__iter__.return_value = iter([body] if body else [])
    return resp


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
        repo = MagicMock()
        repo.notify.side_effect = [RuntimeError("listener failed"), None]
        with patch.dict(os.environ, {}, clear=True):
            thread = _StreamingThread("http://localhost/", ["key"], repo)
        body = (b"event: config\ndata: {}\n\n"
                b"event: features\ndata: [{\"id\":\"1\"}]\n\n"
                b"event: feature\ndata: {\"id\":\"2\"}\n\n")
        delays = _run_until_waits(thread, [_sse_response(b""), _sse_response(body)], 2)
        self.assertFalse(thread.stopped)
        self.assertEqual(repo.notify.call_count, 2)
        # the second stream delivered the features, so the delay was reset rather than grown to 2
        self.assertEqual(delays, [1.0, 1.0])

    def test_unexpected_exception_does_not_kill_thread(self):
        with patch.dict(os.environ, {}, clear=True):
            thread = _thread()
        delays = _run_until_waits(thread, [RuntimeError("boom"), RuntimeError("boom")], 2)
        self.assertEqual(delays, [1.0, 2.0])

    def test_events_other_than_features_do_not_reset_the_delay(self):
        with patch.dict(os.environ, {}, clear=True):
            thread = _thread()
        body = b"event: config\ndata: {}\n\n"
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

    def test_requests_use_timeouts(self):
        with patch.dict(os.environ, {"FEATUREHUB_STREAMING_READ_TIMEOUT": "90"}, clear=True):
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

        resp = MagicMock(name="sse-response")
        resp.status = 200
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
        client = StreamingEdgeClient("http://localhost/", ["key"], MagicMock())
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
        for flag in ("_invalid_key", "_stopped"):
            client = self._client()
            with patch.object(_StreamingThread, "run"):
                asyncio.run(client.poll())
                first = client._streaming_thread
                first.join(1)
                setattr(first, flag, True)
                asyncio.run(client.poll())
                self.assertIs(client._streaming_thread, first)
