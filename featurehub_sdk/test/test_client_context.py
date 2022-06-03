import unittest
from unittest import TestCase
from unittest.mock import MagicMock

from featurehub_sdk.client_context import ClientContext
from featurehub_sdk.strategy_attribute_country_name import StrategyAttributeCountryName
from featurehub_sdk.strategy_attribute_device_name import StrategyAttributeDeviceName
from featurehub_sdk.strategy_attribute_platform_name import StrategyAttributePlatformName


class ClientContextTest(TestCase):

    def setUp(self) -> None:
        self.mock_repo = MagicMock()
        self.mock_feature = MagicMock()
        self.mock_repo.feature.return_value = self.mock_feature
        self.client_context = ClientContext(self.mock_repo)

    def test_get_number(self):
        self.client_context.get_number('angel')
        self.mock_repo.feature.assert_called_with('angel')
        self.mock_feature.get_number.assert_called_once_with()
        self.mock_feature.get_boolean.assert_not_called()

    def test_feature_passthrough(self):
        self.mock_feature.get_raw_json.return_value = None
        self.client_context.is_set('set')
        self.client_context.is_enabled('enabled')
        self.client_context.get_boolean('bool')
        self.client_context.get_flag('flag')
        self.client_context.get_string('string')
        self.client_context.get_json('json')
        self.client_context.get_raw_json('raw-json')

        self.mock_feature.get_boolean.assert_called_once_with()
        self.mock_feature.get_flag.assert_called_once_with()
        self.mock_feature.get_string.assert_called_once_with()
        self.mock_feature.is_enabled.assert_called_once_with()
        self.mock_feature.is_set.assert_called_once_with()
        self.assertEquals(self.mock_feature.get_raw_json.call_count, 2)

    def test_well_known_keys(self):
        self.assertEquals(self.client_context.user_key('fred').get_attr(ClientContext.USER_KEY), 'fred')
        self.assertEquals(self.client_context.session_key('mary').get_attr(ClientContext.SESSION), 'mary')
        self.assertEquals(self.client_context.country(StrategyAttributeCountryName.Ukraine)
                          .get_attr(ClientContext.COUNTRY), StrategyAttributeCountryName.Ukraine)
        self.assertEquals(self.client_context.device(StrategyAttributeDeviceName.Desktop)
                          .get_attr(ClientContext.DEVICE), StrategyAttributeDeviceName.Desktop)
        self.assertEquals(self.client_context.platform(StrategyAttributePlatformName.Android)
                          .get_attr(ClientContext.PLATFORM), StrategyAttributePlatformName.Android)
        self.assertEquals(self.client_context.version("1.0-RC7").get_attr(ClientContext.VERSION), "1.0-RC7")
        self.assertEquals(self.client_context.attribute_values('warehouse_id', ['city', 'smaller-city'])
                          .get_attr('warehouse_id'), ['city', 'smaller-city'])
        self.assertEquals(self.client_context.default_percentage_key(), 'mary')
        self.assertEquals(self.client_context.clear().get_attr(ClientContext.USER_KEY), None)
        self.assertEquals(self.client_context.user_key('fred').get_attr(ClientContext.USER_KEY), 'fred')
        self.assertEquals(self.client_context.default_percentage_key(), 'fred')

    async def test_passed_methods(self):
        await self.client_context.build()
        await self.client_context.close()

if __name__ == '__main__':
    unittest.main()
