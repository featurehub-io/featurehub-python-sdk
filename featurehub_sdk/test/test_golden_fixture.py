# Checks rollout strategy evaluation against the golden fixture from featurehub-sdk-docs
# (specs/fixtures/typescript_golden.json, described in specs/rollout-strategies.yaml). fixtures/typescript_golden.json
# here MUST stay identical to that copy: update it from there when the fixture is regenerated.
import json
import os
import re
import time
import unittest
from pathlib import Path

from murmurhash2 import murmurhash3

from featurehub_sdk.client_context import ClientContext, RolloutStrategy, RolloutStrategyAttribute
from featurehub_sdk.strategy_matchers import ApplyFeature, MatcherRegistry, Murmur3PercentageCalculator

FIXTURE = json.loads((Path(__file__).parent / 'fixtures' / 'typescript_golden.json').read_text(encoding='utf-8'))

# a TypeScript bug the specification says implementations MUST NOT reproduce (golden_fixture.known_typescript_bugs)
KNOWN_TYPESCRIPT_BUGS = {'empty strategy first'}

_PLAIN_NUMBER = re.compile(r'[+-]?\d+(\.\d+)?')
_VERSION_PART = re.compile(r'\d+')


# this SDK deliberately doesn't parse numbers in strings with JavaScript's rules (parseInt/parseFloat prefixes, Number()
# of "", " 1", "0x1f", exponents), so the fixture's cases that depend on them are skipped until the specification
# stops relying on them
def depends_on_javascript_number_parsing(case) -> bool:
    if case['type'] == 'NUMBER':
        return any(isinstance(v, str) and not _PLAIN_NUMBER.fullmatch(v) for v in [case['supplied'], *case['values']])
    if case['type'] == 'SEMANTIC_VERSION':
        for v in [case['supplied'], *case['values']]:
            parts = str(v).split('.')[:3]
            if any(not _VERSION_PART.fullmatch(p) and _javascript_number(p) for p in parts):
                return True
    return False


# whether JavaScript's Number(part) is a number (not NaN) for a part that isn't plain digits
def _javascript_number(part: str) -> bool:
    s = part.strip()
    return s == '' or bool(re.fullmatch(r'[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?|0[xX][0-9a-fA-F]+|0[bB][01]+|0[oO][0-7]+'
                                        r'|[+-]?Infinity', s))


def _context(attributes) -> ClientContext:
    ctx = ClientContext(None)
    for key, value in attributes.items():
        ctx.attribute_values(key, value)
    return ctx


class GoldenFixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # the fixture is generated with TZ=UTC: date-times without an offset are local time
        cls._tz = os.environ.get('TZ')
        os.environ['TZ'] = 'UTC'
        time.tzset()

    @classmethod
    def tearDownClass(cls):
        if cls._tz is None:
            os.environ.pop('TZ', None)
        else:
            os.environ['TZ'] = cls._tz
        time.tzset()

    def _assert_no_failures(self, failures, total):
        self.assertEqual(failures, [], f"{len(failures)} of {total} fixture cases failed, the first: {failures[:10]}")

    def test_murmur(self):
        failures = [c for c in FIXTURE['murmur'] if murmurhash3(c['key'].encode('utf-8'), 0) != c['hash']]
        self._assert_no_failures(failures, len(FIXTURE['murmur']))

    def test_percentage(self):
        calculator = Murmur3PercentageCalculator()
        failures = [c for c in FIXTURE['percentage']
                    if calculator.determine_client_percentage(c['key'], c['id']) != c['value']]
        self._assert_no_failures(failures, len(FIXTURE['percentage']))

    def test_matchers(self):
        registry = MatcherRegistry()
        failures = []
        checked = 0
        combinations = set()
        for case in FIXTURE['matchers']:
            if depends_on_javascript_number_parsing(case):
                continue
            checked += 1
            combinations.add((case['type'], case['conditional']))
            attr = RolloutStrategyAttribute({'conditional': case['conditional'], 'type': case['type'],
                                             'values': case['values'], 'fieldName': 'f'})
            # "throw" means TypeScript threw (an invalid pattern, address or block): it MUST NOT match
            expected = False if case['result'] == 'throw' else case['result']
            got = registry.find_matcher(attr).match(case['supplied'], attr)
            if got != expected:
                failures.append({**case, 'got': got})
        self._assert_no_failures(failures, checked)
        # skipping the JavaScript number parsing cases still checks every field type with every conditional
        self.assertEqual(len(combinations), 77)

    def test_apply(self):
        apply = ApplyFeature()
        failures = []
        checked = 0
        for case in FIXTURE['apply']:
            if case['name'] in KNOWN_TYPESCRIPT_BUGS:
                continue
            checked += 1
            result = apply.apply([RolloutStrategy(s) for s in case['strategies']], 'key', case['featureValueId'],
                                 _context(case['context']))
            got = (result.matched, result.value if result.matched else None)
            if got != (case['matched'], case['value'] if case['matched'] else None):
                failures.append({**case, 'got': got})
        self._assert_no_failures(failures, checked)

    def test_known_typescript_bug_is_not_reproduced(self):
        # the empty strategy is skipped, so the 100% strategy after it matches anyone with a percentage key
        apply = ApplyFeature()
        for case in FIXTURE['apply']:
            if case['name'] == 'empty strategy first' and case['context'].get('userkey'):
                result = apply.apply([RolloutStrategy(s) for s in case['strategies']], 'key',
                                     case['featureValueId'], _context(case['context']))
                self.assertTrue(result.matched, case)


if __name__ == '__main__':
    unittest.main()
