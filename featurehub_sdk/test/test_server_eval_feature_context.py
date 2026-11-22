
import unittest
import asyncio

from unittest import TestCase
from unittest.mock import MagicMock

from datetime import datetime, timezone, timedelta, date
from decimal import Decimal

from featurehub_sdk.client_context import ServerEvalFeatureContext, x_featurehub_header, wire_value
from featurehub_sdk.strategy_attribute_country_name import StrategyAttributeCountryName
from featurehub_sdk.strategy_attribute_platform_name import StrategyAttributePlatformName

# cannot figure out how to reuse this

# we need this so we can do async testing (Stack Overflow)
def sync(coro):
    def wrapper(*args, **kwargs):
        asyncio.run(coro(*args, **kwargs))
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
        self.mock_edge.context_change.assert_called_once_with('piffle=a%2B%2Cb%2Cc,userkey=fred')

    def test_requests_feature_do_not_use_with_context(self):
        self.client_context.feature('X')

        self.mock_feature.with_context.assert_not_called()


class XFeatureHubHeaderTest(TestCase):
    def test_attributes_are_sorted_and_joined_by_commas(self):
        self.assertEqual(x_featurehub_header({'userkey': ['lingling'], 'country': ['thailand']}),
                         'country=thailand,userkey=lingling')

    def test_keys_are_encoded_too(self):
        self.assertEqual(x_featurehub_header({'always wonder': ['orm'], 'ling,orm=1': ['kwong']}),
                         'always%20wonder=orm,ling%2Corm%3D1=kwong')

    def test_no_attributes_is_no_header(self):
        self.assertEqual(x_featurehub_header({}), '')
        self.assertEqual(x_featurehub_header({'orm': None, 'ling': []}), '')

    def test_values_are_encoded_as_a_uri_component(self):
        self.assertEqual(x_featurehub_header({'shop': ["omu&co", "kwong pastry", "(chago)!*'~"]}),
                         "shop=omu%26co%2Ckwong%20pastry%2C(chago)!*'~")
        self.assertEqual(x_featurehub_header({'name': ['หลิงหลิง', '鄺玲玲']}),
                         'name=%E0%B8%AB%E0%B8%A5%E0%B8%B4%E0%B8%87%E0%B8%AB%E0%B8%A5%E0%B8%B4%E0%B8%87%2C'
                         '%E9%84%BA%E7%8E%B2%E7%8E%B2')

    def test_wire_values(self):
        self.assertEqual(wire_value(True), 'true')
        self.assertEqual(wire_value(False), 'false')
        self.assertEqual(wire_value(3.0), '3')
        self.assertEqual(wire_value(3.5), '3.5')
        self.assertEqual(wire_value(7), '7')
        self.assertEqual(wire_value(float('nan')), 'NaN')
        self.assertEqual(wire_value(float('inf')), 'Infinity')
        self.assertEqual(wire_value(Decimal('4.00')), '4')
        self.assertEqual(wire_value(Decimal('4.25')), '4.25')
        self.assertEqual(wire_value('kornaphat'), 'kornaphat')
        self.assertEqual(wire_value(StrategyAttributeCountryName.Thailand), 'thailand')
        self.assertEqual(wire_value(datetime(2026, 11, 17, 9, 47, 28, tzinfo=timezone(timedelta(hours=7)))),
                         '2026-11-17T02:47:28.000Z')
        self.assertEqual(wire_value(date(2026, 11, 17)), '2026-11-17')

    def test_context_builder_values(self):
        ctx = ServerEvalFeatureContext(MagicMock(), MagicMock())
        ctx.user_key('ormkorn').country(StrategyAttributeCountryName.Thailand) \
            .platform(StrategyAttributePlatformName.Linux).attribute_values('fan', [True, 2.0])
        self.assertEqual(x_featurehub_header(ctx._attributes),
                         'country=thailand,fan=true%2C2,platform=linux,userkey=ormkorn')


if __name__ == '__main__':
    unittest.main()