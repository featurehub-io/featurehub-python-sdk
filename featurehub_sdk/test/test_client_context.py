import unittest
from unittest import TestCase
from unittest.mock import MagicMock, PropertyMock

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
        raw_number_mock = PropertyMock(return_value=126.34)
        type(self.mock_feature).get_number = raw_number_mock
        self.client_context.get_number('angel')
        self.mock_repo.feature.assert_called_with('angel')
        raw_number_mock.assert_called_once_with()
        self.assertEqual(self.mock_repo.feature.call_count, 1)

    def test_feature_passthrough(self):
        raw_json_mock = PropertyMock(return_value=None)
        type(self.mock_feature).get_raw_json = raw_json_mock

        self.client_context.get_raw_json('raw-json')
        self.client_context.get_json('json')

        self.assertEqual(raw_json_mock.call_count, 2)

        raw_isset_mock = PropertyMock(return_value=True)
        type(self.mock_feature).is_set = raw_isset_mock
        self.assertTrue(self.client_context.is_set('set'))
        raw_isset_mock.assert_called_once()

        raw_enabled_mock = PropertyMock(return_value=True)
        type(self.mock_feature).is_enabled = raw_enabled_mock
        self.assertTrue(self.client_context.is_enabled('enabled'))
        raw_enabled_mock.assert_called_once()

        raw_boolean_mock = PropertyMock(return_value=True)
        type(self.mock_feature).get_boolean = raw_boolean_mock
        self.assertTrue(self.client_context.get_boolean('bool'))
        raw_boolean_mock.assert_called_once()

        raw_flag_mock = PropertyMock(return_value=True)
        type(self.mock_feature).get_flag = raw_flag_mock
        self.assertTrue(self.client_context.get_flag('flag'))
        raw_flag_mock.assert_called_once()

        raw_string_mock = PropertyMock(return_value='Maverick')
        type(self.mock_feature).get_string = raw_string_mock
        self.assertEqual(self.client_context.get_string('string'), 'Maverick')
        raw_string_mock.assert_called_once()

        raw_number_mock = PropertyMock(return_value=126.34)
        type(self.mock_feature).get_number = raw_number_mock
        self.assertEqual(self.client_context.get_number('number'), 126.34)
        raw_number_mock.assert_called_once()


    def test_well_known_keys(self):
        self.assertEqual(self.client_context.user_key('fred').get_attr(ClientContext.USER_KEY), 'fred')
        self.assertEqual(self.client_context.session_key('mary').get_attr(ClientContext.SESSION), 'mary')
        self.assertEqual(self.client_context.country(StrategyAttributeCountryName.Ukraine)
                          .get_attr(ClientContext.COUNTRY), StrategyAttributeCountryName.Ukraine)
        self.assertEqual(self.client_context.device(StrategyAttributeDeviceName.Desktop)
                          .get_attr(ClientContext.DEVICE), StrategyAttributeDeviceName.Desktop)
        self.assertEqual(self.client_context.platform(StrategyAttributePlatformName.Android)
                          .get_attr(ClientContext.PLATFORM), StrategyAttributePlatformName.Android)
        self.assertEqual(self.client_context.version("1.0-RC7").get_attr(ClientContext.VERSION), "1.0-RC7")
        self.assertEqual(self.client_context.attribute_values('warehouse_id', ['city', 'smaller-city'])
                          .get_attr('warehouse_id'), ['city', 'smaller-city'])
        self.assertEqual(self.client_context.default_percentage_key, 'mary')
        self.assertEqual(self.client_context.clear().get_attr(ClientContext.USER_KEY), None)
        self.assertEqual(self.client_context.user_key('fred').get_attr(ClientContext.USER_KEY), 'fred')
        self.assertEqual(self.client_context.default_percentage_key, 'fred')

    async def test_passed_methods(self):
        await self.client_context.build()
        await self.client_context.close()

if __name__ == '__main__':
    unittest.main()
