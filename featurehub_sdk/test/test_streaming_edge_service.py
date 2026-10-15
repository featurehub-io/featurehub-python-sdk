import os
from unittest import TestCase
from unittest.mock import MagicMock, patch

from featurehub_sdk.streaming_edge_service import _StreamingThread


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
                b"event: feature\ndata: {\"id\":\"1\"}\n\n"
                b"event: feature\ndata: {\"id\":\"2\"}\n\n")
        delays = _run_until_waits(thread, [_sse_response(b""), _sse_response(body)], 2)
        self.assertFalse(thread.stopped)
        self.assertEqual(repo.notify.call_count, 2)
        # the second stream delivered events, so the delay was reset rather than grown to 2
        self.assertEqual(delays, [1.0, 1.0])

    def test_unexpected_exception_does_not_kill_thread(self):
        with patch.dict(os.environ, {}, clear=True):
            thread = _thread()
        delays = _run_until_waits(thread, [RuntimeError("boom"), RuntimeError("boom")], 2)
        self.assertEqual(delays, [1.0, 2.0])
