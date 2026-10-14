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
