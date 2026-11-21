from unittest import TestCase
import unittest

from unittest.mock import MagicMock

from featurehub_sdk.client_context import RolloutStrategy, ClientContext, RolloutStrategyAttribute, \
    RolloutStrategyAttributeConditional
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
        ctx.get_attr_values.return_value = None
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
        ctx.get_attr_values.assert_called_once_with('warehouseId')

    def test_should_not_match_percentage_and_should_match_field(self):
        ctx = MagicMock()
        ctx.default_percentage_key = 'userkey-value'
        ctx.get_attr_values.return_value = ['ponsonby']
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
        self.assertEqual(found.value, 'sausage')

    def test_should_not_match_field_comparison_if_value_is_different(self):
        ctx = MagicMock()
        ctx.default_percentage_key = 'userkey-value'
        ctx.get_attr_values.return_value = ['ponsonby']

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

        self.assertEqual(ApplyFeature.determine_percentage_key(ctx, rs), 'user@email')

        rs.has_percentage_attributes = True
        rs.percentage_attributes = ['a', 'b']

        self.assertEqual(ApplyFeature.determine_percentage_key(ctx, rs), 'one-thing$two-thing')

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
        self.assertEqual(found.value, 'sausage')
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
        attr_mock = MagicMock(side_effect=lambda *args: ['ponsonby']
        if args[0] == 'warehouseId' else None)
        ctx.get_attr_values = attr_mock

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
        self.assertEqual(found.value, 'sausage')
        percent_mock.assert_called_with('userkey', 'fid')
        attr_mock.assert_called_with('warehouseId')

    def test_should_fail_pattern_percentages(self):
        ctx = MagicMock(spec=ClientContext)
        ctx.default_percentage_key = 'userkey'

        percent_mock = MagicMock(side_effect=lambda *args: 15 if args[0] == 'userkey' and args[1] == 'fid' else None)
        self.percent.determine_client_percentage = percent_mock
        ctx.get_attr_values.return_value = None

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
        ctx.get_attr_values.assert_called_with('warehouseId')

    # "should return false if the supplied value is nil, the attribute value has a value and its an equals comparison"
    def test_should_return_false_if_supplied_nil(self):
        attr = MagicMock(spec=RolloutStrategyAttribute)
        attr.field_name = "userkey"
        attr.values = "fred"
        rs = MagicMock(spec=RolloutStrategy)
        rs.attributes = [attr]
        ctx = MagicMock(spec=ClientContext)
        ctx.get_attr_values.return_value = None

        val = self.apply.match_attribute(ctx, rs)
        self.assertFalse(val)
        ctx.get_attr_values.assert_called_with('userkey')

    # an attribute the context doesn't supply never matches, even when the strategy has no values for it
    # (rollout-strategies.yaml attributes_match)
    def test_both_none_should_not_match(self):
        attr = MagicMock(spec=RolloutStrategyAttribute)
        attr.field_name = "userkey"
        attr.values = None
        attr.conditional = RolloutStrategyAttributeConditional.Equals
        rs = MagicMock(spec=RolloutStrategy)
        rs.attributes = [attr]
        ctx = MagicMock(spec=ClientContext)
        ctx.get_attr_values.return_value = None

        val = self.apply.match_attribute(ctx, rs)
        self.assertFalse(val)
        ctx.get_attr_values.assert_called_with('userkey')


class ApplyFeatureAlgorithmTest(TestCase):
    def _ctx(self, **attributes) -> ClientContext:
        ctx = ClientContext(MagicMock())
        for key, value in attributes.items():
            ctx.attribute_values(key, value if isinstance(value, list) else [value])
        return ctx

    def test_percentage_strategies_stack(self):
        # 20% then 30%: someone at 35% gets the second strategy (this used to match nothing)
        percent = MagicMock()
        percent.determine_client_percentage.return_value = 350000
        apply = ApplyFeature(percent, MatcherRegistry())
        found = apply.apply([RolloutStrategy({'id': 'p1', 'percentage': 200000, 'value': 'ling'}),
                             RolloutStrategy({'id': 'p2', 'percentage': 300000, 'value': 'orm'})],
                            'key', 'fv', self._ctx(userkey='sirilak'))
        self.assertTrue(found.matched)
        self.assertEqual(found.value, 'orm')
        percent.determine_client_percentage.assert_called_once_with('sirilak', 'fv')

    def test_a_list_attribute_matches_if_any_value_does(self):
        found = ApplyFeature().apply([RolloutStrategy({'id': 'a', 'value': 'chago', 'attributes': [
            {'conditional': 'EQUALS', 'type': 'STRING', 'fieldName': 'shop', 'values': ['kwong pastry']}]})],
            'key', 'fv', self._ctx(shop=['omu&co', 'kwong pastry']))
        self.assertTrue(found.matched)

    def test_a_session_list_is_one_percentage_key(self):
        self.assertEqual(self._ctx(session=['ling', 'orm'], userkey='kwong').default_percentage_key, 'ling,orm')
        self.assertEqual(self._ctx(session=[''], userkey='kwong').default_percentage_key, 'kwong')
        self.assertIsNone(self._ctx().default_percentage_key)

    def test_an_absent_date_is_today(self):
        found = ApplyFeature().apply([RolloutStrategy({'id': 'd', 'value': 'after', 'attributes': [
            {'conditional': 'GREATER', 'type': 'DATE', 'fieldName': 'launch', 'values': ['2000-01-01']}]})],
            'key', 'fv', self._ctx())
        self.assertTrue(found.matched)


if __name__ == '__main__':
    unittest.main()
