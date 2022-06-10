
import unittest
import asyncio

from unittest import TestCase
from unittest.mock import MagicMock

from featurehub_sdk.client_context import ServerEvalFeatureContext

# cannot figure out how to reuse this

# we need this so we can do async testing (Stack Overflow)
def sync(coro):
    def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(coro(*args, **kwargs))
    return wrapper

# monkey patch MagicMock to support async (Stack Overflow)
async def async_magic():
    pass

MagicMock.__await__ = lambda x: async_magic().__await__()


class ServerEvalFeatureContextTest(TestCase):

    def setUp(self) -> None:
        self.mock_repo = MagicMock()
        self.mock_feature = MagicMock()
        self.mock_edge = MagicMock()
        self.mock_repo.feature.return_value = self.mock_feature
        self.client_context = ServerEvalFeatureContext(self.mock_repo, self.mock_edge)

    def test_build_waits_for_edge_poll_when_no_attrs(self):
        asyncio.run(self.client_context.build())

        self.mock_edge.poll.assert_called_once_with()

    def test_sync_build_works(self):
        self.client_context.build_sync()
        self.mock_edge.poll.assert_called_once_with()

    def test_encodes_attributes_and_changes_headers_when_attrs(self):
        asyncio.run(self.client_context.user_key('fred').attribute_values('piffle', ['a+', 'b', 'c']).build())

        self.mock_repo.not_ready.assert_called_once()
        self.mock_edge.context_change.assert_called_once_with('userkey=fred&piffle=a%2B')

    def test_requests_feature_do_not_use_with_context(self):
        self.client_context.feature('X')

        self.mock_feature.with_context.assert_not_called()


if __name__ == '__main__':
    unittest.main()