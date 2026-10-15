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
    - polling stopped by an invalid API key (404) is no longer restarted by poll(), context_change() or update_interval()
    - updated dependencies based on trivy scan
* 1.1.0 - update dependencies
* 1.0.0 - added in support for server based poll interval changes, stale environments, consistent logging name (now "featurehub_sdk"), updated example to match. Production grade SDK.
* 0.0.2 - initial release
