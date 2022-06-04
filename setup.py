from setuptools import setup

from featurehub_sdk.version import sdk_version

setup(
    name='featurehub-python-sdk',
    version=sdk_version,
    description='Official Python SDK for FeatureHub',
    author='FeatureHub.io',
    author_email='info@featurehub.io',
    packages=['featurehub_sdk'],
    install_requires=['urllib3==1.26.*',
                      'sseclient-py==1.7.*',
                      'murmurhash2==0.2.*',
                      'node_semver==0.8.*'],
)
