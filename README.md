# Official FeatureHub Python SDK.

## Overview
To control the feature flags from the FeatureHub Admin console, either use our [demo](https://demo.featurehub.io) version for evaluation or install the app using our guide [here](https://docs.featurehub.io/featurehub/latest/installation.html)

Versions 3.7+ of Python are supported.

## SDK installation

`pip install featurehub-sdk`


## Options to get feature updates

There are 2 ways to request for feature updates via this SDK:

- **SSE (Server Sent Events) realtime updates mechanism**

  In this mode, you will make a connection to the FeatureHub Edge server using the EventSource (based on urllib3's `sseclient-py`), and any updates to any features will come through in _near realtime_, automatically updating the feature values in the repository. This method is recommended for server applications.

- **FeatureHub polling client (GET request updates)**

    In this mode you can set an interval (from 0 - just once) to any number of seconds between polling. This is more useful for when you have short term single threaded
    processes like command line tools. Batch tools that iterate over data sets and wish to control when updates happen can also benefit from this method.

## Example

Check our example Flask app [here](https://github.com/featurehub-io/featurehub-python-sdk/tree/main/example)

## Quick start

### Connecting to FeatureHub
There are 3 steps to connecting:
1) Copy FeatureHub API Key from the FeatureHub Admin Console
2) Create FeatureHub config
3) Check FeatureHub Repository readiness and request feature state

#### 1. API Key from the FeatureHub Admin Console
Find and copy your API Key from the FeatureHub Admin Console on the API Keys page -
you will use this in your code to configure feature updates for your environments.
It should look similar to this: ```default/71ed3c04-122b-4312-9ea8-06b2b8d6ceac/fsTmCrcZZoGyl56kPHxfKAkbHrJ7xZMKO3dlBiab5IqUXjgKvqpjxYdI8zdXiJqYCpv92Jrki0jY5taE```.
There are two options - a Server Evaluated API Key and a Client Evaluated API Key. More on this [here](https://docs.featurehub.io/#_client_and_server_api_keys)

Client Side evaluation is intended for use in secure environments (such as microservices) and is intended for rapid client side evaluation, per request for example.

Server Side evaluation is more suitable when you are using an _insecure client_. (e.g. command line tool). This also means you evaluate one user per client.

#### 2. Create FeatureHub config:

Create `FeatureHubConfig`. You need to provide the API Key and the URL of the FeatureHub Edge server.

```python3
from featurehub_sdk.featurehub_config import FeatureHubConfig

edge_url = 'http://localhost:8085/'
client_eval_key = 'default/3f7a1a34-642b-4054-a82f-1ca2d14633ed/aH0l9TDXzauYq6rKQzVUPwbzmzGRqe*oPqyYqhUlVC50RxAzSmx'

config = FeatureHubConfig(edge_url, [client_eval_key])
asyncio.run(config.init()) # run async command in sync

```

By default, this SDK will use SSE client. If you decide to use FeatureHub polling client, after initialising the config, you can add this:

```python3
config.use_polling_edge_service(30)
# OR
config.use_polling_edge_service() # uses environment variable FEATUREHUB_POLL_INTERVAL or default of 30 
```

in this case it is configured for requesting an update every 30 seconds.

#### 3. Check FeatureHub Repository readiness and request feature state

Check for FeatureHub Repository readiness:
```python3
 if config.repository().is_ready():
    # do something
```

If you are not intending to use rollout strategies, you can pass empty context to the SDK:

**Synchronous function:**

```python3
    def name_arg(name):
        if config.new_context().build_sync().feature('FEATURE_TITLE_TO_UPPERCASE').get_flag:
            return "HELLO WORLD"
        else:
            return "hello world"
```

**Asynchronous function:**

```python3
async def async_name_arg(name):
        ctx = await config.new_context().build()
        if ctx.feature('FEATURE_TITLE_TO_UPPERCASE').get_flag:
            return "HELLO WORLD"
        else:
            return "hello world"
```


If you are using rollout strategies and targeting rules they are all determined by the active _user context_. In this example we pass `user_key` to the context :

**Synchronous function:**

```python3
    def name_arg(name):
        if config.new_context().user_key(name).build_sync().feature('FEATURE_TITLE_TO_UPPERCASE').get_flag:
            return "HELLO WORLD"
        else:
            return "hello world"
```

**Asynchronous function:**

```python3
async def async_name_arg(name):
        ctx = await config.new_context().user_key(name).build()
        if ctx.feature('FEATURE_TITLE_TO_UPPERCASE').get_flag:
            return "HELLO WORLD"
        else:
            return "hello world"
```

See more options to request feature states [here](https://github.com/featurehub-io/featurehub-python-sdk/blob/main/featurehub_sdk/client_context.py)
