from typing import Optional

from featurehub_sdk.client_context import InternalFeatureRepository, ClientContext, Applied, RolloutStrategy
from featurehub_sdk.fh_state_base_holder import FeatureStateHolder
from featurehub_sdk.interceptors import ValueInterceptor, InterceptorValue
from featurehub_sdk.strategy_matchers import ApplyFeature


class FeatureHubRepository(InternalFeatureRepository):
    features: dict[str, FeatureStateHolder] # do we need this to be private and expose it as a getter method?
    _ready: bool = False
    _interceptors: list[ValueInterceptor]
    _strategy_matcher: ApplyFeature

    def __init__(self, apply_features: Optional[ApplyFeature] = None):
        self._strategy_matcher = apply_features if apply_features is not None else ApplyFeature()
        self._interceptors = []
        self.features = {}

    def apply(self, strategies: list[RolloutStrategy], key: str, feature_id: str, context: ClientContext) -> Applied:
        return self._strategy_matcher.apply(strategies, key, feature_id, context)

    def notify(self, status: str, data: Optional):
        if status == 'failed':
            self._ready = False
            return

        if data is None:
            return

        if status == 'features':
            self.__update_features(data)
            self._ready = True
        elif status == 'feature':
            self.__update_feature_state(data)
            self._ready = True
        elif status == 'delete_feature':
            self._delete_feature(data)

    def _delete_feature(self, data: dict):
        feat = self.features.get(data['key'])
        if feat:
            feat.set_feature_state(None)

    def __update_features(self, data: list[dict]):
        if data:
            for feature_state in data:
                self.__update_feature_state(feature_state)

    def __update_feature_state(self, feature_state):
        if not feature_state or not feature_state.get('key'):
            return

        # check if feature already in the dictionary, if not add to the dictionary
        holder = self.features.get(feature_state['key'])
        if not holder:
            new_feature = FeatureStateHolder(feature_state['key'], self, feature_state, None, None)
            self.features[feature_state['key']] = new_feature
            return

        # if feature is in the dictionary, check if version has changed
        elif feature_state.get('version') < holder.get_version:
            return
        elif feature_state.get('version') == holder.get_version and feature_state.get('value') == holder.get_value:
            return

        holder.set_feature_state(feature_state)

    def is_ready(self):
        return self._ready

    def feature(self, key) -> FeatureStateHolder:
        # we follow the standard as per other SDKs, if the key doesn't exist, we create it so the
        # chain of repository.feature(X).get_flag() for example works but returns None and doesn't explode

        fs = self.features.get(key)

        if fs is None:
            fs = FeatureStateHolder(key, self, None, None, None)
            self.features[key] = fs

        return fs

    def not_ready(self):
        self._ready = False

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
