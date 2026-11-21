from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Callable, Optional, Any, Dict, List
import json
import math
import urllib.parse
import asyncio

from featurehub_sdk.edge_service import EdgeService
from featurehub_sdk.interceptors import InterceptorValue
from featurehub_sdk.strategy_attribute_country_name import StrategyAttributeCountryName
from featurehub_sdk.strategy_attribute_device_name import StrategyAttributeDeviceName
from featurehub_sdk.strategy_attribute_platform_name import StrategyAttributePlatformName


class FeatureState:
    # Python can't cope with circular dependencies, which is why this is here, FeatureState/Context are a tree
    # structure of each other, e.g. feature('X') -> raw value, ctx.feature('X').withContext(ctx).get_boolean()
    @property
    def get_value(self):
        return ""

    @property
    def locked(self):
        return False

    @property
    def id(self):
        return ""

    @property
    def get_version(self) -> int:
        return -1

    @property
    def get_key(self) -> str:
        return ""

    @property
    def get_string(self) -> Optional[str]:
        return None

    @property
    def get_number(self) -> Optional[Decimal]:
        return None

    @property
    def get_raw_json(self) -> Optional[str]:
        return None

    @property
    def get_boolean(self) -> Optional[bool]:
        return None

    @property
    def get_flag(self) -> Optional[bool]:
        return None

    @property
    def is_enabled(self) -> bool:
        return False

    @property
    def is_set(self) -> bool:
        return False

    @property
    def exists(self) -> bool:
        return False

    @property
    def key(self) -> str:
        return ""

    def with_context(self, ctx: ClientContext) -> "FeatureState":
        pass

# the RolloutX are normally generated from OpenAPI


class RolloutStrategyAttributeConditional(Enum):
    Equals = 'EQUALS'
    EndsWith = 'ENDS_WITH'
    StartsWith = 'STARTS_WITH'
    Greater = 'GREATER'
    GreaterEquals = 'GREATER_EQUALS'
    Less = 'LESS'
    LessEquals = 'LESS_EQUALS'
    NotEquals = 'NOT_EQUALS'
    Includes = 'INCLUDES'
    Excludes = 'EXCLUDES'
    Regex = 'REGEX'


class RolloutStrategyFieldType(Enum):
    String = 'STRING'
    SemanticVersion = 'SEMANTIC_VERSION'
    Number = 'NUMBER'
    Date = 'DATE'
    Datetime = 'DATETIME'
    Boolean = 'BOOLEAN'
    IpAddress = 'IP_ADDRESS'


class RolloutStrategyAttribute:
    _attr: dict

    def __init__(self, attr: dict):
        self._attr = attr

    @property
    def id(self) -> Optional[str]:
        return self._attr.get('id')

    @property
    def conditional(self) -> RolloutStrategyAttributeConditional:
        return RolloutStrategyAttributeConditional(self._attr.get('conditional'))

    @property
    def field_name(self) -> str:
        return self._attr.get('fieldName')

    @property
    def values(self) -> Optional[List[Any]]:
        return self._attr.get('values')

    @property
    def float_values(self) -> List[float]:
        return list(map(lambda x: float(x), filter(lambda x: x is not None, self.values)))

    @property
    def str_values(self) -> List[str]:
        return list(map(lambda x: str(x), filter(lambda x: x is not None, self.values)))

    @property
    def field_type(self) -> RolloutStrategyFieldType:
        return RolloutStrategyFieldType(self._attr.get('type'))


class RolloutStrategy:
    _attr: dict
    _attributes: List[RolloutStrategyAttribute]
    _has_attributes: bool

    def __init__(self, attr: dict):
        self._attr = attr

        rsa = self._attr.get('attributes')
        self._attributes = list(map(lambda x: RolloutStrategyAttribute(x), list(rsa))) if rsa else []
        # this is calculated a lot, so cache it
        self._has_attributes = len(self._attributes) > 0

    @property
    def id(self) -> Optional[str]:
        return self._attr.get('id')

    @property
    def name(self) -> Optional[str]:
        return self._attr.get('name')

    @property
    def percentage(self) -> int:
        p = self._attr.get('percentage')
        return int(p) if p is not None else 0

    @property
    def percentage_attributes(self) -> List[str]:
        pa = self._attr.get('percentageAttributes')

        return list(pa) if pa is not None else []

    @property
    def has_percentage_attributes(self) -> bool:
        pa = self._attr.get('percentageAttributes')
        return len(pa) > 0 if pa is not None else False

    @property
    def value(self) -> Optional[Any]:
        return self._attr.get('value')

    @property
    def attributes(self) -> List[RolloutStrategyAttribute]:
        return self._attributes

    @property
    def has_attributes(self) -> bool:
        return self._has_attributes

class Applied:
    _matched: bool
    _value: Any

    def __init__(self, matched: bool, value: Any):
        self._matched = matched
        self._value = value

    @property
    def value(self):
        return self._value

    @property
    def matched(self):
        return self._matched


class Readiness(Enum):
    # NotReady: no features are held. Ready: features are held and current. Stale: features are held and served, but
    # may not be current (a context change is being fetched, or the connection failed or the environment is stale -
    # see the repository's connection_failed and environment_stale). Failed: final, the connection failed before any
    # features were received
    NotReady = 'NotReady'
    Ready = 'Ready'
    Stale = 'Stale'
    Failed = 'Failed'


class InternalFeatureRepository:
    # give me the raw feature from the repository level (top level features, no contexts)
    def feature(self, key: str) -> FeatureState:
        pass

    # is there an interceptor for this feature value?
    def find_interceptor(self, feature_value: str) -> Optional[InterceptorValue]:
        pass

    # is the repo ready? has it had at least one set of features from any source?
    def is_ready(self) -> bool:
        pass

    # set repo to not being ready
    def not_ready(self) -> bool:
        pass

    # the detailed readiness state. repositories that only implement is_ready() report Ready or NotReady
    @property
    def readiness(self) -> Readiness:
        return Readiness.Ready if self.is_ready() else Readiness.NotReady

    # the source says the environment is stale and will send no further updates
    def mark_environment_stale(self):
        pass

    # the connection updating the repository has permanently failed
    @property
    def connection_failed(self) -> bool:
        return False

    # the environment is stale: FeatureHub will send no more updates
    @property
    def environment_stale(self) -> bool:
        return False

    # listener(readiness) is called whenever readiness changes, and at once with the current readiness. repositories
    # that don't support listeners never call it. each returns a function that removes the listener
    def register_readiness_listener(self, listener) -> Callable[[], None]:
        return lambda: None

    # listener() is called once when the connection permanently fails
    def register_connection_failed_listener(self, listener) -> Callable[[], None]:
        return lambda: None

    # listener() is called once when the environment goes stale
    def register_environment_stale_listener(self, listener) -> Callable[[], None]:
        return lambda: None

    def apply(self, strategies: List[RolloutStrategy], key: str, feature_id: str, context: "ClientContext") -> Applied:
        pass

    def notify(self, cmd: str, data: Optional):
        pass

class ClientContext:
    """holds client context"""
    # every attribute is a list of values, which can be of any type (strings, numbers, booleans, datetimes, enums...).
    # they are kept as given, and converted to the type a strategy attribute needs when it is evaluated
    _attributes: Dict[str, List[Any]]
    _repo: InternalFeatureRepository
    USER_KEY = 'userkey'
    SESSION = 'session'
    COUNTRY = 'country'
    DEVICE = 'device'
    PLATFORM = 'platform'
    VERSION = 'version'

    def __init__(self, repo: InternalFeatureRepository):
        self._repository = repo
        self._attributes = {}

    def user_key(self, value: Any) -> ClientContext:
        return self.attribute_values(ClientContext.USER_KEY, value)

    def session_key(self, value: Any) -> ClientContext:
        return self.attribute_values(ClientContext.SESSION, value)

    def country(self, value: StrategyAttributeCountryName) -> ClientContext:
        return self.attribute_values(ClientContext.COUNTRY, value)

    def device(self, value: StrategyAttributeDeviceName) -> ClientContext:
        return self.attribute_values(ClientContext.DEVICE, value)

    def platform(self, value: StrategyAttributePlatformName) -> ClientContext:
        return self.attribute_values(ClientContext.PLATFORM, value)

    def version(self, version: Any) -> ClientContext:
        return self.attribute_values(ClientContext.VERSION, version)

    # values is one value or a list (or tuple or set) of them, of any type. None removes the attribute
    def attribute_values(self, key: str, values: Any) -> ClientContext:
        if values is None:
            self._attributes.pop(key, None)
        elif isinstance(values, (list, tuple, set, frozenset)):
            self._attributes[key] = list(values)
        else:
            self._attributes[key] = [values]
        return self

    def clear(self) -> ClientContext:
        self._attributes.clear()
        return self

    # the first value of an attribute, or default_value if it isn't set or has no values
    def get_attr(self, key: str, default_value: Optional[Any] = None) -> Optional[Any]:
        values = self._attributes.get(key)
        return values[0] if values else default_value

    # all the values of an attribute (a copy), or None if it isn't set
    def get_attr_values(self, key: str) -> Optional[List[Any]]:
        values = self._attributes.get(key)
        return None if values is None else list(values)

    # the session if set, else the userkey; several values are joined with ","
    @property
    def default_percentage_key(self) -> Optional[str]:
        for key in (ClientContext.SESSION, ClientContext.USER_KEY):
            values = self.get_attr_values(key)
            if values and (len(values) > 1 or values[0] not in (None, '')):
                return ','.join('' if v is None else wire_value(v) for v in values)
        return None

    def is_enabled(self, name: str) -> bool:
        return self.feature(name).is_enabled

    def feature(self, name: str) -> FeatureState:
        # context never matters as the repository always reflects the correctly evaluated state
        return self._repository.feature(name)

    def is_set(self, name: str) -> bool:
        return self.feature(name).is_set

    def get_number(self, name: str) -> Optional[Decimal]:
        return self.feature(name).get_number

    def get_string(self, name: str) -> Optional[str]:
        return self.feature(name).get_string

    def get_json(self, name: str) -> Optional[any]:
        val = self.feature(name).get_raw_json
        return json.loads(val) if val else None

    def get_raw_json(self, name: str) -> Optional[str]:
        return self.feature(name).get_raw_json

    def get_flag(self, name: str) -> Optional[bool]:
        return self.feature(name).get_flag

    def get_boolean(self, name: str) -> Optional[bool]:
        return self.feature(name).get_boolean

    def exists(self, name: str) -> bool:
        return self.feature(name).exists

    async def build(self) -> ClientContext:
        pass

    def build_sync(self) -> ClientContext:
        pass


class ClientEvalFeatureContext(ClientContext):
    _edge: EdgeService

    def __init__(self, repo: InternalFeatureRepository, edge: EdgeService):
        super().__init__(repo)
        self._edge = edge

    async def build(self) -> ClientContext:
        await self._edge.poll()
        return self

    def build_sync(self) -> ClientContext:
        # assumes you have already dont an init yourself and the repository is up and going, you should
        # use this on your server instances
        return self

    def feature(self, name: str) -> FeatureState:
        return self._repository.feature(name).with_context(self)


# how a context attribute value is written when sent to FeatureHub (the protocol's wire_value)
def wire_value(value: Any) -> str:
    if isinstance(value, Enum):
        value = value.value
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, float):
        # as JavaScript's String(n) does
        if math.isnan(value):
            return 'NaN'
        if math.isinf(value):
            return 'Infinity' if value > 0 else '-Infinity'
        return str(int(value)) if value.is_integer() and abs(value) < 1e21 else repr(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            return wire_value(float(value))
        return str(int(value)) if value == value.to_integral_value() else str(value)
    if isinstance(value, datetime):
        # a naive datetime is taken as local time, as datetime.astimezone() does
        return value.astimezone(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


# encoded as JavaScript's encodeURIComponent does
def _encode_component(value: str) -> str:
    return urllib.parse.quote(value, safe="-_.!~*'()")


# the x-featurehub header for server evaluated keys: for each attribute the encoded key + "=" + the encoded values
# joined by ",", sorted and joined by ",". empty if there are no attributes
def x_featurehub_header(attributes: Dict[str, Any]) -> str:
    parts = []
    for key, values in attributes.items():
        if values is None:
            continue
        if not isinstance(values, (list, tuple)):
            values = [values]
        values = [wire_value(v) for v in values if v is not None]
        if not values:
            continue
        parts.append(_encode_component(str(key)) + "=" + _encode_component(",".join(values)))
    return ",".join(sorted(parts))


class ServerEvalFeatureContext(ClientContext):
    # server eval feature context needs to evaluate the context on the server, so we need to wrap up the
    # context in a bunch of url encoded key value pairs and send it off to the edge service to be updated and
    # refreshed
    _old_header: Optional[str] = None
    _current_edge: Optional[EdgeService]

    def __init__(self, repo: InternalFeatureRepository, edge: EdgeService):
        super().__init__(repo)
        self._current_edge = edge

    async def build(self) -> ClientContext:
        new_header = x_featurehub_header(self._attributes)

        if self._old_header is None and len(new_header) == 0:
            await self._current_edge.poll()  # just make sure we have started
        elif new_header != self._old_header: # make sure it changed
            self._old_header = new_header

            self._repository.not_ready()

            await self._current_edge.context_change(new_header)

        return self

    def build_sync(self) -> ClientContext:
        asyncio.run(self.build())
        return self

