import logging
import os

log = logging.getLogger('featurehub_sdk')


# reads a positive number of seconds from an environment variable, falling back to the default if unset or invalid
def _env_seconds(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        seconds = float(value)
        if seconds > 0:
            return seconds
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
