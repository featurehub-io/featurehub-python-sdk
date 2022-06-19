#!/usr/bin/env python3
"""
Documentation

See also https://www.python-boilerplate.com/flask
"""
import os
import asyncio
from flask import Flask, jsonify, abort, request
from flask_cors import CORS

from featurehub_sdk.featurehub_config import FeatureHubConfig
import config as cnf
from featurehub_sdk.polling_edge_service import PollingEdgeService

app = None

users = dict()

class Todo:
    def __init__(self, todo_id, title, resolved):
        self.todo_id = todo_id
        self.title = title
        self.resolved = resolved

    def __str__(self):
        return f"{self.todo_id} {self.title} {self.resolved}"


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
    edge_url = "https://zjbisc.demo.featurehub.io" # cnf.edge_url
    client_eval_key = "default/9b71f803-da79-4c04-8081-e5c0176dda87/CtVlmUHirgPd9Qz92Y0IQauUMUv3Wb*4dacoo47oYp6hSFFjVkG" # cnf.client_eval_key

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

    # @app.route("/health/readiness")
    # def check_fh_readiness():
    #     if fh.is_ready():
    #         return "FeatureHub server is ready"
    #     else:
    #         return abort(503, 'FeatureHub server is not ready')

    # /todo/:user/:id/resolve
    @app.route("/todo/<user>/<id>/resolve", methods = ["PUT"])
    def resolve_to(user, id):
        print(user, id)
        return 'wat'

    # # /delete('/todo/:user/:id')
    # @app.route("/todo/<user>/<id>/resolve", methods = ["DELETE"])
    # def resolve_to(user, id):
    #     print(user, id)
    #     return 'wat'

    # delete('/todo/:user') do
    @app.route("/todo/<user>", methods = ["DELETE"])
    def delete_user(user):
        if user in users:
            users.pop(user)

        return "", 204

    # post('/todo/:user')
    @app.route("/todo/<user>", methods = ["POST"])
    def create_user_todo(user):
        data = request.json
        print(data)

        if data['title'] is None:
            return "", 400

        todos = user_todos(user)
        print(todos)
        todos.append(Todo(data["id"], data["title"], data["resolved"]))
        print(todos)

    # # get('/todo/:user')
    # @app.route("/todo/<user>/<id>/resolve", methods = ["GET"])
    # def resolve_to(user, id):
    #     print(user, id)
    #     return 'wat'

    # get( "/health/readiness")
    @app.route("/health/readiness", methods = ["GET"])
    def get_health_check():
        if config.repository().is_ready():
            return "OK"

        return "", 500

    def user_todos(user):
        todos = users.get(user, [])
        return todos

    def todo_list(user):
        ctx = config.

    return app


if __name__ == "__main__":
    if app is None:
        port = int(os.environ.get("PORT", 8000))
        app = create_app()
        app.run(host="0.0.0.0", port=port, use_reloader=False)
