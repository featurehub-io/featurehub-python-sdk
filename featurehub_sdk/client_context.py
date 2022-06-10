from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Optional, Any
import json
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
    def values(self) -> Optional[list[Any]]:
        return self._attr.get('values')

    @property
    def float_values(self) -> list[float]:
        return list(map(lambda x: float(x), filter(lambda x: x is not None, self.values)))

    @property
    def str_values(self) -> list[str]:
        return list(map(lambda x: str(x), filter(lambda x: x is not None, self.values)))

    @property
    def field_type(self) -> RolloutStrategyFieldType:
        return RolloutStrategyFieldType(self._attr.get('type'))


class RolloutStrategy:
    _attr: dict
    _attributes: list[RolloutStrategyAttribute]

    def __init__(self, attr: dict):
        self._attr = attr

        rsa = self._attr.get('attributes')
        self._attributes = list(map(lambda x: RolloutStrategyAttribute(x), list(rsa))) if rsa else []

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
    def percentage_attributes(self) -> list[str]:
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
    def attributes(self) -> list[RolloutStrategyAttribute]:
        return self._attributes

    @property
    def has_attributes(self) -> bool:
        return len(self._attributes) > 0

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

    def apply(self, strategies: list[RolloutStrategy], key: str, feature_id: str, context: "ClientContext") -> Applied:
        pass

    def notify(self, cmd: str, data):
        pass

class ClientContext:
    """holds client context"""
    _attributes: dict[str, object]
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

    def user_key(self, value: str) -> ClientContext:
        self._attributes[ClientContext.USER_KEY] = value
        return self

    def session_key(self, value: str) -> ClientContext:
        self._attributes[ClientContext.SESSION] = value
        return self

    def country(self, value: StrategyAttributeCountryName) -> ClientContext:
        self._attributes[ClientContext.COUNTRY] = value
        return self

    def device(self, value: StrategyAttributeDeviceName) -> ClientContext:
        self._attributes[ClientContext.DEVICE] = value
        return self

    def platform(self, value: StrategyAttributePlatformName) -> ClientContext:
        self._attributes[ClientContext.PLATFORM] = value
        return self

    def version(self, version: str) -> ClientContext:
        self._attributes[ClientContext.VERSION] = version
        return self

    def attribute_values(self, key: str, values: list[str]) -> ClientContext:
        self._attributes[key] = values
        return self

    def clear(self) -> ClientContext:
        self._attributes.clear()
        return self

    def get_attr(self, key: str, default_value: Optional[str] = None) -> Optional[object]:
        if key in self._attributes:
            return self._attributes.get(key)
        return default_value

    @property
    def default_percentage_key(self) -> str:
        return self.get_attr(ClientContext.SESSION) if self.get_attr(ClientContext.SESSION) \
            else str(self.get_attr(ClientContext.USER_KEY))

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

    async def close(self):
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

    async def close(self):
        self._edge.close()

    def feature(self, name: str) -> FeatureState:
        return self._repository.feature(name).with_context(self)


class ServerEvalFeatureContext(ClientContext):
    # server eval feature context needs to evaluate the context on the server, so we need to wrap up the
    # context in a bunch of url encoded key value pairs and send it off to the edge service to be updated and
    # refreshed
    _old_header: Optional[str] = None
    _current_edge: Optional[EdgeService]

    def __init__(self, repo: InternalFeatureRepository, edge: EdgeService):
        super().__init__(repo)
        self._current_edge = edge

    def _pick_first(self, v: object):
        return v[0] if isinstance(v, list) else v

    async def build(self) -> ClientContext:
        new_header = "&".join("=".join((k, urllib.parse.quote(str(self._pick_first(v))))) for k,v in self._attributes.items())

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

    async def close(self):
        if self._current_edge:
            self._current_edge.close()
            self._current_edge = None
            self._old_header = None
