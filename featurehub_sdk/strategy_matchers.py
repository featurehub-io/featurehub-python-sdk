import datetime
from typing import Optional

import re

from semver import cmp
import math
from murmurhash2 import murmurhash3
from ipaddress import ip_address, ip_network

from featurehub_sdk.client_context import ClientContext, RolloutStrategyAttributeConditional, \
    RolloutStrategyFieldType, RolloutStrategy, RolloutStrategyAttribute, Applied


class PercentageCalculator:
    def determine_client_percentage(self, percentage_text: str, feature_id: str) -> float:
        pass


class Murmur3PercentageCalculator(PercentageCalculator):
    MAX_PERCENTAGE = 1000000
    SEED = 0

    def determine_client_percentage(self, percentage_text: str, feature_id: str) -> float:
        result = murmurhash3(bytes(percentage_text + feature_id, 'utf-8'), Murmur3PercentageCalculator.SEED)
        return math.floor(result / math.pow(2, 32) * Murmur3PercentageCalculator.MAX_PERCENTAGE)


class StrategyMatcher:
    def match(self, supplied_value: str, attr: RolloutStrategyAttribute) -> bool:
        pass


class MatcherRepository:
    def find_matcher(self, attr: RolloutStrategyAttribute) -> StrategyMatcher:
        pass


class FallthroughMatcher(StrategyMatcher):
    def match(self, supplied_value: str, attr: RolloutStrategyAttribute) -> bool:
        return False


class BooleanMatcher(StrategyMatcher):
    def match(self, supplied_value: str, attr: RolloutStrategyAttribute) -> bool:
        val = 'true' == supplied_value.lower()

        if attr.conditional == RolloutStrategyAttributeConditional.Equals:
            return val == (str(attr.values[0]).lower() == 'true')

        if attr.conditional == RolloutStrategyAttributeConditional.NotEquals:
            return val != (str(attr.values[0]).lower() == 'true')

        return False


class StringMatcher(StrategyMatcher):
    def match(self, supplied_value: str, attr: RolloutStrategyAttribute) -> bool:
        vals = attr.str_values

        # match was only introduced in python 3.10 so...
        if attr.conditional == RolloutStrategyAttributeConditional.Equals:
            return next(filter(lambda x: supplied_value == x, vals), None) is not None
        elif attr.conditional == RolloutStrategyAttributeConditional.EndsWith:
            return next(filter(lambda x: supplied_value.endswith(x), vals), None) is not None
        elif attr.conditional == RolloutStrategyAttributeConditional.StartsWith:
            return next(filter(lambda x: supplied_value.startswith(x), vals), None) is not None
        elif attr.conditional == RolloutStrategyAttributeConditional.Greater:
            return next(filter(lambda x: supplied_value > x, vals), None) is not None
        elif attr.conditional == RolloutStrategyAttributeConditional.GreaterEquals:
            return next(filter(lambda x: supplied_value >= x, vals), None) is not None
        elif attr.conditional == RolloutStrategyAttributeConditional.Less:
            return next(filter(lambda x: supplied_value < x, vals), None) is not None
        elif attr.conditional == RolloutStrategyAttributeConditional.LessEquals:
            return next(filter(lambda x: supplied_value <= x, vals), None) is not None
        elif attr.conditional == RolloutStrategyAttributeConditional.Includes:
            return next(filter(lambda x: x in supplied_value, vals), None) is not None
        elif attr.conditional == RolloutStrategyAttributeConditional.Excludes:
            return next(filter(lambda x: x in supplied_value, vals), None) is None
        elif attr.conditional == RolloutStrategyAttributeConditional.Regex:
            return next(filter(lambda x: re.search(x, supplied_value), vals), None) is not None
        elif attr.conditional == RolloutStrategyAttributeConditional.NotEquals:
            return next(filter(lambda x: supplied_value == x, vals), None) is None

        return False


# we are not doing Date or DateTime matcher but treating those as plain strings


class NumberMatcher(StrategyMatcher):
    def match(self, supplied_value: str, attr: RolloutStrategyAttribute) -> bool:
        try:
            parsed_val = float(supplied_value)

            # these we treat as strings
            if attr.conditional == RolloutStrategyAttributeConditional.EndsWith:
                return next(filter(lambda x: supplied_value.endswith(x), attr.str_values), None) is not None
            elif attr.conditional == RolloutStrategyAttributeConditional.StartsWith:
                return next(filter(lambda x: supplied_value.startswith(x), attr.str_values), None) is not None
            elif attr.conditional == RolloutStrategyAttributeConditional.Regex:
                return next(filter(lambda x: re.search(x, supplied_value), attr.str_values), None) is not None
            else:  # the rest we treat as floats
                vals = attr.float_values

                # match was only introduced in python 3.10 so...
                if attr.conditional == RolloutStrategyAttributeConditional.Equals or \
                        attr.conditional == RolloutStrategyAttributeConditional.Includes:
                    return next(filter(lambda x: parsed_val == x, vals), None) is not None
                elif attr.conditional == RolloutStrategyAttributeConditional.Greater:
                    return next(filter(lambda x: parsed_val > x, vals), None) is not None
                elif attr.conditional == RolloutStrategyAttributeConditional.GreaterEquals:
                    return next(filter(lambda x: parsed_val >= x, vals), None) is not None
                elif attr.conditional == RolloutStrategyAttributeConditional.Less:
                    return next(filter(lambda x: parsed_val < x, vals), None) is not None
                elif attr.conditional == RolloutStrategyAttributeConditional.LessEquals:
                    return next(filter(lambda x: parsed_val <= x, vals), None) is not None
                elif attr.conditional == RolloutStrategyAttributeConditional.NotEquals or \
                        attr.conditional == RolloutStrategyAttributeConditional.Excludes:
                    return next(filter(lambda x: parsed_val == x, vals), None) is None
        except ValueError:
            pass

        return False


class SemanticVersionMatcher(StrategyMatcher):
    def match(self, supplied_value: str, attr: RolloutStrategyAttribute) -> bool:
        vals = attr.str_values

        if attr.conditional == RolloutStrategyAttributeConditional.Includes \
                or attr.conditional == RolloutStrategyAttributeConditional.Equals:
            return next(filter(lambda x: cmp(supplied_value, "==", x, True), vals), None) is not None
        elif attr.conditional == RolloutStrategyAttributeConditional.Excludes \
                or attr.conditional == RolloutStrategyAttributeConditional.NotEquals:
            return next(filter(lambda x: cmp(supplied_value, "==", x, True), vals), None) is None
        elif attr.conditional == RolloutStrategyAttributeConditional.Greater:
            return next(filter(lambda x: cmp(supplied_value, ">", x, True), vals), None) is not None
        elif attr.conditional == RolloutStrategyAttributeConditional.GreaterEquals:
            return next(filter(lambda x: cmp(supplied_value, ">=", x, True), vals), None) is not None
        elif attr.conditional == RolloutStrategyAttributeConditional.Less:
            return next(filter(lambda x: cmp(supplied_value, "<", x, True), vals), None) is not None
        elif attr.conditional == RolloutStrategyAttributeConditional.LessEquals:
            return next(filter(lambda x: cmp(supplied_value, "<=", x, True), vals), None) is not None

        return False


class IPNetworkMatcher(StrategyMatcher):
    def match(self, supplied_value: str, attr: RolloutStrategyAttribute) -> bool:

        if attr.conditional == RolloutStrategyAttributeConditional.Includes \
                or attr.conditional == RolloutStrategyAttributeConditional.Equals:
            return next(filter(lambda x: ip_address(supplied_value) in ip_network(x), attr.values), None) is not None
        elif attr.conditional == RolloutStrategyAttributeConditional.Excludes \
                or attr.conditional == RolloutStrategyAttributeConditional.NotEquals:
            return next(filter(lambda x: ip_address(supplied_value) in ip_network(x), attr.values), None) is None

        return False


class MatcherRegistry(MatcherRepository):
    def find_matcher(self, attr: RolloutStrategyAttribute) -> StrategyMatcher:
        if attr.field_type == RolloutStrategyFieldType.String or \
                attr.field_type == RolloutStrategyFieldType.Date or \
                attr.field_type == RolloutStrategyFieldType.Datetime:
            return StringMatcher()

        if attr.field_type == RolloutStrategyFieldType.SemanticVersion:
            return SemanticVersionMatcher()

        if attr.field_type == RolloutStrategyFieldType.Number:
            return NumberMatcher()

        if attr.field_type == RolloutStrategyFieldType.Boolean:
            return BooleanMatcher()

        if attr.field_type == RolloutStrategyFieldType.IpAddress:
            return IPNetworkMatcher()

        return FallthroughMatcher()


class ApplyFeature:
    _percentageCalculator: PercentageCalculator
    _matcherRepository: MatcherRepository

    def __init__(self, percentage_calculator: Optional[PercentageCalculator] = None,
                 matcher_repository: Optional[MatcherRepository] = None):
        self._percentageCalculator = percentage_calculator if percentage_calculator is not None \
            else Murmur3PercentageCalculator()
        self._matcherRepository = matcher_repository if matcher_repository is not None else MatcherRegistry()

    def apply(self, strategies: list[RolloutStrategy], key: str, feature_value_id: str,
              context: ClientContext) -> Applied:
        if context is None or strategies is None or len(strategies) == 0:
            return Applied(False, None)

        percentage: Optional[float] = None
        percentage_key: Optional[str] = None
        base_percentage: dict[str, float] = {}
        default_percentage_key = context.default_percentage_key

        for rsi in strategies:
            if rsi.percentage != 0 and (default_percentage_key is not None or
                                        rsi.has_percentage_attributes):
                new_percentage_key = self.determine_percentage_key(context, rsi)

                if new_percentage_key not in base_percentage:
                    base_percentage[new_percentage_key] = 0

                base_percentage_val = base_percentage.get(new_percentage_key)

                if percentage is None or new_percentage_key != percentage_key:
                    percentage_key = new_percentage_key
                    percentage = self._percentageCalculator.determine_client_percentage(percentage_key,
                                                                                        feature_value_id)

                    use_base_percentage = 0 if rsi.has_attributes else base_percentage_val

                    # if the percentage is lower than the user's key/feature-id then apply it
                    if percentage <= (use_base_percentage + rsi.percentage):
                        if (not rsi.has_attributes) or (rsi.has_attributes and self.match_attribute(context, rsi)):
                            return Applied(True, rsi.value)

                    if not rsi.has_attributes:
                        base_percentage[percentage_key] = base_percentage.get(percentage_key) + rsi.percentage

            if rsi.percentage == 0 and rsi.has_attributes and self.match_attribute(context, rsi):
                return Applied(True, rsi.value)

        return Applied(False, None)

    def match_attribute(self, context: ClientContext, rs: RolloutStrategy) -> bool:
        for attr in rs.attributes:
            supplied_value = context.get_attr(attr.field_name)
            if supplied_value is None and attr.field_name.lower() == 'now':
                if attr.field_type == RolloutStrategyFieldType.Date:
                    supplied_value = datetime.datetime.utcnow().isoformat()[0:10]
                elif attr.field_type == RolloutStrategyFieldType.Datetime:
                    supplied_value = datetime.datetime.utcnow().isoformat()

            if attr.values is None and supplied_value is None:
                if attr.conditional != RolloutStrategyAttributeConditional.Equals:
                    return False

                continue  # skip this loop

            if attr.values is None or supplied_value is None:
                return False

            if not self._matcherRepository.find_matcher(attr).match(supplied_value, attr):
                return False

        return True

    @staticmethod
    def determine_percentage_key(context: ClientContext, rs: RolloutStrategy) -> str:
        if not rs.has_percentage_attributes:
            return context.default_percentage_key

        return "$".join(list(map(lambda x:
                                 str(context.get_attr(x, '<none>')), rs.percentage_attributes)))
