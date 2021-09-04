from __future__ import annotations

from typing import Optional
import json

from edge_service import EdgeService
from featurehub_repository import FeatureHubRepository
from fh_state_base_holder import FeatureStateBaseHolder
from strategy_attribute_country_name import StrategyAttributeCountryName
from strategy_attribute_device_name import StrategyAttributeDeviceName
from strategy_attribute_platform_name import StrategyAttributePlatformName


class ClientContext:
    """holds client context"""

    def __init__(self, repo: FeatureHubRepository, edge: EdgeService):
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

    def feature(self, name: str) -> FeatureStateBaseHolder:
        return self._repository.feature(name)

    def is_set(self, name: str) -> bool:
        return self.feature(name).is_set()

    def get_number(self, name: str) -> Optional[int, float]:
        return self.feature(name).get_number()

    def get_string(self, name: str) -> Optional[str]:
        return self.feature(name).get_string()

    def get_json(self, name: str) -> Optional[any]:
        val = self.feature(name).get_raw_json()
        return None if not val else json.loads(val)  # is it what we want?

    def get_raw_json(self, name: str) -> Optional[str]:
        return self.feature(name).get_raw_json()

    def get_flag(self, name: str) -> Optional[bool]:
        return self.feature(name).get_flag()

    def get_boolean(self, name: str) -> Optional[bool]:
        return self.feature(name).get_boolean()


class ClientEvalFeatureContext(ClientContext):
    pass


class ServerEvalFeatureContext(ClientContext):
    pass
