import logging
import math
import os
import re
import threading
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote, urlsplit, urlunsplit

import urllib3

log = logging.getLogger('featurehub_sdk')


# the one duration grammar every SDK shares: a single number and a lowercase unit, or 0 (featurehub-protocol.yaml
# providers.environment_variables.durations). deliberately not Go's time.ParseDuration: no compound values, no signs
_DURATION = re.compile(r'0|(?P<number>[0-9]+(\.[0-9]+)?)(?P<unit>ms|s|m|h)')
_DURATION_UNITS = {'ms': 1e-3, 's': 1.0, 'm': 60.0, 'h': 3600.0}
# FEATUREHUB_SSE_BACKOFF_MULTIPLIER is a number, not a duration
_NUMBER = re.compile(r'[0-9]+(\.[0-9]+)?')

# the protocol generation this SDK speaks to Edge (featurehub-protocol.yaml spec.sdk_version), sent as the sdk_version
# query parameter on every request. it changes only when the wire protocol changes, not with the SDK's own version
PROTOCOL_SDK_VERSION = "2"


# a duration in seconds, such as "30s", "500ms", "1.5m" or "1h" (the unit is required, except for "0"), after trimming.
# raises ValueError otherwise
def parse_duration(value: str) -> float:
    match = _DURATION.fullmatch(value.strip())
    if not match:
        raise ValueError(f"not a duration: {value!r}")
    if match.group('unit') is None:  # "0"
        return 0.0
    return float(match.group('number')) * _DURATION_UNITS[match.group('unit')]


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
    if _NUMBER.fullmatch(value.strip()):
        number = float(value)
        if number > 0 and math.isfinite(number):
            return number
    log.warning("ignoring invalid %s=%r, using %s", name, value, default)
    return default


# a request URL to Edge: the host's path with `path` added, then the host's own query string (less any parameter the SDK
# sends itself, so each is sent once), then the SDK's parameters in the order given. the order is fixed
# (featurehub-protocol.yaml featurehub_edge.query_parameters) so equal requests have equal URLs for a CDN. values are
# sent as given, as API keys always have been
def _edge_url(host: str, path: str, params: List[Tuple[str, str]]) -> str:
    parts = urlsplit(host)
    base = parts.path if parts.path.endswith('/') else parts.path + '/'
    names = {name for name, _ in params}
    kept = [p for p in parts.query.split('&') if p and unquote(p.split('=', 1)[0]) not in names]
    query = '&'.join(kept + [f"{name}={value}" for name, value in params])
    return urlunsplit((parts.scheme, parts.netloc, base + path, query, ''))


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
