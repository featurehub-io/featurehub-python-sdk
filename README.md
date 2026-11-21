# Official FeatureHub Python SDK.

## Overview
To control the feature flags from the FeatureHub Admin console, either use our [demo](https://demo.featurehub.io) version for evaluation or install the app using our guide [here](https://docs.featurehub.io/featurehub/latest/installation.html)

Versions 3.11+ of Python are supported.

## SDK installation

`pip install featurehub-sdk`

## Upgrading from 1.x to 2.0

Version 2.0 brings the SDK in line with the [FeatureHub SDK protocol](https://github.com/featurehub-io/featurehub-sdk-docs/blob/main/specs/featurehub-protocol.yaml)
and [rollout strategy](https://github.com/featurehub-io/featurehub-sdk-docs/blob/main/specs/rollout-strategies.yaml)
specifications. Most applications need no code changes, but go through these steps before upgrading.

1. **Use Python 3.11 or later.** Older versions of Python will stay on 1.x.

2. **Server Evaluated API Keys must choose polling.** In 1.x a Server Evaluated key streamed by default, and the
   context was never sent, so FeatureHub evaluated your features without it. In 2.0 there is no default for these
   keys: unless you choose polling, `init()` (and `new_context()`) raise a `ValueError`. Choose it in code:

   ```python3
   config = FeatureHubConfig(edge_url, [server_eval_key])
   config.use_polling_edge_service(30)  # poll every 30 seconds
   ```

   or set the environment variable `FEATUREHUB_POLL_INTERVAL` (for example `FEATUREHUB_POLL_INTERVAL=30`). If you
   create a `StreamingEdgeClient` yourself (for example in a custom edge provider), it now raises a `ValueError` for a
   Server Evaluated key. Client Evaluated keys (those containing `*`) are not affected and still stream by default.

3. **Check your polling intervals.** An interval must be `0` (poll once) or at least 5 seconds; anything else raises a
   `ValueError`. Check calls to `use_polling_edge_service()` and `update_interval()`, `PollingEdgeService` if you create
   it yourself, and the `FEATUREHUB_POLL_INTERVAL` environment variable in every environment you deploy to. A
   `Cache-Control: max-age` from the server below 5 seconds is raised to 5.

4. **Check how you use `is_ready()`.** It is now true whenever features are held, including:
   - while a Server Evaluated context change is being fetched (the previous context's features are still served);
   - after FeatureHub has rejected the API key, if features had already been received;
   - after the environment has gone stale.

   If you used `is_ready()` going false to detect a rejected key, use `config.repository().readiness`,
   `connection_failed` or `environment_stale`, or register a listener (see
   [readiness](#3-check-featurehub-repository-readiness-and-request-feature-state)).

5. **Review rollout strategies whose results may change.** Strategy evaluation now follows the specification, which
   fixes bugs but means some users can get a different value than before, with no change to your code. In the
   FeatureHub Admin console, look for strategies that:
   - **stack percentage rollouts** (two or more percentage strategies on one feature). In 1.x only the first was ever
     applied, so users in the later ones got the default value; they now get the later strategy's value.
   - use **`NOT_EQUALS` or `EXCLUDES` on a semantic version with more than one value.** These now match if the version
     is unequal to *any* of the values, which is almost always true. If you meant "none of these versions", use one
     value per strategy, or `EQUALS` on the versions you want and order the strategies accordingly.
   - use **`BOOLEAN`** attributes. Only `True` or the exact string `"true"` is true, so `"True"` (for example from
     `str(True)`) or `"TRUE"` is now false. Pass Python booleans instead.
   - use **`DATE` or `DATETIME`** attributes. Values are now converted to UTC before being compared (a date-time
     without an offset is local time), and if the context doesn't supply the attribute at all, today's date (or now)
     is used.
   - use **`NUMBER`** attributes with values your application supplies as strings. A string that isn't a plain number
     (such as `"12abc"`) no longer matches anything.
   - compare an attribute (other than a `DATE` or `DATETIME`) that the context doesn't supply. It now never matches,
     even if the strategy has no values for it.

6. **Pass context values in their natural types.** `attribute_values()` (and `user_key()`, `version()` and the other
   well-known setters) now take one value or a list, tuple or set of values of any type - strings, numbers, booleans,
   dates, datetimes or enums - and convert them as each strategy needs. Passing `None` removes the attribute.

7. **Caches in front of FeatureHub Edge.** For Server Evaluated keys the `x-featurehub` header (and so the
   `contextSha` query parameter) is now written as the other SDKs write it. If a proxy or CDN caches Edge responses
   by these, expect cache misses once after upgrading.

8. **Custom repositories and matchers.** `InternalFeatureRepository` has new methods (`readiness`,
   `mark_environment_stale`, `connection_failed`, `environment_stale` and the listener methods), all with default
   implementations, so existing subclasses keep working. A custom `StrategyMatcher` that overrides `match()` keeps
   working; it is now given context values as they were supplied (not always strings).

9. **`node-semver` is no longer installed** with the SDK. If your own code imports `nodesemver`, add it to your own
   dependencies.

New in 2.0 and optional to adopt: extra headers for every request to FeatureHub
(`FeatureHubConfig(..., headers={...})`), readiness and failure listeners, and a configurable streaming backoff
(`FEATUREHUB_STREAMING_BACKOFF_MULTIPLIER`). See [CHANGELOG.md](CHANGELOG.md) for everything that changed.

## Options to get feature updates

There are 2 ways to request for feature updates via this SDK:

- **SSE (Server Sent Events) realtime updates mechanism**

  In this mode, you will make a connection to the FeatureHub Edge server using the EventSource (based on urllib3's `sseclient-py`), and any updates to any features will come through in _near realtime_, automatically updating the feature values in the repository. This method is recommended for server applications.
  It is only available for Client Evaluated API Keys: this SDK does not send the context over streaming, so Server
  Evaluated API Keys must use polling.

- **FeatureHub polling client (GET request updates)**

    In this mode you can set an interval of 0 (poll just once) or any number of seconds from 5 upwards between polling. This is more useful for when you have short term single threaded
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

By default, this SDK will use SSE client for a Client Evaluated API Key. A Server Evaluated API Key has no default: you
must choose polling, either with `config.use_polling_edge_service()` (below) or by setting the environment variable
`FEATUREHUB_POLL_INTERVAL`, otherwise a `ValueError` is raised when the config is initialised. If the SSE connection fails, it reconnects
after a delay that starts at 1 second and doubles on each consecutive failure up to 30 seconds. These can be changed
with the environment variables `FEATUREHUB_STREAMING_INITIAL_RETRY_DELAY` and `FEATUREHUB_STREAMING_MAX_RETRY_DELAY`
(in seconds, at least 0.1) and `FEATUREHUB_STREAMING_BACKOFF_MULTIPLIER` (at least 1). It reconnects if connecting takes
longer than 12 seconds, or if no data arrives on an open stream for 60 seconds; these can be changed (in seconds) with
`FEATUREHUB_STREAMING_CONNECT_TIMEOUT` and `FEATUREHUB_STREAMING_READ_TIMEOUT`. If FeatureHub rejects the API key (any
4xx response) it stops for good.

If you need to send extra headers with every request to FeatureHub (for example for an API gateway or a proxy in front
of it), pass them to the config. The SDK's own headers take precedence over any of the same name.

```python3
config = FeatureHubConfig(edge_url, [client_eval_key], headers={'X-Api-Gateway-Key': 'secret'})
```

If you decide to use FeatureHub polling client, after initialising the config, you can add this:

```python3
config.use_polling_edge_service(30)
# OR
config.use_polling_edge_service() # uses environment variable FEATUREHUB_POLL_INTERVAL or default of 30 
```

in this case it is configured for requesting an update every 30 seconds. The interval must be 0 (request once) or at
least 5 seconds, otherwise a `ValueError` is raised. If FeatureHub responds with a `Cache-Control: max-age`, that
replaces the interval (but never starts polling again if the interval is 0).

Each polling request times out after 12 seconds, which can be changed (in seconds) with the environment variable
`FEATUREHUB_POLLING_TIMEOUT`.

#### 3. Check FeatureHub Repository readiness and request feature state

Check for FeatureHub Repository readiness:
```python3
 if config.repository().is_ready():
    # do something
```

`is_ready()` is true once features have been received. For more detail, `config.repository().readiness` is one of
(from `featurehub_sdk.client_context import Readiness`):

- `Readiness.NotReady`: no features have been received yet
- `Readiness.Ready`: the features are current
- `Readiness.Stale`: the features are still used, but may not be current - either a Server Evaluated context change is
  being fetched, or FeatureHub has stopped sending updates for good. `config.repository().connection_failed` (the API
  key was rejected) and `config.repository().environment_stale` (the environment is stale) say whether it has stopped
- `Readiness.Failed`: the API key was rejected before any features were received

You can also listen for these changes. Each register call returns a function that removes the listener. Listeners are
called on the thread that delivered the change (usually the SDK's polling or streaming thread), so they should return
quickly; an exception in one is logged and doesn't affect the others.

```python3
from featurehub_sdk.client_context import Readiness

repo = config.repository()

# called at once with the current readiness, then whenever it changes (and each time a new set of features arrives
# while it is Ready)
remove = repo.register_readiness_listener(lambda readiness: print(f"features are {readiness.value}"))

# each called once, when it happens (or at once, if it already has)
repo.register_connection_failed_listener(lambda: print("FeatureHub rejected the API key"))
repo.register_environment_stale_listener(lambda: print("the environment is stale, no more updates will arrive"))

remove()  # stop listening
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
