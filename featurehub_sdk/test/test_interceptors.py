
import unittest
import os
from unittest import TestCase
from unittest.mock import MagicMock, patch

from featurehub_sdk.interceptors import EnvironmentInterceptor


class InterceptorTests(TestCase):
    def test_environment(self):
        with patch.dict(os.environ, {"FEATUREHUB_OVERRIDE_FEATURES": "true", "FEATUREHUB_FAFF": "true"}):
            self.assertEqual(EnvironmentInterceptor().intercepted_value("FAFF").cast("BOOLEAN"), True)


if __name__ == '__main__':
    unittest.main()
