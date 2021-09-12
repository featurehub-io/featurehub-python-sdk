from setuptools import setup

setup(
    name='featurehub-python-sdk',
    version='1.0',
    description='Official Python SDK for FeatureHub',
    author='FeatureHub.io',
    author_email='info@featurehub.io',
    packages=['featurehub_sdk'],
    install_requires=['httpx[http2]==0.19.*',
                      'respx==0.17.*'],
)
