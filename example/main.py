#!/usr/bin/env python3
"""
Documentation

See also https://www.python-boilerplate.com/flask
"""
import os
import asyncio
from flask import Flask, jsonify, abort
from flask_cors import CORS

from featurehub_sdk.featurehub_config import FeatureHubConfig
import config as cnf
from featurehub_sdk.polling_edge_service import PollingEdgeService

app = None

def create_app(config=None):
    app = Flask(__name__)

    # See http://flask.pocoo.org/docs/latest/config/
    app.config.update(dict(DEBUG=True))
    app.config.update(config or {})

    # Setup cors headers to allow all domains
    # https://flask-cors.readthedocs.io/en/latest/
    CORS(app)

    # Definition of the routes. Put them into their own file. See also
    # Flask Blueprints: http://flask.pocoo.org/docs/latest/blueprints

    # Create FeatureHub configuration
    edge_url = cnf.edge_url
    client_eval_key = cnf.client_eval_key

    config = FeatureHubConfig(edge_url, [client_eval_key])
    # to use polling
    # config.use_polling_edge_service()
    # it takes a parameter uses the environment variable FEATUREHUB_POLL_INTERVAL if set

    asyncio.run(config.init())
    fh = config.repository()

    @app.route("/")
    def hello_world():
        if fh.feature('FEATURE_TITLE_TO_UPPERCASE').get_flag:
            return "HELLO WORLD"
        else:
            return "hello world"

    @app.route("/async-name/<name>")
    async def async_name_arg(name):
        ctx = await config.new_context().user_key(name).build()
        if ctx.feature('FEATURE_TITLE_TO_UPPERCASE').get_flag:
            return "HELLO WORLD"
        else:
            return "hello world"

    @app.route("/name/<name>")
    def name_arg(name):
        if config.new_context().user_key(name).build_sync().feature('FEATURE_TITLE_TO_UPPERCASE').get_flag:
            return "HELLO WORLD"
        else:
            return "hello world"


    @app.route("/foo/<someId>")
    def foo_url_arg(someId):
        return jsonify({"echo": someId})

    @app.route("/health/readiness")
    def check_fh_readiness():
        if fh.is_ready():
            return "FeatureHub server is ready"
        else:
            return abort(503, 'FeatureHub server is not ready')

    return app


if __name__ == "__main__":
    if app is None:
        port = int(os.environ.get("PORT", 8000))
        app = create_app()
        app.run(host="0.0.0.0", port=port, use_reloader=False)
