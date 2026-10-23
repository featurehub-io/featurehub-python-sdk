# Changelog

* 1.2.0
    - requires Python 3.11 or later (tested on 3.11 - 3.15)
    - build moved from setup.py to pyproject.toml and uv
    - fixes for SSE for last-event-id and making streaming more resilient: it reconnects with an increasing delay
      instead of stopping when the server is unavailable, and a bad event or failing listener no longer drops the stream
    - added new environment variables for retry delays: FEATUREHUB_STREAMING_INITIAL_RETRY_DELAY and
      FEATUREHUB_STREAMING_MAX_RETRY_DELAY
    - made polling more resilient to failures, particularly on 1st one: errors are logged and polling continues
    - polling now uses a single worker thread so only one request is ever in flight; poll() and context_change()
      wait for it without blocking the event loop. poll_with_interval() and poll_again() have been removed
    - polling or streaming stopped by an invalid API key (404) or a stale environment is no longer restarted by poll(),
      update_interval() or close(). context_change() still fetches once for the new context (reporting failure for an
      invalid key), so the repository doesn't stay not ready
    - nothing is applied to the repository from a request or stream that was in flight when close() was called
    - polling requests time out after 12 seconds, configurable with the FEATUREHUB_POLLING_TIMEOUT environment variable
    - update_interval() takes effect immediately on a running poller, and starts polling if the interval was 0
    - the streaming client can be polled again after close(), and releases its connection when a stream ends
    - streaming reconnects after a connect timeout (12s) or a quiet stream (60s), configurable with
      FEATUREHUB_STREAMING_CONNECT_TIMEOUT and FEATUREHUB_STREAMING_READ_TIMEOUT
    - streaming notifies the repository of failure on an invalid API key (404), as polling does
    - updated dependencies based on trivy scan
* 1.1.0 - update dependencies
* 1.0.0 - added in support for server based poll interval changes, stale environments, consistent logging name (now "featurehub_sdk"), updated example to match. Production grade SDK.
* 0.0.2 - initial release
