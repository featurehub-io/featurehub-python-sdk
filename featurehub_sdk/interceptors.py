from typing import Optional, Union
import os

# value interceptors are for permanent or contextual feature value overrides, but mostly they are intended for
# permanent ones


class InterceptorValue:
    _val: Optional[object]

    def __init__(self, val: object):
        self._val = val

    def cast(self, expected_type: Optional[str]) -> Union[None, bool, str, float]:
        if expected_type is None or self._val is None:
            return self._val

        if expected_type == 'BOOLEAN':
            return str(self._val).lower().strip() == 'true'
        elif expected_type == 'NUMBER':
            return float(str(self._val))

        return str(self._val)


class ValueInterceptor:
    def intercepted_value(self, feature_key: str) -> Optional[InterceptorValue]:
        pass


class EnvironmentInterceptor(ValueInterceptor):
    _enabled: bool
    # this is an example of an interceptor that when it starts checks the environment for a feature value override
    def __init__(self):
        self._enabled = os.environ.get("FEATUREHUB_POLL_INTERVAL", "false") == "true"

    def sanitize_feature_name(self, feature_key: str) -> str:
        return feature_key.replace(" ", "_")

    def intercepted_value(self, feature_key: str) -> Optional[InterceptorValue]:
        if self._enabled:
            found = os.environ.get(f"FEATUREHUB_{self.sanitize_feature_name(feature_key)}")
            if found is not None:
                return InterceptorValue(found)

        return None

# TODO: should also provide a filesystem or dictionary based value interceptor