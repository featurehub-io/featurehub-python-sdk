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
            new_feature = FeatureStateHolder(feature_state)
            self.features[feature_state['key']] = new_feature
            return

        # if feature is in the dictionary, check if version has changed
        elif feature_state['version'] < holder.version:
            return
        elif feature_state['version'] == holder.version and feature_state['value'] == holder.value:
            return

        holder.set_feature_state(feature_state)

    def is_ready(self):
        return self._ready

    def feature(self, name) -> FeatureStateHolder:
        return self.features.get(name)

    def not_ready(self):
        _ready = False
