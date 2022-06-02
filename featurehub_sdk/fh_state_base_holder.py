from decimal import Decimal
from typing import Optional

from featurehub_sdk.client_context import ClientContext, FeatureState


# this represents one of 3 things:
# - a legtimate feature state set of data as it has come from the server
# - an empty holder because the user has asked for a feature state that does not exist and we need to
#   provide them with an API that doesn't explode
# - a single hierarchy tree of a feature. When a context is created it needs to hold onto the individual context
#   and teh feature state it refers to, as many different concurrent users could have an active context pointing to
#   that feature. so ctx1 and ctx2 will each get their own copy of a FeatureStateHolder but it stores no actual state,
#   only a reference to the parent holder, that means as new data comes in, the context needs to always refer to the
#   current state, we have no way of searching for all of the instances of context/features and updating them.
class FeatureStateHolder(FeatureState):
    """Holder for features. Wraps raw response with features dictionary"""

    _key: Optional[str]
    _internal_feature_state = {}
    _parent_state: "FeatureStateHolder"
    _ctx: ClientContext

    def __eq__(self, other):
        if not isinstance(other, FeatureStateHolder):
            return NotImplemented
        else:
            fs = self._feature_state()
            o = other._feature_state()
            if fs is None or o is None:
                return False

            # if their id's and versions are the same, they have to be the same
            return fs['id'] == o['id'] and fs['version'] == o['version']

    # we can be initialised with no state when someone request a key that does not exist
    # the parent exists so we can keep track of the original feature when we use contexts
    def __init__(self, key: str, feature_state: Optional = None, parent_state: Optional["FeatureStateHolder"] = None, ctx: Optional[ClientContext] = None):
        super().__init__()

        self._key = key
        self._parent_state = parent_state
        self._ctx = ctx

        if feature_state:
            self.__set_feature_state(feature_state)

    def __set_feature_state(self, feature_state):
        self._internal_feature_state = feature_state

    def __get_value(self, feature_type: Optional[str]) -> Optional[object]:
        # walk up the chain to find the original feature state (if any)
        fs = self._feature_state()

        # if the feature isn't a feature (they have asked for a feature that doesn't exist
        # or the type is wrong, return None
        if fs is None or (feature_type is not None and fs['type'] != feature_type):
            return None

        #     if (this._ctx != null) {
        #       const matched = this._repo.apply(featureState.strategies, this._key, featureState.id, this._ctx);
        #
        #       if (matched.matched) {
        #         return this._castType(type, matched.value);
        #       }
        #     }

        return fs.get('value')

    def with_context(self, ctx: ClientContext) -> FeatureState:
        return FeatureStateHolder(self._key, None, self, ctx)

    def _feature_state(self) -> dict:
        # if we have a feature state, we are essentially at the top of the tree
        # so we return that as the state
        if self._internal_feature_state:
            return self._internal_feature_state

        # if we have a parent state, we are inside a context, so we need to walk up
        # the tree to
        if self._parent_state:
            return self._parent_state._feature_state()

        # this is in fact "None"
        return self._internal_feature_state

    def locked(self):
        fs = self._feature_state()
        return fs.get('l') if fs else False

    def set_feature_state(self, feature_state):
        self.__set_feature_state(feature_state)

    def get_value(self):
        return self.__get_value(None)

    def get_version(self) -> str:
        fs = self._feature_state()
        return fs.get('version') if fs else False

    def get_key(self) -> str:
        return self._key

    def get_string(self) -> Optional[str]:
        return self.__get_value('STRING')

    def get_number(self) -> Optional[Decimal]:
        return self.__get_value('NUMBER')

    def get_raw_json(self) -> Optional[str]:
        return self.__get_value('JSON')

    def get_boolean(self) -> Optional[bool]:
        return self.__get_value('BOOLEAN')

    def get_flag(self) -> bool:
        return self.get_boolean()

    def is_enabled(self) -> bool:
        return self.get_boolean() is True

    def is_set(self) -> bool:
        return self.__get_value(None) is not None

