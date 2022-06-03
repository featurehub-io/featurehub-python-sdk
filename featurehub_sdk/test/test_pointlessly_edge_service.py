import unittest
from unittest import TestCase

from featurehub_sdk.edge_service import EdgeService


class EdgeServiceTest(TestCase):
    def setUp(self) -> None:
        self.edge = EdgeService()

    # all methods are pass as it is an interface, but hey, complaints of non close to 100%
    async def test_pointelessly(self):
        await self.edge.close()
        await self.edge.poll()
        self.edge.client_evaluated()
        await self.edge.context_change(header='sausage')


if __name__ == '__main__':
    unittest.main()
