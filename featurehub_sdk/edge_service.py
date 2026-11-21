import logging
import math
import os
import threading
from typing import Dict, Optional

import urllib3

log = logging.getLogger('featurehub_sdk')


# reads a positive number of seconds from an environment variable, falling back to the default if unset or invalid.
# capped at the longest timeout threading accepts, as waiting for longer raises OverflowError
def _env_seconds(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        seconds = float(value)
        if seconds > 0 and math.isfinite(seconds):
            return min(seconds, threading.TIMEOUT_MAX)
    except ValueError:
        pass
    log.warning("ignoring invalid %s=%r, using %ss", name, value, default)
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
