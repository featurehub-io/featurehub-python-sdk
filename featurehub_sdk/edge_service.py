import logging
import math
import os
import re
import threading
from typing import Dict, Optional

import urllib3

log = logging.getLogger('featurehub_sdk')


_DURATION_PART = re.compile(r'(\d+(?:\.\d*)?|\.\d+)(ns|us|µs|μs|ms|s|m|h)')
_DURATION_UNITS = {'ns': 1e-9, 'us': 1e-6, 'µs': 1e-6, 'μs': 1e-6, 'ms': 1e-3, 's': 1.0, 'm': 60.0, 'h': 3600.0}


# a duration in seconds, written as Go's time.ParseDuration takes it ("30s", "1m30s", "500ms"). the unit is required,
# except for "0" (featurehub-protocol.yaml providers.environment_variables.durations). raises ValueError otherwise
def parse_duration(value: str) -> float:
    s = value.strip()
    if s in ('0', '+0', '-0'):
        return 0.0
    sign = -1.0 if s.startswith('-') else 1.0
    body = s[1:] if s[:1] in '+-' else s
    position, seconds = 0, 0.0
    while position < len(body):
        part = _DURATION_PART.match(body, position)
        if not part:
            break
        seconds += float(part.group(1)) * _DURATION_UNITS[part.group(2)]
        position = part.end()
    if not body or position != len(body):
        raise ValueError(f"not a duration: {value!r}")
    return sign * seconds


# reads a positive duration (parse_duration) from an environment variable, in seconds, falling back to the default if
# unset or invalid. capped at the longest timeout threading accepts, as waiting for longer raises OverflowError
def _env_seconds(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    try:
        seconds = parse_duration(value)
        if seconds > 0 and math.isfinite(seconds):
            return min(seconds, threading.TIMEOUT_MAX)
    except ValueError:
        pass
    log.warning("ignoring invalid %s=%r, using %ss", name, value, default)
    return default


# reads a positive number (not a duration) from an environment variable, falling back to the default if unset or invalid
def _env_number(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    try:
        number = float(value)
        if number > 0 and math.isfinite(number):
            return number
    except ValueError:
        pass
    log.warning("ignoring invalid %s=%r, using %s", name, value, default)
    return default


# the headers for a request: the application's extra headers, then the SDK's own, which win over an extra header of the
# same name (header names are case-insensitive)
def _request_headers(extra: Optional[Dict[str, str]], sdk_headers: Dict[str, str]) -> urllib3.HTTPHeaderDict:
    headers = urllib3.HTTPHeaderDict(extra or {})
    for name, value in sdk_headers.items():
        headers[name] = value
    return headers


class EdgeService:
    async def poll(self):
        pass

    def client_evaluated(self):
        pass

    def close(self):
        pass

    async def context_change(self, header: str):
        pass

    # called as features are read: a passive poller fetches if its features are older than its interval. it must not
    # block. other edge services do nothing
    def refresh_if_stale(self):
        pass
