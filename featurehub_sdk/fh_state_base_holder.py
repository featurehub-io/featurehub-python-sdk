from decimal import Decimal
from typing import Optional, Union

from featurehub_sdk.client_context import ClientContext, FeatureState, InternalFeatureRepository, RolloutStrategy


# this represents one of 3 things:
# - a legtimate feature state set of data as it has come from the server
# - an empty holder because the user has asked for a feature state that does not exist and we need to
#   provide them with an API that doesn't explode
# - a single hierarchy tree of a feature. When a context is created it needs to hold onto the individual context
#   and teh feature state it refers to, as many different concurrent users could have an active context pointing to
#   that feature. so ctx1 and ctx2 will each get their own copy of a FeatureStateHolder but it stores no actual state,
#   only a reference to the parent holder, that means as new data comes in, the context needs to always refer to the
#   current state, we have no way of searching for all of the instances of context/features and updating them.
from featurehub_sdk.interceptors import InterceptorValue
from typing import List


class FeatureStateHolder(FeatureState):
    """Holder for features. Wraps raw response with features dictionary"""

    _key: Optional[str]
    _internal_feature_state: Optional[dict]
    _parent_state: "FeatureStateHolder"
    _ctx: ClientContext
    _repo: InternalFeatureRepository
    _encoded_strategies: List[RolloutStrategy]

    # we can be initialised with no state when someone request a key that does not exist
    # the parent exists so we can keep track of the original feature when we use contexts
    def __init__(self, key: str,
                 repo: InternalFeatureRepository,
                 feature_state: Optional = None,
                 parent_state: Optional["FeatureStateHolder"] = None,
                 ctx: Optional[ClientContext] = None,
                 ):
        super().__init__()

        self._key = key
        self._parent_state = parent_state
        self._ctx = ctx
        self._repo = repo
        self._encoded_strategies = []
        self._internal_feature_state = None

        if feature_state:
            self.__set_feature_state(feature_state)

    def __set_feature_state(self, feature_state):
        self._internal_feature_state = feature_state if feature_state is not None else {}
        found_strategies = feature_state.get('strategies') if feature_state and feature_state.get('strategies') else []

        self._encoded_strategies = list(map(lambda rs: RolloutStrategy(rs), found_strategies))

    def __get_value(self, feature_type: Optional[str]) -> Union[None, bool, str, float]:
        if not self.locked:
            intercept = self._repo.find_interceptor(self._key)

            if intercept:
                return intercept.cast(feature_type if feature_type else 'STRING')

        # walk up the chain to find the original feature state (if any)
        fs = self._top_feature_state_holder()

        state = fs._feature_state()

        if state is None:
            return None

        # if the feature isn't a feature (they have asked for a feature that doesn't exist
        # or the type is wrong, return None
        if fs is None or (feature_type is not None and fs.feature_type != feature_type):
            return None

        if self._ctx is not None:
            matched = self._repo.apply(fs._encoded_strategies, self._key, fs.id, self._ctx)

            if matched.matched:
                return InterceptorValue(matched.value).cast(feature_type)

        return state.get('value')

    def with_context(self, ctx: ClientContext) -> FeatureState:
        return FeatureStateHolder(self._key, self._repo, None, self, ctx)

    def _top_feature_state_holder(self) -> "FeatureStateHolder":
        if self._parent_state:
            return self._parent_state._top_feature_state_holder()

        return self

    def _feature_state(self) -> dict:
        return self._top_feature_state_holder()._internal_feature_state

    @property
    def id(self) -> Optional[str]:
        return self._feature_state().get('id') if self.exists else None

    @property
    def feature_type(self) -> Optional[str]:
        return self._feature_state().get('type') if self.exists else None

    @property
    def locked(self):
        fs = self._feature_state()
        return fs.get('l') if fs else False

    def set_feature_state(self, feature_state: Optional[dict]):
        self.__set_feature_state(feature_state)

    @property
    def get_value(self):
        return self.__get_value(self.feature_type if self.exists else None)

    @property
    def get_version(self) -> int:
        fs = self._feature_state()
        return fs.get('version') if fs else -1

    @property
    def key(self) -> str:
        return self._key

    @property
    def get_string(self) -> Optional[str]:
        return self.__get_value('STRING')

    @property
    def get_number(self) -> Optional[Decimal]:
        return self.__get_value('NUMBER')

    @property
    def get_raw_json(self) -> Optional[str]:
        return self.__get_value('JSON')

    @property
    def get_boolean(self) -> Optional[bool]:
        return self.__get_value('BOOLEAN')

    @property
    def exists(self) -> bool:
        f = self._feature_state()
        return (f.get('l') is not None) if f else False

    @property
    def get_flag(self) -> Optional[bool]:
        return self.get_boolean

    @property
    def is_enabled(self) -> bool:
        return self.get_boolean is True

    @property
    def is_set(self) -> bool:
        return self.__get_value(self.feature_type) is not None

    def _get_internal_feature_state(self):
        return self._internal_feature_state if self.exists else None

    internal_feature_state = property(_get_internal_feature_state, __set_feature_state)