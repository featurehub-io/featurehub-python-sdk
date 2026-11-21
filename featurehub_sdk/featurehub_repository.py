import logging
import threading
from typing import Callable, Optional, List, Dict

from featurehub_sdk.client_context import InternalFeatureRepository, ClientContext, Applied, RolloutStrategy, Readiness
from featurehub_sdk.fh_state_base_holder import FeatureStateHolder
from featurehub_sdk.interceptors import ValueInterceptor, InterceptorValue
from featurehub_sdk.strategy_matchers import ApplyFeature

log = logging.getLogger('featurehub_sdk')

ReadinessListener = Callable[[Readiness], None]
EventListener = Callable[[], None]


class FeatureHubRepository(InternalFeatureRepository):
    features: Dict[str, FeatureStateHolder] # do we need this to be private and expose it as a getter method?
    _readiness: Readiness
    _environment_stale: bool
    _connection_failed: bool
    _had_features: bool
    _lock: threading.RLock
    _readiness_listeners: List[ReadinessListener]
    _connection_failed_listeners: List[EventListener]
    _environment_stale_listeners: List[EventListener]
    _interceptors: List[ValueInterceptor]
    _strategy_matcher: ApplyFeature

    def __init__(self, apply_features: Optional[ApplyFeature] = None):
        self._strategy_matcher = apply_features if apply_features is not None else ApplyFeature()
        self._interceptors = []
        self.features = {}
        self._readiness = Readiness.NotReady
        self._environment_stale = False
        # the connection updating the repository has permanently failed (separate from readiness)
        self._connection_failed = False
        # a full set of features has been received, so a failure can no longer make readiness Failed
        self._had_features = False
        # notifications come from the edge service's thread while the application reads and listens on others
        self._lock = threading.RLock()
        self._readiness_listeners = []
        self._connection_failed_listeners = []
        self._environment_stale_listeners = []

    def apply(self, strategies: List[RolloutStrategy], key: str, feature_id: str, context: ClientContext) -> Applied:
        return self._strategy_matcher.apply(strategies, key, feature_id, context)

    def notify(self, status: str, data: Optional):
        with self._lock:
            before = self._readiness
            events = []
            broadcast = self.__apply_notification(status, data, events)
            after = self._readiness
        # listeners are called once the change is complete, outside the lock, so they see a consistent repository
        for listeners in events:
            self.__call_listeners(listeners)
        if broadcast or after != before:
            self.__call_listeners(self._readiness_listeners, after)

    # must be called holding self._lock. returns True if readiness is to be broadcast even if it hasn't changed, and
    # adds the listener lists for any events raised to events
    def __apply_notification(self, status: str, data: Optional, events: list) -> bool:
        if status in ('failed', 'failure'):
            # the connection has permanently failed. before any features readiness is Failed; after them it is Stale
            # and the last features keep being served
            if self._connection_failed:
                return False
            self._connection_failed = True
            events.append(self._connection_failed_listeners)
            if not self._had_features:
                if self._readiness == Readiness.NotReady:
                    self._readiness = Readiness.Failed
            elif self._readiness == Readiness.Ready:
                self._readiness = Readiness.Stale
            return False

        if data is None:  # includes bye: the connection is being re-established, nothing changes
            return False

        if status == 'features':
            if not isinstance(data, list):  # not a full set, so nothing is removed and readiness doesn't change
                log.error("ignoring featurehub features that are not a list: %r", data)
                return False
            self.__update_features(data)
            self._had_features = True
            if self._readiness == Readiness.NotReady:
                self._readiness = Readiness.Ready
            elif self._readiness == Readiness.Stale and not (self._connection_failed or self._environment_stale):
                # e.g. a context change's features have arrived. once the connection has failed or the environment
                # is stale nothing will bring the features up to date, so it stays Stale
                self._readiness = Readiness.Ready
            # every full set that leaves it Ready is broadcast, so anything waiting for the next ready wakes up
            return self._readiness == Readiness.Ready
        elif status == 'feature':
            self.__update_feature_state(data)
        elif status in ('delete_feature', 'deleteFeature'):
            self._delete_feature(data)
        return False

    def mark_environment_stale(self):
        with self._lock:
            if self._environment_stale:
                return
            self._environment_stale = True
            changed = self._readiness == Readiness.Ready
            if changed:
                self._readiness = Readiness.Stale
        self.__call_listeners(self._environment_stale_listeners)
        if changed:
            self.__call_listeners(self._readiness_listeners, Readiness.Stale)

    # listener is called with the new readiness whenever it changes, and each time a full set of features leaves it
    # Ready. it is called at once with the current readiness. returns a function that removes the listener
    def register_readiness_listener(self, listener: ReadinessListener) -> Callable[[], None]:
        with self._lock:
            current = self._readiness
        remove = self.__add_listener(self._readiness_listeners, listener)
        self.__call_listener(listener, current)
        return remove

    # listener is called once, when the connection updating the repository permanently fails (e.g. the API key was
    # rejected); at once if it already has. returns a function that removes the listener
    def register_connection_failed_listener(self, listener: EventListener) -> Callable[[], None]:
        return self.__add_event_listener(self._connection_failed_listeners, listener, lambda: self._connection_failed)

    # listener is called once, when FeatureHub says the environment is stale and will send no more updates; at once if
    # it already has. returns a function that removes the listener
    def register_environment_stale_listener(self, listener: EventListener) -> Callable[[], None]:
        return self.__add_event_listener(self._environment_stale_listeners, listener, lambda: self._environment_stale)

    def __add_event_listener(self, listeners: list, listener: EventListener, happened: Callable[[], bool]):
        with self._lock:
            already = happened()
        remove = self.__add_listener(listeners, listener)
        if already:
            self.__call_listener(listener)
        return remove

    def __add_listener(self, listeners: list, listener) -> Callable[[], None]:
        with self._lock:
            listeners.append(listener)

        def remove():
            with self._lock:
                if listener in listeners:
                    listeners.remove(listener)

        return remove

    def __call_listeners(self, listeners: list, *args):
        with self._lock:
            listeners = list(listeners)  # a listener may add or remove listeners
        for listener in listeners:
            self.__call_listener(listener, *args)

    @staticmethod
    def __call_listener(listener, *args):
        try:
            listener(*args)
        except Exception:
            # one failing listener mustn't stop the others, or the edge service delivering the change
            log.exception("featurehub repository listener failed")

    @property
    def environment_stale(self) -> bool:
        return self._environment_stale

    @property
    def connection_failed(self) -> bool:
        return self._connection_failed

    @property
    def readiness(self) -> Readiness:
        return self._readiness

    def _delete_feature(self, data: dict):
        feat = self.features.get(data.get('key'))
        if feat:
            feat.set_feature_state(None)

    def __update_features(self, data: List[dict]):
        keys = set()
        for feature_state in data:
            if self.__update_feature_state(feature_state):
                keys.add(feature_state['key'])

        # a full set: features not in it have gone. their holders are kept (empty), as code and contexts may refer
        # to them
        for key, holder in self.features.items():
            if key not in keys and holder.exists:
                holder.set_feature_state(None)

    # applies the feature if it should replace the one held, returns False if the feature is invalid
    def __update_feature_state(self, feature_state) -> bool:
        if not feature_state or not isinstance(feature_state, dict) or not feature_state.get('key'):
            return False

        # version and type are required: without them it isn't a valid feature
        version = feature_state.get('version')
        if isinstance(version, bool) or not isinstance(version, (int, float)) or not feature_state.get('type'):
            return False
        if not isinstance(version, int):  # a JSON number is accepted and truncated
            feature_state['version'] = int(version)

        key = feature_state['key']
        holder = self.features.get(key)
        if not holder:
            self.features[key] = FeatureStateHolder(key, self, feature_state, None, None)
            return True

        held = holder.internal_feature_state
        if held:
            held_version = held.get('version')
            if held_version > feature_state['version']:
                return True
            # the same version is only replaced if something that matters differs: a server evaluated feature
            # changes its value without a version change when the context changes
            if held_version == feature_state['version'] and \
                    all(held.get(f) == feature_state.get(f) for f in ('value', 'v', 'id', 'type')):
                return True

        holder.set_feature_state(feature_state)
        return True

    # True once features have been received and are being served (Ready, or Stale: they may not be current, because a
    # context change is being fetched or the source has stopped for good). see readiness, connection_failed and
    # environment_stale for which
    def is_ready(self):
        return self._readiness in (Readiness.Ready, Readiness.Stale)

    def feature(self, key) -> FeatureStateHolder:
        # we follow the standard as per other SDKs, if the key doesn't exist, we create it so the
        # chain of repository.feature(X).get_flag() for example works but returns None and doesn't explode

        fs = self.features.get(key)

        if fs is None:
            fs = FeatureStateHolder(key, self, None, None, None)
            self.features[key] = fs

        return fs

    # called before a server evaluated context change is fetched: Ready -> Stale. any other readiness stays as it is
    def not_ready(self):
        # the old features are still held and served while the new context's are fetched, so this is Stale (never
        # NotReady) until they arrive
        with self._lock:
            changed = self._readiness == Readiness.Ready
            if changed:
                self._readiness = Readiness.Stale
        if changed:
            self.__call_listeners(self._readiness_listeners, Readiness.Stale)

    def register_interceptor(self, interceptor: ValueInterceptor):
        self._interceptors.append(interceptor)

    def find_interceptor(self, feature_value: str) -> Optional[InterceptorValue]:
        for interceptor in self._interceptors:
            found = interceptor.intercepted_value(feature_value)
            if found is not None:
                return found

    def extract_feature_state(self) -> list:
        # allows you to extract the internal state of value features out and store it outside the repository
        # if you wish
        feats = []

        for k, v in self.features.items():
            data = v.internal_feature_state
            if data:
                feats.append(data)

        return feats
