import datetime
from typing import Any, Optional, List
from unittest import TestCase
from featurehub_sdk.strategy_matchers import MatcherRegistry
from featurehub_sdk.client_context import RolloutStrategyFieldType, RolloutStrategyAttributeConditional, \
    RolloutStrategyAttribute

class StrategyMatcherTest(TestCase):

    matcher: MatcherRegistry
    field_type: RolloutStrategyFieldType

    def setUp(self) -> None:
        self.matcher = MatcherRegistry()

    def equals(self, condition: RolloutStrategyAttributeConditional, vals: List[Any],
               suppplied_val: Optional[str], matches: bool):
        rsa = RolloutStrategyAttribute({
            'conditional': condition,
            'type': self.field_type,
            'values': vals
        })

        self.assertEqual(self.matcher.find_matcher(rsa).match(suppplied_val, rsa), matches)

    def test_boolean_strategy_matcher(self):
        self.field_type = RolloutStrategyFieldType.Boolean

        self.equals(RolloutStrategyAttributeConditional.Equals, ['true'], 'true', True)
        self.equals(RolloutStrategyAttributeConditional.NotEquals, ['true'], 'true', False)
        self.equals(RolloutStrategyAttributeConditional.NotEquals, ['true'], 'false', True)
        self.equals(RolloutStrategyAttributeConditional.Equals, [True], 'true', True)
        self.equals(RolloutStrategyAttributeConditional.Equals, ['true'], 'false', False)
        self.equals(RolloutStrategyAttributeConditional.Equals, [True], 'false', False)
        self.equals(RolloutStrategyAttributeConditional.Equals, [False], 'false', True)
        self.equals(RolloutStrategyAttributeConditional.Equals, [False], 'true', False)
        self.equals(RolloutStrategyAttributeConditional.Equals, ['false'], 'true', False)

    def test_string_strategy_matcher(self):
        self.field_type = RolloutStrategyFieldType.String

        self.equals(RolloutStrategyAttributeConditional.Equals, ['a', 'b'], None, False)
        self.equals(RolloutStrategyAttributeConditional.Equals, ['a', 'b'], 'a', True)
        self.equals(RolloutStrategyAttributeConditional.Includes, ['a', 'b'], 'a', True)
        self.equals(RolloutStrategyAttributeConditional.NotEquals, ['a', 'b'], 'a', False)
        self.equals(RolloutStrategyAttributeConditional.Excludes, ['a', 'b'], 'a', False)
        self.equals(RolloutStrategyAttributeConditional.Excludes, ['a', 'b'], 'c', True)
        self.equals(RolloutStrategyAttributeConditional.Greater, ['a', 'b'], 'a', False)
        self.equals(RolloutStrategyAttributeConditional.GreaterEquals, ['a', 'b'], 'a', True)
        self.equals(RolloutStrategyAttributeConditional.Greater, ['a', 'b'], 'c', True)
        self.equals(RolloutStrategyAttributeConditional.Less, ['a', 'b'], 'a', True) # < b
        self.equals(RolloutStrategyAttributeConditional.Less, ['a', 'b'], '1', True)
        self.equals(RolloutStrategyAttributeConditional.Less, ['a', 'b'], 'b', False)
        self.equals(RolloutStrategyAttributeConditional.Less, ['a', 'b'], 'c', False)
        self.equals(RolloutStrategyAttributeConditional.LessEquals, ['a', 'b'], 'a', True)
        self.equals(RolloutStrategyAttributeConditional.LessEquals, ['a', 'b'], 'b', True)
        self.equals(RolloutStrategyAttributeConditional.LessEquals, ['a', 'b'], '1', True)
        self.equals(RolloutStrategyAttributeConditional.LessEquals, ['a', 'b'], 'c', False)
        self.equals(RolloutStrategyAttributeConditional.StartsWith, ['fr'], 'fred', True)
        self.equals(RolloutStrategyAttributeConditional.StartsWith, ['fr'], 'mar', False)
        self.equals(RolloutStrategyAttributeConditional.EndsWith, ['ed'], 'fred', True)
        self.equals(RolloutStrategyAttributeConditional.EndsWith, ['fred'], 'mar', False)
        self.equals(RolloutStrategyAttributeConditional.Regex, ['(.*)gold(.*)'], 'actapus (gold)', True)
        self.equals(RolloutStrategyAttributeConditional.Regex, ['(.*)gold(.*)'], '(.*)purple(.*)', False)

    def test_semantic_versions(self):
        self.field_type = RolloutStrategyFieldType.SemanticVersion

        self.equals(RolloutStrategyAttributeConditional.Equals, ['2.0.3'], '2.0.3', True)
        self.equals(RolloutStrategyAttributeConditional.Equals, ['2.0.3', '2.0.1'], '2.0.3', True)
        self.equals(RolloutStrategyAttributeConditional.Equals, ['2.0.3'], '2.0.1', False)
        self.equals(RolloutStrategyAttributeConditional.NotEquals, ['2.0.3'], '2.0.1', True)
        self.equals(RolloutStrategyAttributeConditional.NotEquals, ['2.0.3'], '2.0.3', False)
        self.equals(RolloutStrategyAttributeConditional.Greater, ['2.0.0'], '2.1.0', True)
        self.equals(RolloutStrategyAttributeConditional.Greater, ['2.0.0'], '2.0.1', True)
        self.equals(RolloutStrategyAttributeConditional.Greater, ['2.0.0'], '2.0.1', True)
        self.equals(RolloutStrategyAttributeConditional.Greater, ['2.0.0'], '1.2.1', False)
        self.equals(RolloutStrategyAttributeConditional.GreaterEquals, ['7.1.0'], '7.1.6', True)
        self.equals(RolloutStrategyAttributeConditional.GreaterEquals, ['7.1.6'], '7.1.6', True)
        self.equals(RolloutStrategyAttributeConditional.GreaterEquals, ['7.1.6'], '7.1.2', False)
        self.equals(RolloutStrategyAttributeConditional.Less, ['2.0.0'], '1.1.0', True)
        self.equals(RolloutStrategyAttributeConditional.Less, ['2.0.0'], '1.0.1', True)
        self.equals(RolloutStrategyAttributeConditional.Less, ['2.0.0'], '1.9.9', True)
        self.equals(RolloutStrategyAttributeConditional.Less, ['2.0.0'], '3.2.1', False)
        self.equals(RolloutStrategyAttributeConditional.LessEquals, ['7.1.0'], '7.0.6', True)
        self.equals(RolloutStrategyAttributeConditional.LessEquals, ['7.1.6'], '7.1.2', True)
        self.equals(RolloutStrategyAttributeConditional.LessEquals, ['7.1.2'], '7.1.6', False)


    def test_ips(self):
        self.field_type = RolloutStrategyFieldType.IpAddress
        self.equals(RolloutStrategyAttributeConditional.Equals, ['192.168.86.75'], '192.168.86.75', True)
        self.equals(RolloutStrategyAttributeConditional.Equals, ['192.168.86.75', '10.7.4.8'], '192.168.86.75', True)
        self.equals(RolloutStrategyAttributeConditional.Equals, ['192.168.86.75', '10.7.4.8'], '192.168.83.75', False)
        self.equals(RolloutStrategyAttributeConditional.Excludes, ['192.168.86.75', '10.7.4.8'], '192.168.83.75', True)
        self.equals(RolloutStrategyAttributeConditional.Excludes, ['192.168.86.75', '10.7.4.8'], '192.168.86.75', False)
        self.equals(RolloutStrategyAttributeConditional.Includes, ['192.168.86.75', '10.7.4.8'], '192.168.86.75', True)
        self.equals(RolloutStrategyAttributeConditional.Equals, ['192.168.86.75'], '192.168.86.72', False)
        self.equals(RolloutStrategyAttributeConditional.NotEquals, ['192.168.86.75'], '192.168.86.75', False)
        self.equals(RolloutStrategyAttributeConditional.NotEquals, ['192.168.86.75'], '192.168.86.72', True)
        self.equals(RolloutStrategyAttributeConditional.Equals, ['192.168.0.0/16'], '192.168.86.72', True)
        self.equals(RolloutStrategyAttributeConditional.Equals, ['192.168.0.0/16'], '192.162.86.72', False)
        self.equals(RolloutStrategyAttributeConditional.Equals, ['10.0.0.0/24', '192.168.0.0/16'], '192.168.86.72', True)
        self.equals(RolloutStrategyAttributeConditional.Equals, ['10.0.0.0/24', '192.168.0.0/16'], '172.168.86.72', False)

    def test_dates(self):
        self.field_type = RolloutStrategyFieldType.Date

        self.equals(RolloutStrategyAttributeConditional.Equals, ['2019-01-01', '2019-02-01'], '2019-02-01', True)
        self.equals(RolloutStrategyAttributeConditional.Equals, ['2019-01-01', '2019-02-01'], '2019-02-01', True)
        self.equals(RolloutStrategyAttributeConditional.Includes, ['2019-01-01', '2019-02-01'], '2019-02-01', True)
        self.equals(RolloutStrategyAttributeConditional.NotEquals, ['2019-01-01', '2019-02-01'], '2019-02-01', False)
        self.equals(RolloutStrategyAttributeConditional.Excludes, ['2019-01-01', '2019-02-01'], '2019-02-01', False)

        self.equals(RolloutStrategyAttributeConditional.Equals, ['2019-01-01', '2019-02-01'], '2019-02-07', False)
        self.equals(RolloutStrategyAttributeConditional.Includes, ['2019-01-01', '2019-02-01'], '2019-02-07', False)
        self.equals(RolloutStrategyAttributeConditional.NotEquals, ['2019-01-01', '2019-02-01'], '2019-02-07', True)
        self.equals(RolloutStrategyAttributeConditional.Excludes, ['2019-01-01', '2019-02-01'], '2019-02-07', True)

        self.equals(RolloutStrategyAttributeConditional.Greater, ['2019-01-01', '2019-02-01'], '2019-02-07', True)
        self.equals(RolloutStrategyAttributeConditional.GreaterEquals, ['2019-01-01', '2019-02-01'], '2019-02-07', True)
        self.equals(RolloutStrategyAttributeConditional.GreaterEquals, ['2019-01-01', '2019-02-01'], '2019-02-01', True)
        self.equals(RolloutStrategyAttributeConditional.Less, ['2019-01-01', '2019-02-01'], '2017-02-01', True)
        self.equals(RolloutStrategyAttributeConditional.Less, ['2019-01-01', '2019-02-01'], '2019-02-01', False)
        self.equals(RolloutStrategyAttributeConditional.LessEquals, ['2019-01-01', '2019-02-01'], '2019-02-01', True)
        self.equals(RolloutStrategyAttributeConditional.LessEquals, ['2019-01-01', '2019-02-01'], '2019-03-01', False)
        self.equals(RolloutStrategyAttributeConditional.Regex, ['2019-.*'], '2019-03-01', True)
        self.equals(RolloutStrategyAttributeConditional.Regex, ['2019-.*'], '2017-03-01', False)
        self.equals(RolloutStrategyAttributeConditional.Regex, ['2019-.*', '(.*)-03-(.*)'], '2017-03-01', True)

        self.equals(RolloutStrategyAttributeConditional.StartsWith, ['2019', '2017'], '2019-02-07', True)
        self.equals(RolloutStrategyAttributeConditional.StartsWith, ['2019'], '2017-02-07', False)

        self.equals(RolloutStrategyAttributeConditional.EndsWith, ['01'], '2017-02-01', True)
        self.equals(RolloutStrategyAttributeConditional.EndsWith, ['03', '02', '2017'], '2017-02-01', False)

    def test_numbers(self):
        self.field_type = RolloutStrategyFieldType.Number
        self.equals(RolloutStrategyAttributeConditional.Equals, [10, 5], '5', True)
        self.equals(RolloutStrategyAttributeConditional.Equals, [5], '5', True)
        self.equals(RolloutStrategyAttributeConditional.Equals, [4], '5', False)
        self.equals(RolloutStrategyAttributeConditional.Equals, [4, 7], '5', False)
        self.equals(RolloutStrategyAttributeConditional.Includes, [4, 7], '5', False)
        self.equals(RolloutStrategyAttributeConditional.NotEquals, [23, 100923], '5', True)
        self.equals(RolloutStrategyAttributeConditional.Excludes, [23, 100923], '5', True)
        self.equals(RolloutStrategyAttributeConditional.NotEquals, [5], '5', False)
        self.equals(RolloutStrategyAttributeConditional.Greater, [2, 4], '5', True)
        self.equals(RolloutStrategyAttributeConditional.GreaterEquals, [2, 5], '5', True)
        self.equals(RolloutStrategyAttributeConditional.GreaterEquals, [4, 5], '5', True)
        self.equals(RolloutStrategyAttributeConditional.LessEquals, [2, 5], '5', True)
        self.equals(RolloutStrategyAttributeConditional.Less, [8, 7], '5', True)
        self.equals(RolloutStrategyAttributeConditional.Greater, [7, 10], '5', False)
        self.equals(RolloutStrategyAttributeConditional.GreaterEquals, [6, 7], '5', False)
        self.equals(RolloutStrategyAttributeConditional.LessEquals, [2, 3], '5', False)
        self.equals(RolloutStrategyAttributeConditional.Less, [1, -1], '5', False)

    def test_datetimes(self):
        self.field_type = RolloutStrategyFieldType.Datetime
        # // test equals
        self.equals(RolloutStrategyAttributeConditional.Equals, ['2019-01-01T01:01:01Z', '2019-02-01T01:01:01Z'],
          '2019-02-01T01:01:01Z', True)
        self.equals(RolloutStrategyAttributeConditional.Includes, ['2019-01-01T01:01:01Z', '2019-02-01T01:01:01Z'],
          '2019-02-01T01:01:01Z', True)
        self.equals(RolloutStrategyAttributeConditional.NotEquals, ['2019-01-01T01:01:01Z', '2019-02-01T01:01:01Z'],
          '2019-02-01T01:01:01Z', False)
        self.equals(RolloutStrategyAttributeConditional.Excludes, ['2019-01-01T01:01:01Z', '2019-02-01T01:01:01Z'],
          '2019-02-01T01:01:01Z', False)

        # // test not equals
        self.equals(RolloutStrategyAttributeConditional.Equals, ['2019-01-01T01:01:01Z', '2019-02-01T01:01:01Z'],
          '2017-02-01T01:01:01Z', False)
        self.equals(RolloutStrategyAttributeConditional.Includes, ['2019-01-01T01:01:01Z', '2019-02-01T01:01:01Z'],
          '2017-02-01T01:01:01Z', False)
        self.equals(RolloutStrategyAttributeConditional.NotEquals, ['2019-01-01T01:01:01Z', '2019-02-01T01:01:01Z'],
          '2017-02-01T01:01:01Z', True)
        self.equals(RolloutStrategyAttributeConditional.Excludes, ['2019-01-01T01:01:01Z', '2019-02-01T01:01:01Z'],
          '2017-02-01T01:01:01Z', True)

        # // test  less & less =
        self.equals(RolloutStrategyAttributeConditional.Less, ['2019-01-01T01:01:01Z', '2019-02-01T01:01:01Z'],
          '2016-02-01T01:01:01Z', True)
        self.equals(RolloutStrategyAttributeConditional.Less, ['2019-01-01T01:01:01Z', '2019-02-01T01:01:01Z'],
          '2020-02-01T01:01:01Z', False)

        self.equals(RolloutStrategyAttributeConditional.LessEquals, ['2019-01-01T01:01:01Z', '2019-02-01T01:01:01Z'],
          '2019-02-01T01:01:01Z', True)
        self.equals(RolloutStrategyAttributeConditional.LessEquals, ['2019-01-01T01:01:01Z', '2019-02-01T01:01:01Z'],
          '2020-02-01T01:01:01Z', False)

        self.equals(RolloutStrategyAttributeConditional.Regex, ['2019-.*'], '2019-07-06T01:01:01Z', True)
        self.equals(RolloutStrategyAttributeConditional.Regex, ['2019-.*'], '2016-07-06T01:01:01Z', False)
        self.equals(RolloutStrategyAttributeConditional.Regex, ['2019-.*', '(.*)-03-(.*)'], '2019-07-06T01:01:01Z', True)
        self.equals(RolloutStrategyAttributeConditional.Regex, ['2019-.*', '(.*)-03-(.*)'], '2014-03-06T01:01:01Z', True)

        self.equals(RolloutStrategyAttributeConditional.StartsWith, ['2019', '2017'], '2017-03-06T01:01:01Z', True)
        self.equals(RolloutStrategyAttributeConditional.StartsWith, ['2019'], '2017-03-06T01:01:01Z', False)
        self.equals(RolloutStrategyAttributeConditional.EndsWith, [':01Z'], '2017-03-06T01:01:01Z', True)
        self.equals(RolloutStrategyAttributeConditional.EndsWith, ['03', '2017', '01:01'], '2017-03-06T01:01:01Z', False)
        self.equals(RolloutStrategyAttributeConditional.EndsWith, ['rubbish'], '2017-03-06T01:01:01Z', False)


class StrategyMatcherSpecTest(TestCase):
    """cases rollout-strategies.yaml calls out that the golden fixture doesn't cover, and earlier bugs"""

    def setUp(self) -> None:
        self.registry = MatcherRegistry()

    def match(self, field_type: str, conditional: str, values, supplied) -> bool:
        attr = RolloutStrategyAttribute({'conditional': conditional, 'type': field_type, 'values': values,
                                         'fieldName': 'f'})
        return self.registry.find_matcher(attr).match(supplied, attr)

    def test_non_string_context_values(self):
        self.assertTrue(self.match('BOOLEAN', 'EQUALS', [True], True))
        self.assertTrue(self.match('BOOLEAN', 'EQUALS', ['true'], True))
        self.assertTrue(self.match('NUMBER', 'GREATER', [18], 24))
        self.assertTrue(self.match('NUMBER', 'STARTS_WITH', [1], 100.0))
        self.assertTrue(self.match('STRING', 'EQUALS', ['true'], True))

    def test_native_datetimes_are_converted_to_utc(self):
        bangkok = datetime.timezone(datetime.timedelta(hours=7))
        self.assertTrue(self.match('DATE', 'EQUALS', ['2026-11-16'], datetime.datetime(2026, 11, 17, 2, 0, tzinfo=bangkok)))
        self.assertTrue(self.match('DATETIME', 'EQUALS', ['2026-11-16T19:00:00Z'],
                                   datetime.datetime(2026, 11, 17, 2, 0, 0, 123000, tzinfo=bangkok)))
        self.assertTrue(self.match('DATE', 'EQUALS', ['2026-11-17'], datetime.date(2026, 11, 17)))

    def test_invalid_values_never_match_or_raise(self):
        self.assertFalse(self.match('STRING', 'REGEX', ['(ling'], 'lingling kwong'))
        self.assertFalse(self.match('IP_ADDRESS', 'INCLUDES', ['10.0.0.0/8'], '::1'))
        self.assertFalse(self.match('IP_ADDRESS', 'NOT_EQUALS', ['not-an-ip'], '10.0.0.1'))
        self.assertFalse(self.match('SEMANTIC_VERSION', 'GREATER', ['1.0.0'], 'always wonder'))
        self.assertFalse(self.match('DATE', 'EQUALS', ['2026-11-17'], 'keep silent'))

    def test_numbers_in_strings_are_parsed_strictly(self):
        # strict_number, not JavaScript's prefix parsing: a string that isn't exactly a number never matches
        self.assertTrue(self.match('NUMBER', 'EQUALS', [12], '12'))
        self.assertTrue(self.match('NUMBER', 'EQUALS', ['12.5'], '+12.5'))
        for not_a_number in (' 12.5', '1e3', '.5', '5.', 'Infinity', float('inf'), float('nan')):
            self.assertFalse(self.match('NUMBER', 'NOT_EQUALS', [1], not_a_number), not_a_number)
        self.assertTrue(self.match('NUMBER', 'NOT_EQUALS', ['1e3'], 1000))  # values that aren't numbers are ignored
        self.assertFalse(self.match('NUMBER', 'GREATER', [10], '12abc'))
        self.assertFalse(self.match('NUMBER', 'NOT_EQUALS', [1], 'kornaphat'))

    def test_semantic_versions_compare_numerically(self):
        self.assertTrue(self.match('SEMANTIC_VERSION', 'GREATER', ['1.9.0'], '1.10.0'))
        self.assertTrue(self.match('SEMANTIC_VERSION', 'EQUALS', ['2.0'], '2.0'))
        self.assertFalse(self.match('SEMANTIC_VERSION', 'STARTS_WITH', ['2'], '2.0.0'))
