from unittest import TestCase
import unittest

from unittest.mock import MagicMock

from featurehub_sdk.client_context import RolloutStrategy, ClientContext
from featurehub_sdk.strategy_matchers import ApplyFeature, MatcherRepository, PercentageCalculator, StrategyMatcher, \
    MatcherRegistry


class ApplyFeatureTest(TestCase):
    apply: ApplyFeature
    matcher: MatcherRepository
    percent: PercentageCalculator
    s_matcher: StrategyMatcher

    def setUp(self) -> None:
        self.percent = MagicMock()
        self.matcher = MagicMock()
        self.s_matcher = MagicMock()

        self.matcher.find_matcher.return_value = self.s_matcher
        self.apply = ApplyFeature(self.percent, self.matcher)

    def test_should_always_return_false_when_undefined_ctx(self):
        found = self.apply.apply([RolloutStrategy({})], 'key', 'fld', None)

        self.assertFalse(found.matched)
        self.assertIsNone(found.value)

    def test_false_when_rollout_strategies_are_empty(self):
        found = self.apply.apply([], 'key', 'fid', MagicMock())

        self.assertFalse(found.matched)
        self.assertIsNone(found.value)

    def test_should_be_false_when_strategies_are_none(self):
        found = self.apply.apply(None, 'key', 'fid', MagicMock())

        self.assertFalse(found.matched)
        self.assertIsNone(found.value)

    def test_should_be_false_if_no_strategies_match_context(self):
        ctx = MagicMock()
        mock_default_percentage_key = 'userkey-value'
        ctx.default_percentage_key = mock_default_percentage_key
        ctx.get_attr.return_value = None
        found = self.apply.apply([RolloutStrategy({
            'attributes': [
                {
                    'fieldName': 'warehouseId',
                    'conditional': 'INCLUDES',
                    'values': ['ponsonby'],
                    'type': 'STRING'
                }
            ]
        })], 'FEATURE_NAME', 'fid', ctx)

        self.assertFalse(found.matched)
        self.assertIsNone(found.value)
        ctx.get_attr.assert_called_once()

    def test_should_not_match_percentage_not_should_match_field(self):
        ctx = MagicMock()
        ctx.default_percentage_key = 'userkey-value'
        ctx.get_attr.return_value = 'ponsonby'
        self.s_matcher.match.return_value = True
        found = self.apply.apply([RolloutStrategy({
            'value': 'sausage',
            'attributes': [
                {
                    'fieldName': 'warehouseId',
                    'conditional': 'INCLUDES',
                    'values': ['ponsonby'],
                    'type': 'STRING'
                }
            ]
        })], 'FEATURE_NAME', 'fid', ctx)

        self.assertTrue(found.matched)
        self.assertEquals(found.value, 'sausage')

    def test_should_not_match_field_comparison_if_value_is_different(self):
        ctx = MagicMock()
        ctx.default_percentage_key = 'userkey-value'
        ctx.get_attr.return_value = 'ponsonby'

        self.s_matcher.match.return_value = False

        found = self.apply.apply([RolloutStrategy({
            'value': 'sausage',
            'attributes': [
                {
                    'fieldName': 'warehouseId',
                    'conditional': 'INCLUDES',
                    'values': ['ponsonby'],
                    'type': 'STRING'
                }
            ]
        })], 'FEATURE_NAME', 'fid', ctx)


        self.assertFalse(found.matched)
        self.assertIsNone(found.value)

    def test_should_extract_values_out_of_context_when_percentage(self):
        ctx = ClientContext(MagicMock())
        ctx.user_key('user@email')
        ctx.attribute_values('a', ['one-thing'])
        ctx.attribute_values('b', ['two-thing'])
        # ctx.default_percentage_key = 'user@email'
        rs = MagicMock()
        rs.has_percentage_attributes = False

        self.assertEquals(ApplyFeature.determine_percentage_key(ctx, rs), 'user@email')

        rs.has_percentage_attributes = True
        rs.percentage_attributes = ['a', 'b']

        self.assertEquals(ApplyFeature.determine_percentage_key(ctx, rs), 'one-thing$two-thing')

    def test_should_process_basic_percentages_property(self):
        ctx = MagicMock(spec=ClientContext)
        ctx.default_percentage_key = 'userkey'

        percent_mock = MagicMock(side_effect=lambda *args: 15 if args[0] == 'userkey' and args[1] == 'fid' else None)
        self.percent.determine_client_percentage = percent_mock

        # self.percent.determine_client_percentage.return_value = 15

        self.apply = ApplyFeature(self.percent, MatcherRegistry())

        found = self.apply.apply([RolloutStrategy({
            'value': 'sausage', 'percentage': 20
        })], 'FEATURE_NAME', 'fid', ctx)

        self.assertTrue(found.matched)
        self.assertEquals(found.value, 'sausage')
        percent_mock.assert_called_with('userkey', 'fid')

    def test_should_bounce_bad_percentages(self):
        ctx = MagicMock(spec=ClientContext)
        ctx.default_percentage_key = 'userkey'

        percent_mock = MagicMock(side_effect=lambda *args: 21 if args[0] == 'userkey' and args[1] == 'fid' else None)
        self.percent.determine_client_percentage = percent_mock
        self.apply = ApplyFeature(self.percent, MatcherRegistry())

        found = self.apply.apply([RolloutStrategy({
            'value': 'sausage', 'percentage': 20
        })], 'FEATURE_NAME', 'fid', ctx)

        self.assertFalse(found.matched)
        percent_mock.assert_called_with('userkey', 'fid')

    def test_should_process_pattern_match_percentages(self):
        ctx = MagicMock(spec=ClientContext)
        ctx.default_percentage_key = 'userkey'

        percent_mock = MagicMock(side_effect=lambda *args: 15 if args[0] == 'userkey' and args[1] == 'fid' else None)
        self.percent.determine_client_percentage = percent_mock
        attr_mock = MagicMock(side_effect=lambda *args: 'ponsonby' if args[0] == 'warehouseId'
                                                                      and args[1] is None else None)
        ctx.get_attr = attr_mock

        # self.percent.determine_client_percentage.return_value = 15

        self.apply = ApplyFeature(self.percent, MatcherRegistry())

        found = self.apply.apply([RolloutStrategy({
            'value': 'sausage', 'percentage': 20,
            'attributes': [{
                'fieldName': 'warehouseId',
                'conditional': 'INCLUDES',
                'values': ['ponsonby'],
                'type': 'STRING'
            }]
        })], 'FEATURE_NAME', 'fid', ctx)

        self.assertTrue(found.matched)
        self.assertEquals(found.value, 'sausage')
        percent_mock.assert_called_with('userkey', 'fid')
        attr_mock.assert_called_with('warehouseId', None)

    def test_should_fail_pattern_percentages(self):
        ctx = MagicMock(spec=ClientContext)
        ctx.default_percentage_key = 'userkey'

        percent_mock = MagicMock(side_effect=lambda *args: 15 if args[0] == 'userkey' and args[1] == 'fid' else None)
        self.percent.determine_client_percentage = percent_mock
        ctx.get_attr.return_value = None

        # self.percent.determine_client_percentage.return_value = 15

        self.apply = ApplyFeature(self.percent, MatcherRegistry())

        found = self.apply.apply([RolloutStrategy({
            'value': 'sausage', 'percentage': 20,
            'attributes': [{
                'fieldName': 'warehouseId',
                'conditional': 'INCLUDES',
                'values': ['ponsonby'],
                'type': 'STRING'
            }]
        })], 'FEATURE_NAME', 'fid', ctx)

        self.assertFalse(found.matched)
        percent_mock.assert_called_with('userkey', 'fid')
        ctx.get_attr.assert_called_with('warehouseId', None)


if __name__ == '__main__':
    unittest.main()