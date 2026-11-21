# Rollout strategy evaluation, as specified by featurehub-sdk-docs specs/rollout-strategies.yaml and checked against
# its golden fixture (featurehub_sdk/test/fixtures/typescript_golden.json).
#
# Numbers are strict (js_conversions.strict_number): a finite number, or a string that is exactly a decimal integer or
# float, never JavaScript's parseInt/parseFloat prefix rules.
import datetime
import logging
import math
import re
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, Iterable, List, Optional

from murmurhash2 import murmurhash3

from featurehub_sdk.client_context import ClientContext, RolloutStrategyAttributeConditional, \
    RolloutStrategyFieldType, RolloutStrategy, RolloutStrategyAttribute, Applied, wire_value

log = logging.getLogger('featurehub_sdk')

Conditional = RolloutStrategyAttributeConditional


class PercentageCalculator:
    def determine_client_percentage(self, percentage_text: str, feature_id: str) -> float:
        pass


class Murmur3PercentageCalculator(PercentageCalculator):
    MAX_PERCENTAGE = 1000000
    SEED = 0

    def determine_client_percentage(self, percentage_text: str, feature_id: str) -> float:
        result = murmurhash3(bytes(percentage_text + feature_id, 'utf-8'), Murmur3PercentageCalculator.SEED)
        return math.floor(result / math.pow(2, 32) * Murmur3PercentageCalculator.MAX_PERCENTAGE)


class _Invalid(Exception):
    """a value that can't be evaluated (an invalid pattern, address or block): the attribute doesn't match"""


# the text form of a value, as the specification's js_to_string: whole floats without a fraction, true/false
def _text(value: Any) -> str:
    return '' if value is None else wire_value(value)


def _values(attr: RolloutStrategyAttribute) -> List[Any]:
    return [v for v in (attr.values or []) if v is not None]


def _any(values: Iterable[Any], test: Callable[[Any], bool]) -> bool:
    for v in values:
        if test(v):
            return True
    return False


def _utf16(s: str) -> bytes:
    # strings are ordered by UTF-16 code unit, as in the other SDKs
    return s.encode('utf-16-be', 'surrogatepass')


class StrategyMatcher:
    # supplied_value is one value from the context. a matcher never raises: anything it can't evaluate doesn't match
    def match(self, supplied_value: Any, attr: RolloutStrategyAttribute) -> bool:
        if isinstance(supplied_value, Enum):  # e.g. StrategyAttributeCountryName: matched by its value
            supplied_value = supplied_value.value
        if supplied_value is None:
            return False
        try:
            return self._match(supplied_value, attr)
        except _Invalid:
            return False
        except Exception:
            log.debug("featurehub strategy attribute %s could not be evaluated", attr.field_name, exc_info=True)
            return False

    def _match(self, supplied_value: Any, attr: RolloutStrategyAttribute) -> bool:
        return False


class MatcherRepository:
    def find_matcher(self, attr: RolloutStrategyAttribute) -> StrategyMatcher:
        pass


class FallthroughMatcher(StrategyMatcher):
    pass


def _string_match(supplied: str, conditional: Conditional, values: List[str]) -> bool:
    if conditional == Conditional.Equals:
        return supplied in values
    if conditional == Conditional.NotEquals:
        return supplied not in values
    if conditional == Conditional.StartsWith:
        return _any(values, lambda v: supplied.startswith(v))
    if conditional == Conditional.EndsWith:
        return _any(values, lambda v: supplied.endswith(v))
    if conditional == Conditional.Includes:
        return _any(values, lambda v: v in supplied)
    if conditional == Conditional.Excludes:
        return not _any(values, lambda v: v in supplied)
    if conditional == Conditional.Regex:
        return _any(values, lambda v: _regex(v).search(supplied) is not None)
    s = _utf16(supplied)
    if conditional == Conditional.Greater:
        return _any(values, lambda v: s > _utf16(v))
    if conditional == Conditional.GreaterEquals:
        return _any(values, lambda v: s >= _utf16(v))
    if conditional == Conditional.Less:
        return _any(values, lambda v: s < _utf16(v))
    if conditional == Conditional.LessEquals:
        return _any(values, lambda v: s <= _utf16(v))
    return False


def _regex(pattern: str) -> re.Pattern:
    try:
        return re.compile(pattern)
    except re.error:
        raise _Invalid()


class StringMatcher(StrategyMatcher):
    def _match(self, supplied_value: Any, attr: RolloutStrategyAttribute) -> bool:
        return _string_match(_text(supplied_value), attr.conditional, [_text(v) for v in _values(attr)])


_NUMBER = re.compile(r'[+-]?[0-9]+(\.[0-9]+)?')


# strict_number: a finite number, or a string that is exactly a decimal integer or float ("12", "-0.5"; not "12abc",
# "1e3", " 3" or ".5"); else None
def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, str) and _NUMBER.fullmatch(value):
        return float(value)
    if isinstance(value, Decimal) and value.is_finite():
        return float(value)
    return None


class NumberMatcher(StrategyMatcher):
    _STRING_CONDITIONALS = (Conditional.StartsWith, Conditional.EndsWith, Conditional.Includes,
                            Conditional.Excludes, Conditional.Regex)

    def _match(self, supplied_value: Any, attr: RolloutStrategyAttribute) -> bool:
        supplied = _number(supplied_value)
        if supplied is None:  # not a number, so nothing matches
            return False
        conditional = attr.conditional
        values = [n for n in (_number(v) for v in _values(attr)) if n is not None]  # values that aren't numbers are ignored
        if conditional in self._STRING_CONDITIONALS:
            # these compare the number's text with the values' text, so 100.0 STARTS_WITH 1
            return _string_match(_text(supplied), conditional, [_text(v) for v in values])

        if conditional == Conditional.Equals:
            return _any(values, lambda v: supplied == v)
        if conditional == Conditional.NotEquals:
            return not _any(values, lambda v: supplied == v)
        if conditional == Conditional.Greater:
            return _any(values, lambda v: supplied > v)
        if conditional == Conditional.GreaterEquals:
            return _any(values, lambda v: supplied >= v)
        if conditional == Conditional.Less:
            return _any(values, lambda v: supplied < v)
        if conditional == Conditional.LessEquals:
            return _any(values, lambda v: supplied <= v)
        return False


_VERSION_PART = re.compile(r'\d+')


# compares the first three dot separated parts numerically; a part that is missing or not a number sorts below any
# number, and two of them are equal. pre-release and build suffixes are not understood
def _compare_versions(a: str, b: str) -> int:
    pa, pb = a.split('.'), b.split('.')
    for i in range(3):
        na = int(pa[i]) if i < len(pa) and _VERSION_PART.fullmatch(pa[i]) else None
        nb = int(pb[i]) if i < len(pb) and _VERSION_PART.fullmatch(pb[i]) else None
        if na is None and nb is None:
            continue
        if na is None:
            return -1
        if nb is None:
            return 1
        if na != nb:
            return 1 if na > nb else -1
    return 0


class SemanticVersionMatcher(StrategyMatcher):
    def _match(self, supplied_value: Any, attr: RolloutStrategyAttribute) -> bool:
        supplied = _text(supplied_value)
        values = [_text(v) for v in _values(attr)]
        conditional = attr.conditional
        compare = lambda v: _compare_versions(supplied, v)
        if conditional in (Conditional.Equals, Conditional.Includes):
            return _any(values, lambda v: compare(v) == 0)
        if conditional in (Conditional.NotEquals, Conditional.Excludes):
            return _any(values, lambda v: compare(v) != 0)  # any value unequal, as the specification says
        if conditional == Conditional.Greater:
            return _any(values, lambda v: compare(v) > 0)
        if conditional == Conditional.GreaterEquals:
            return _any(values, lambda v: compare(v) >= 0)
        if conditional == Conditional.Less:
            return _any(values, lambda v: compare(v) < 0)
        if conditional == Conditional.LessEquals:
            return _any(values, lambda v: compare(v) <= 0)
        return False


_DATE_ONLY = re.compile(r'\d{4}-\d{2}-\d{2}')


# the supplied value as a UTC datetime: a date-only string is UTC, a date-time with an offset is converted to UTC, and
# one without an offset is local time. None if it can't be parsed
def _instant(value: Any) -> Optional[datetime.datetime]:
    if isinstance(value, datetime.datetime):
        return value.astimezone(datetime.timezone.utc)
    if isinstance(value, datetime.date):
        return datetime.datetime(value.year, value.month, value.day, tzinfo=datetime.timezone.utc)
    if not isinstance(value, str):
        return None
    s = value.strip()
    try:
        if _DATE_ONLY.fullmatch(s):
            return datetime.datetime.strptime(s, '%Y-%m-%d').replace(tzinfo=datetime.timezone.utc)
        return datetime.datetime.fromisoformat(s).astimezone(datetime.timezone.utc)
    except ValueError:
        return None


class DateMatcher(StrategyMatcher):
    FORMAT = '%Y-%m-%d'

    def _match(self, supplied_value: Any, attr: RolloutStrategyAttribute) -> bool:
        instant = _instant(supplied_value)
        if instant is None:
            return False
        # the values are compared as they are: they should already be in this form
        return _string_match(instant.strftime(self.FORMAT), attr.conditional, [_text(v) for v in _values(attr)])


class DateTimeMatcher(DateMatcher):
    FORMAT = '%Y-%m-%dT%H:%M:%SZ'


def _to_bool(value: Any) -> bool:
    return value if isinstance(value, bool) else _text(value) == 'true'


class BooleanMatcher(StrategyMatcher):
    def _match(self, supplied_value: Any, attr: RolloutStrategyAttribute) -> bool:
        values = _values(attr)
        if not values:
            return False
        if attr.conditional == Conditional.Equals:
            return _to_bool(supplied_value) == _to_bool(values[0])
        if attr.conditional == Conditional.NotEquals:
            return _to_bool(supplied_value) != _to_bool(values[0])
        return False


# IPv4 addresses in dotted quad or the short forms, each part decimal, octal (leading 0) or hex (leading 0x)
def _ip_part(s: str):
    i, base, digits = 0, 10, '0123456789'
    if len(s) > 1 and s[0] == '0':
        if s[1] in 'xX':
            i, base, digits = 2, 16, '0123456789abcdefABCDEF'
        elif s[1].isdigit():
            i, base, digits = 1, 8, '01234567'
    start, n = i, 0
    while i < len(s) and s[i] in digits:
        n = (n * base + int(s[i], 16)) & 0xFFFFFFFF
        i += 1
    if i == start:
        raise _Invalid()
    return n, i


def _ip_to_int(ip: str) -> int:
    parts = []
    rest = ip
    while rest and len(parts) < 4:
        if parts:
            if rest[0] != '.':
                raise _Invalid()
            rest = rest[1:]
        n, used = _ip_part(rest)
        parts.append(n)
        rest = rest[used:]
    if rest or not parts:
        raise _Invalid()
    # the last part fills the bytes the others don't: a.b is a (8 bits) then b (24 bits)
    limits = {1: [0xFFFFFFFF], 2: [0xFF, 0xFFFFFF], 3: [0xFF, 0xFF, 0xFFFF], 4: [0xFF] * 4}[len(parts)]
    if any(p > limit for p, limit in zip(parts, limits)):
        raise _Invalid()
    value = 0
    for i, p in enumerate(parts[:-1]):
        value |= p << (24 - 8 * i)
    return value | parts[-1]


# a block as (network, mask): CIDR (10.0.0.0/8), dotted mask (172.16.0.0/255.240.0.0) or a single address (/32)
def _ip_block(block: str):
    if block.count('/') > 1:
        raise _Invalid()
    address, _, mask = block.partition('/')
    if not mask:
        bits = 32
    elif '.' in mask:
        mask_value = _ip_to_int(mask)
        bits = next((b for b in range(32, -1, -1) if mask_value == (0xFFFFFFFF << (32 - b)) & 0xFFFFFFFF), None)
        if bits is None:
            raise _Invalid()
    elif re.fullmatch(r'[0-9]{1,2}', mask) and int(mask) <= 32:
        bits = int(mask)
    else:
        raise _Invalid()
    mask_value = (0xFFFFFFFF << (32 - bits)) & 0xFFFFFFFF if bits else 0
    return _ip_to_int(address) & mask_value, mask_value


def _block_contains(block, supplied) -> bool:
    network, mask = block
    first, supplied_mask = supplied
    last = first | (~supplied_mask & 0xFFFFFFFF)
    return (first & mask) == network and (last & mask) == network


class IPNetworkMatcher(StrategyMatcher):
    def _match(self, supplied_value: Any, attr: RolloutStrategyAttribute) -> bool:
        supplied = _ip_block(_text(supplied_value))  # a single address, or a block whose addresses must all be in
        contains = lambda v: _block_contains(_ip_block(_text(v)), supplied)
        if attr.conditional in (Conditional.Equals, Conditional.Includes):
            return _any(_values(attr), contains)
        if attr.conditional in (Conditional.NotEquals, Conditional.Excludes):
            return not _any(_values(attr), contains)
        return False


class MatcherRegistry(MatcherRepository):
    _MATCHERS = {
        RolloutStrategyFieldType.String: StringMatcher(),
        RolloutStrategyFieldType.Date: DateMatcher(),
        RolloutStrategyFieldType.Datetime: DateTimeMatcher(),
        RolloutStrategyFieldType.SemanticVersion: SemanticVersionMatcher(),
        RolloutStrategyFieldType.Number: NumberMatcher(),
        RolloutStrategyFieldType.Boolean: BooleanMatcher(),
        RolloutStrategyFieldType.IpAddress: IPNetworkMatcher(),
    }

    def find_matcher(self, attr: RolloutStrategyAttribute) -> StrategyMatcher:
        try:
            return self._MATCHERS.get(attr.field_type, FallthroughMatcher())
        except ValueError:  # a field type this SDK doesn't know
            return FallthroughMatcher()


def _js_truthy(value: Any) -> bool:
    if value is None or value is False or value == '':
        return False
    if isinstance(value, (int, float)) and not isinstance(value, bool) and (value == 0 or math.isnan(value)):
        return False
    return True


# the text of a percentage attribute: a single value if truthy, else "<none>"; several values joined with ","
def _percentage_attribute_text(values: Optional[List[Any]]) -> str:
    if values is None:
        return '<none>'
    if len(values) == 1:
        return _text(values[0]) if _js_truthy(values[0]) else '<none>'
    return ','.join(_text(v) for v in values)


class ApplyFeature:
    _percentageCalculator: PercentageCalculator
    _matcherRepository: MatcherRepository

    def __init__(self, percentage_calculator: Optional[PercentageCalculator] = None,
                 matcher_repository: Optional[MatcherRepository] = None):
        self._percentageCalculator = percentage_calculator if percentage_calculator is not None \
            else Murmur3PercentageCalculator()
        self._matcherRepository = matcher_repository if matcher_repository is not None else MatcherRegistry()

    def apply(self, strategies: List[RolloutStrategy], key: str, feature_value_id: str,
              context: ClientContext) -> Applied:
        if context is None or strategies is None or len(strategies) == 0:
            return Applied(False, None)

        percentage: Optional[float] = None
        percentage_key: Optional[str] = None
        base_percentage: Dict[str, float] = {}  # per percentage key, the share used so far
        default_percentage_key = context.default_percentage_key

        for rsi in strategies:
            if rsi.percentage != 0 and (default_percentage_key or rsi.has_percentage_attributes):
                new_percentage_key = self.determine_percentage_key(context, rsi)
                base_percentage.setdefault(new_percentage_key, 0)

                # the percentage is only recalculated when the key changes
                if percentage is None or new_percentage_key != percentage_key:
                    percentage_key = new_percentage_key
                    percentage = self._percentageCalculator.determine_client_percentage(percentage_key,
                                                                                        feature_value_id)

                # percentage only strategies stack; one with attributes compares against its own percentage alone
                use_base_percentage = 0 if rsi.has_attributes else base_percentage[new_percentage_key]

                if percentage <= (use_base_percentage + rsi.percentage):
                    if not rsi.has_attributes or self.match_attribute(context, rsi):
                        return Applied(True, rsi.value)

                if not rsi.has_attributes:
                    base_percentage[percentage_key] = base_percentage[percentage_key] + rsi.percentage

            if rsi.percentage == 0 and rsi.has_attributes and self.match_attribute(context, rsi):
                return Applied(True, rsi.value)

        return Applied(False, None)

    # every attribute must match; an attribute matches if any of the context's values for it does
    def match_attribute(self, context: ClientContext, rs: RolloutStrategy) -> bool:
        for attr in rs.attributes:
            supplied = context.get_attr_values(attr.field_name)

            # an absent date or date-time (or an empty "now") is today / now
            if supplied is None or (len(supplied) == 0 and attr.field_name.lower() == 'now'):
                now = datetime.datetime.now(datetime.timezone.utc)
                if attr.field_type == RolloutStrategyFieldType.Date:
                    supplied = [now.strftime('%Y-%m-%d')]
                elif attr.field_type == RolloutStrategyFieldType.Datetime:
                    supplied = [now.isoformat()]

            if supplied is None:
                return False

            supplied = [v for v in supplied if v is not None]
            if not supplied:
                return False

            matcher = self._matcherRepository.find_matcher(attr)
            if not _any(supplied, lambda v: matcher.match(v, attr)):
                return False

        return True

    @staticmethod
    def determine_percentage_key(context: ClientContext, rs: RolloutStrategy) -> str:
        if not rs.has_percentage_attributes:
            return context.default_percentage_key

        return "$".join(_percentage_attribute_text(context.get_attr_values(name)) for name in rs.percentage_attributes)
