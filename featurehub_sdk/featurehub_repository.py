from typing import Optional

from featurehub_sdk.fh_state_base_holder import FeatureStateHolder


class FeatureHubRepository:
    features: dict[str, FeatureStateHolder] = {} #do we need this to be private and expose it as a getter method?
    _ready: bool

    def notify(self, status: str, data: Optional[list[dict]]):
        if status == 'FEATURES':
            self.__update_features(data)
            self._ready = True
        elif status == 'FAILED':
            self._ready = False

    def __update_features(self, data: list[dict]):
        if data:
            for feature_state in data:
                self.__update_feature_state(feature_state)

    def __update_feature_state(self, feature_state):
        if not feature_state or not feature_state['key']:
            return

        # check if feature already in the dictionary, if not add to the dictionary
        holder = self.features.get(feature_state['key'])
        if not holder:
            new_feature = FeatureStateHolder(feature_state['key'], feature_state, None, None)
            self.features[feature_state['key']] = new_feature
            return

        # if feature is in the dictionary, check if version has changed
        elif feature_state.get('version') < holder.get_version():
            return
        elif feature_state.get('version') == holder.get_version() and feature_state.get('value') == holder.get_value():
            return

        holder.set_feature_state(feature_state)

    def is_ready(self):
        return self._ready

    def feature(self, key) -> FeatureStateHolder:
        # we follow the standard as per other SDKs, if the key doesn't exist, we create it so the
        # chain of repository.feature(X).get_flag() for example works but returns None and doesn't explode

        fs = self.features.get(key)

        if fs is None:
            fs = FeatureStateHolder(key, None, None, None)
            self.features[key] = fs

        return fs


    def not_ready(self):
        _ready = False
