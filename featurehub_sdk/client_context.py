from __future__ import annotations

from decimal import Decimal
from typing import Optional, Callable
import json
import urllib.parse

from featurehub_sdk.edge_service import EdgeService
from featurehub_sdk.interceptors import InterceptorValue
from featurehub_sdk.strategy_attribute_country_name import StrategyAttributeCountryName
from featurehub_sdk.strategy_attribute_device_name import StrategyAttributeDeviceName
from featurehub_sdk.strategy_attribute_platform_name import StrategyAttributePlatformName


class FeatureState:
    # Python can't cope with circular dependencies, which is why this is here, FeatureState/Context are a tree
    # structure of each other, e.g. feature('X') -> raw value, ctx.feature('X').withContext(ctx).get_boolean()
    def get_value(self):
        pass

    def get_version(self) -> int:
        pass

    def get_key(self) -> str:
        pass

    def get_string(self) -> Optional[str]:
        pass

    def get_number(self) -> Optional[Decimal]:
        pass

    def get_raw_json(self) -> Optional[str]:
        pass

    def get_boolean(self) -> Optional[bool]:
        pass

    def get_flag(self) -> bool:
        pass

    def is_enabled(self) -> bool:
        pass

    def is_set(self) -> bool:
        pass

    def with_context(self, ctx: ClientContext) -> "FeatureState":
        pass

class InternalFeatureRepository:
    def feature(self, key: str) -> FeatureState:
        pass

    def find_interceptor(self, feature_value: str) -> Optional[InterceptorValue]:
        pass


class ClientContext:
    """holds client context"""
    _attributes: dict[str, object]
    _repo: InternalFeatureRepository

    def __init__(self, repo: InternalFeatureRepository):
        self._repository = repo
        self._attributes = {}

    def user_key(self, value: str) -> ClientContext:
        self._attributes['userkey'] = value
        return self

    def session_key(self, value: str) -> ClientContext:
        self._attributes['session'] = value
        return self

    def country(self, value: StrategyAttributeCountryName) -> ClientContext:
        self._attributes['country'] = value
        return self

    def device(self, value: StrategyAttributeDeviceName) -> ClientContext:
        self._attributes['device'] = value
        return self

    def platform(self, value: StrategyAttributePlatformName) -> ClientContext:
        self._attributes['platform'] = value
        return self

    def version(self, version: str) -> ClientContext:
        self._attributes['version'] = version
        return self

    def attribute_values(self, key: str, values: list[str]) -> ClientContext:
        self._attributes[key] = values
        return self

    def clear(self) -> ClientContext:
        self._attributes.clear()
        return self

    def get_attr(self, key: str, default_value: Optional[str]) -> str:
        if self._attributes[key]:
            return self._attributes.get(key)
        return default_value

    def default_percentage_key(self) -> str:
        return self.get_attr('session') if self._attributes['session'] else self.get_attr('userkey')

    def is_enabled(self, name: str) -> bool:
        return self.feature(name).is_enabled()

    def feature(self, name: str) -> FeatureState:
        # context never matters as the repository always reflects the correctly evaluated state
        return self._repository.feature(name)

    def is_set(self, name: str) -> bool:
        return self.feature(name).is_set()

    def get_number(self, name: str) -> Optional[Decimal]:
        return self.feature(name).get_number()

    def get_string(self, name: str) -> Optional[str]:
        return self.feature(name).get_string()

    def get_json(self, name: str) -> Optional[any]:
        val = self.feature(name).get_raw_json()
        return None if not val else json.loads(val)

    def get_raw_json(self, name: str) -> Optional[str]:
        return self.feature(name).get_raw_json()

    def get_flag(self, name: str) -> Optional[bool]:
        return self.feature(name).get_flag()

    def get_boolean(self, name: str) -> Optional[bool]:
        return self.feature(name).get_boolean()

    async def build(self) -> ClientContext:
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

    async def close(self):
        self._edge.close()

    def feature(self, name: str) -> FeatureState:
        return self._repository.feature(name).with_context(self)


class ServerEvalFeatureContext(ClientContext):
    # server eval feature context needs to evaluate the context on the server, so we need to wrap up the
    # context in a bunch of url encoded key value pairs and send it off to the edge service to be updated and
    # refreshed
    _edge_provider: Callable[[], EdgeService]
    _old_header: Optional[str]
    _current_edge: Optional[EdgeService]

    def __init__(self, repo: InternalFeatureRepository, edge_provider: Callable[[], EdgeService]):
        super().__init__(repo)
        self._edge_provider = edge_provider

    async def build(self) -> ClientContext:
        new_header = "&".join("=".join((k, urllib.parse.quote(str(v)))) for k,v in self._attributes.items())

        if new_header != self._old_header:
            self._old_header = new_header
            self._repository.not_ready()

            if self._current_edge is None:
                self._current_edge = self._edge_provider()

            await self._current_edge.context_change(new_header)

        return self

    async def close(self):
        if self._current_edge:
            self._current_edge.close()
            self._current_edge = None
            self._old_header = None
