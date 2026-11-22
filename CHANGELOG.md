# Changelog

* 2.0.0
    - contains breaking changes: see "Upgrading from 1.x to 2.0" in README.md for the steps to check before upgrading
    - requires Python 3.11 or later (tested on 3.11 - 3.15)
    - build moved from setup.py to pyproject.toml and uv
    - fixes for SSE for last-event-id and making streaming more resilient: it reconnects with an increasing delay
      instead of stopping when the server is unavailable, and a bad event or failing listener no longer drops the stream
    - added new environment variables for retry delays: FEATUREHUB_SSE_INITIAL_RETRY_DELAY and
      FEATUREHUB_SSE_MAX_RETRY_DELAY
    - made polling more resilient to failures, particularly on 1st one: errors are logged and polling continues
    - polling now uses a single worker thread so only one request is ever in flight; poll() and context_change()
      wait for it without blocking the event loop. poll_with_interval() and poll_again() have been removed
    - polling or streaming stopped by a rejected API key or a stale environment is no longer restarted by poll(),
      update_interval() or close()
    - nothing is applied to the repository from a request or stream that was in flight when close() was called
    - polling requests time out after 12 seconds, configurable with the FEATUREHUB_POLLING_REQ_TIMEOUT environment variable
    - update_interval() takes effect immediately on a running poller, and starts polling if the interval was 0
    - the streaming client can be polled again after close(), and releases its connection when a stream ends
    - streaming reconnects after a connect timeout (12s) or a stream with no data for 6 minutes, configurable with
      FEATUREHUB_SSE_CONNECT_TIMEOUT and FEATUREHUB_SSE_READ_TIMEOUT (a warning is logged if it is 5 minutes or less,
      as FeatureHub may hold a quiet connection open that long)
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
        - environment variables use the names the protocol specification gives every server-side SDK
          (providers.environment_variables): FEATUREHUB_EDGE_URL, FEATUREHUB_CLIENT_API_KEY and
          FEATUREHUB_SERVER_API_KEY are used when `FeatureHubConfig` is not given the URL or keys,
          FEATUREHUB_CONNECT_TYPE (active, passive or streaming) and FEATUREHUB_CONNECT_INTERVAL choose how features are
          fetched, the request timeout is FEATUREHUB_POLLING_REQ_TIMEOUT and the streaming settings are FEATUREHUB_SSE_*.
          Intervals, delays and timeouts are a single number and a unit (30s, 500ms, 1.5m, 1h), or 0; compound values
          such as 1m30s are not accepted
        - the 1.x FEATUREHUB_POLL_INTERVAL (seconds, no unit) is still read by use_polling_edge_service(), with a
          deprecation warning, but only when neither FEATUREHUB_CONNECT_TYPE nor FEATUREHUB_CONNECT_INTERVAL is set
        - passive polling: FEATUREHUB_CONNECT_TYPE=passive, or use_polling_edge_service(interval, passive=True), fetches
          only when features are read and are older than the interval
        - the default edge service is chosen from the environment: FEATUREHUB_CONNECT_TYPE=active or passive polls at
          FEATUREHUB_CONNECT_INTERVAL (which must be set), streaming streams, FEATUREHUB_CONNECT_INTERVAL alone polls,
          and with neither a client evaluated key streams (unless the code chooses the edge service itself)
        - polling has no default interval: use_polling_edge_service() without one takes FEATUREHUB_CONNECT_INTERVAL,
          and raises a `ValueError` if it is not set (it was 30 seconds)
        - server evaluated keys have no default: polling must be chosen with use_polling_edge_service() or the
          environment, and `StreamingEdgeClient` rejects them (the context isn't sent over streaming, so FeatureHub
          would evaluate them without it)
        - every request to FeatureHub sends sdk_version=2 (the protocol generation), with the query parameters in a
          fixed order (apiKey, contextSha, sdk_version) so a CDN sees equal requests as equal; streaming now sends
          contextSha too. An edge URL with a query string keeps it
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
          (rather than raising). An absent DATE or DATETIME attribute is today / now. Numbers are strict (rollout-strategies.yaml
          strict_number): a string must be exactly a decimal number, never JavaScript's prefix rules. node-semver is no longer a dependency
        - context attributes are always stored as a list of values of any type: `attribute_values()` (and the
          well-known setters) take one value or a list, tuple or set, and None removes the attribute. Values are kept as
          given and converted to the type each strategy attribute needs when it is evaluated (enums by their value)
        - streaming treats a 200 response that isn't text/event-stream as a failed connection, any `edge.stale` value
          as stale, resets the reconnect delay on any FeatureHub event (bye included, so quiet connections that
          FeatureHub ends with a bye never back off), tells the repository of a lost connection (bye), never waits less
          than 100ms, and the backoff multiplier is configurable with FEATUREHUB_SSE_BACKOFF_MULTIPLIER
        - a stream that ends less than 10 seconds after it opened is a failure, whatever it delivered, and keeps backing
          off (typically a cache in front of FeatureHub replaying a closed stream); after 3 in a row a warning is logged
* 1.1.0 - update dependencies
* 1.0.0 - added in support for server based poll interval changes, stale environments, consistent logging name (now "featurehub_sdk"), updated example to match. Production grade SDK.
* 0.0.2 - initial release
