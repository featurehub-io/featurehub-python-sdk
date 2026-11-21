# Changelog

* 2.0.0
    - contains breaking changes: see "Upgrading from 1.x to 2.0" in README.md for the steps to check before upgrading
    - requires Python 3.11 or later (tested on 3.11 - 3.15)
    - build moved from setup.py to pyproject.toml and uv
    - fixes for SSE for last-event-id and making streaming more resilient: it reconnects with an increasing delay
      instead of stopping when the server is unavailable, and a bad event or failing listener no longer drops the stream
    - added new environment variables for retry delays: FEATUREHUB_STREAMING_INITIAL_RETRY_DELAY and
      FEATUREHUB_STREAMING_MAX_RETRY_DELAY
    - made polling more resilient to failures, particularly on 1st one: errors are logged and polling continues
    - polling now uses a single worker thread so only one request is ever in flight; poll() and context_change()
      wait for it without blocking the event loop. poll_with_interval() and poll_again() have been removed
    - polling or streaming stopped by a rejected API key or a stale environment is no longer restarted by poll(),
      update_interval() or close()
    - nothing is applied to the repository from a request or stream that was in flight when close() was called
    - polling requests time out after 12 seconds, configurable with the FEATUREHUB_POLLING_TIMEOUT environment variable
    - update_interval() takes effect immediately on a running poller, and starts polling if the interval was 0
    - the streaming client can be polled again after close(), and releases its connection when a stream ends
    - streaming reconnects after a connect timeout (12s) or a quiet stream (60s), configurable with
      FEATUREHUB_STREAMING_CONNECT_TIMEOUT and FEATUREHUB_STREAMING_READ_TIMEOUT
    - streaming notifies the repository of failure on a rejected API key, as polling does
    - updated dependencies based on trivy scan
    - aligned with the FeatureHub SDK protocol specification:
        - the repository has a `readiness` of NotReady, Ready, Stale or Failed, and `connection_failed` and
          `environment_stale` flags. A rejected key or a stale environment after features makes it Stale for good (it
          keeps serving the last features, and `is_ready()` stays true); a rejected key before features makes it
          Failed. A server evaluated context change makes it Stale (not not-ready) until the new context's features
          arrive. Listeners can be registered for readiness changes (`register_readiness_listener`), and for the
          connection failing (`register_connection_failed_listener`) or the environment going stale
          (`register_environment_stale_listener`). A full set of features now removes features that are not in it, and a
          feature with the same version replaces the one held if its value, strategy, id or type differs
        - the x-featurehub header (server evaluated keys) is now sorted and comma separated, encodes keys as well as
          values, sends every value of an attribute, and writes booleans, numbers, enums and datetimes as the other
          SDKs do
        - polling with several API keys gives the repository all their features as one set; a response body that
          isn't a list of environments is logged and ignored, as is a features notification that isn't a list
        - a context change clears the polling etag, and on a closed poller fetches once and stays closed;
          update_interval() no longer starts polling that was never started
        - server evaluated keys have no default: polling must be chosen with use_polling_edge_service() or by setting
          FEATUREHUB_POLL_INTERVAL, and `StreamingEdgeClient` rejects them (the context isn't sent over streaming, so
          FeatureHub would evaluate them without it)
        - any 4xx from FeatureHub stops polling or streaming for good, as does a failure event on the stream
        - extra headers can be passed to `FeatureHubConfig(headers=...)` and are sent with every request
        - polling intervals must be 0 or at least 5 seconds (a `ValueError` otherwise); a max-age is raised to 5 seconds
          and doesn't start polling with an interval of 0; a 304 is no longer logged as an error; once the environment
          is stale a context change no longer fetches
        - rollout strategies are evaluated as specs/rollout-strategies.yaml describes, checked against its golden
          fixture: stacked percentage strategies now work (a second percentage strategy was never matched), context
          values that are lists match if any value does, booleans and numbers in the context no longer raise, dates
          and date-times are compared in UTC, semantic versions compare their first three parts numerically, IPv4
          blocks and short/octal/hex forms are understood, and an invalid pattern, address or version never matches
          (rather than raising). An absent DATE or DATETIME attribute is today / now. Numbers in strings are parsed
          strictly, not with JavaScript's prefix rules. node-semver is no longer a dependency
        - context attributes are always stored as a list of values of any type: `attribute_values()` (and the
          well-known setters) take one value or a list, tuple or set, and None removes the attribute. Values are kept as
          given and converted to the type each strategy attribute needs when it is evaluated (enums by their value)
        - streaming treats a 200 response that isn't text/event-stream as a failed connection, any `edge.stale` value
          as stale, resets the reconnect delay on any FeatureHub event, tells the repository of a lost connection
          (bye), never waits less than 100ms, and the backoff multiplier is configurable with
          FEATUREHUB_STREAMING_BACKOFF_MULTIPLIER
* 1.1.0 - update dependencies
* 1.0.0 - added in support for server based poll interval changes, stale environments, consistent logging name (now "featurehub_sdk"), updated example to match. Production grade SDK.
* 0.0.2 - initial release
