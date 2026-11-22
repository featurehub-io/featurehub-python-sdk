import tomllib
from pathlib import Path
from unittest import TestCase

from featurehub_sdk.version import sdk_version


class VersionTest(TestCase):
    def test_sdk_version_matches_package_version(self):
        # the version is sent to the server in X-SDK-Version, so it must match the published package
        pyproject = Path(__file__).parents[2] / "pyproject.toml"
        with pyproject.open("rb") as f:
            self.assertEqual(tomllib.load(f)["project"]["version"], sdk_version)
