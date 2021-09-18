#!/usr/bin/env python3
"""
Documentation

See also https://www.python-boilerplate.com/flask
"""
import os

from flask import Flask, jsonify
from flask_cors import CORS

from featurehub_sdk.featurehub_config import FeatureHubConfig


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
    edge_url = 'https://zjbisc.demo.featurehub.io/'
    client_eval_key = 'default/806d0fe8-2842-4d17-9e1f-1c33eedc5f31/wFk8qfmJEkLnkkJ8A8ZPTbgZPHPTJJ*heGuAGL6U8EKOUXbbRCL'

    config = FeatureHubConfig(edge_url, client_eval_key)
    config.init()
    fh = config.repository()
    features = fh.features
    print(features)



    @app.route("/")
    def hello_world():
        return "Hello World"

    @app.route("/foo/<someId>")
    def foo_url_arg(someId):
        return jsonify({"echo": someId})

    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app = create_app()
    app.run(host="0.0.0.0", port=port)
