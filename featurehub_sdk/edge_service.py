import logging
import math
import os
import threading

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


class EdgeService:
    async def poll(self):
        pass

    def client_evaluated(self):
        pass

    def close(self):
        pass

    async def context_change(self, header: str):
        pass
