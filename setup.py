from setuptools import setup

from featurehub_sdk.version import sdk_version

from pathlib import Path
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()

setup(
    name='featurehub-sdk',
    version=sdk_version,
    license='MIT',
    description='Official Python SDK for FeatureHub',
    url='https://github.com/featurehub-io/featurehub-python-sdk',
    author='FeatureHub.io',
    author_email='info@featurehub.io',
    keywords='feature-flags, feature-toggles, flags, toggles',
    packages=['featurehub_sdk'],
    long_description=long_description,
    long_description_content_type='text/markdown',
    install_requires=['urllib3==2.2.*',
                      'sseclient-py==1.8.*',
                      'murmurhash2==0.2.*',
                      'node_semver==0.9.*'],
)
