
import unittest
import asyncio

from unittest import TestCase
from unittest.mock import MagicMock

from featurehub_sdk.client_context import ClientEvalFeatureContext

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


class ClientEvalFeatureContextTest(TestCase):

    def setUp(self) -> None:
        self.mock_repo = MagicMock()
        self.mock_feature = MagicMock()
        self.mock_edge = MagicMock()
        self.mock_repo.feature.return_value = self.mock_feature
        self.client_context = ClientEvalFeatureContext(self.mock_repo, self.mock_edge)

    @sync
    async def test_build_waits_for_edge_poll(self):
        await self.client_context.build()

        self.mock_edge.poll.assert_called_once_with()

    @sync
    async def test_close_will_close_edge(self):
        await self.client_context.close()

        self.mock_edge.close.assert_called_once_with()

    def test_requests_feature_with_context(self):
        self.client_context.feature('X')

        self.mock_feature.with_context.assert_called_with(self.client_context)


if __name__ == '__main__':
    unittest.main()