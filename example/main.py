#!/usr/bin/env python3
"""
Documentation

See also https://www.python-boilerplate.com/flask
"""
import os
import asyncio
import logging.config
from typing import List

from flask import Flask, jsonify, abort, request, Response
from flask_cors import CORS

from featurehub_sdk.client_context import ClientContext
from featurehub_sdk.version import sdk_version
from featurehub_sdk.featurehub_config import FeatureHubConfig

app = None

users = dict()
config: FeatureHubConfig = None

class Todo:
    def __init__(self, todo_id, title, resolved):
        self.todo_id = todo_id
        self.title = title
        self.resolved = resolved

    def __str__(self):
        return f"{self.todo_id} {self.title} {self.resolved}"

    def to_dict(self):
        return {'id': self.todo_id,
                'title': self.title,
                'resolved': self.resolved}

def create_app(config=None):
    logging.config.fileConfig('logging.conf')

    app = Flask(__name__)

    # See http://flask.pocoo.org/docs/latest/config/
    app.config.update(dict(DEBUG=True))
    app.config.update(config or {})

    # Setup cors headers to allow all domains
    # https://flask-cors.readthedocs.io/en/latest/
    CORS(app)

    print(f"Using featurehub version {sdk_version}")
    # Create FeatureHub configuration
    edge_url = os.environ.get("FEATUREHUB_EDGE_URL", "http://localhost:8085") # cnf.edge_url
    client_eval_key = os.environ.get("FEATUREHUB_CLIENT_API_KEY", "default/845717ab-357e-4ce6-953c-2cb139974f2d/Zmv6OWy9K76IqnfeglTwSJoHbAAqhf*rjXljuNvAtoPVM4tpPIn")  # cnf.client_eval_key

    fh_config = FeatureHubConfig(edge_url, [client_eval_key])
    # to use polling
    fh_config.use_polling_edge_service()
    # it takes a parameter uses the environment variable FEATUREHUB_POLL_INTERVAL if set

    print("starting featurehub")
    asyncio.run(fh_config.init())

    # Definition of the routes. Put them into their own file. See also
    # Flask Blueprints: http://flask.pocoo.org/docs/latest/blueprints

    @app.route("/async-name/<name>")
    async def async_name_arg(name):
        ctx = await fh_config.new_context().user_key(name).build()
        if ctx.feature('FEATURE_TITLE_TO_UPPERCASE').get_flag:
            return "HELLO WORLD"
        else:
            return "hello world"

    @app.route("/name/<name>")
    def name_arg(name):
        if fh_config.new_context().user_key(name).build_sync().feature('FEATURE_TITLE_TO_UPPERCASE').get_flag:
            return "HELLO WORLD"
        else:
            return "hello world"


    @app.route("/foo/<someId>")
    def foo_url_arg(someId):
        return jsonify({"echo": someId})

    # /todo/:user/:id/resolve
    @app.route("/todo/<user>/<id>/resolve", methods = ["PUT"])
    def resolve_to(user, id):
        for todo in user_todos(user):
            if todo.todo_id == id:
                todo.resolved = True
                return todo_list(user), 200

        return "", 404

    # delete: /todo/:user/:id
    @app.route("/todo/<user>/<id>", methods = ["DELETE"])
    def delete_todo(user, id):
        todos = user_todos(user)
        for todo in todos:
            if todo.todo_id == id:
                todos.remove(todo)
                return todo_list(user), 200

        return "", 404

    # # /delete('/todo/:user/:id')
    # @app.route("/todo/<user>/<id>/resolve", methods = ["DELETE"])
    # def resolve_to(user, id):
    #     print(user, id)
    #     return 'wat'

    # delete('/todo/:user') do
    @app.route("/todo/<user>", methods = ["DELETE"])
    def delete_user(user):
        if user in users:
            del users[user]

        return "", 204

        # return "", 404

    # post('/todo/:user')
    @app.route("/todo/<user>", methods = ["POST"])
    def create_user_todo(user):
        data = request.json
        print(data)

        if data['title'] is None:
            return "", 400

        todos = user_todos(user)
        print(todos)
        todos.append(Todo(data["id"], data["title"], data.get("resolved") or False ))
        print(todos)

        return todo_list(user), 201

    @app.route("/health/readiness", methods = ["GET"])
    def get_health_check():
        if fh_config.repository().is_ready():
            return "OK"

        return "", 500

    def user_todos(user) -> List[Todo]:
        return users.setdefault(user, [])

    def process_title(ctx: ClientContext, title: str) -> str:
        new_title = title

        if ctx.is_set("FEATURE_STRING") and title == "buy":
            new_title = f"{title} {ctx.get_string('FEATURE_STRING')}"

        if ctx.is_set("FEATURE_NUMBER") and title == 'pay':
            new_title = f"{title} {ctx.get_number('FEATURE_NUMBER')}"

        if ctx.is_set('FEATURE_JSON') and title == 'find':
            new_title = f"{title} {ctx.get_json('FEATURE_JSON')['foo']}"

        if ctx.is_enabled('FEATURE_TITLE_TO_UPPERCASE'):
            new_title = new_title.upper()

        return new_title

    def todo_list(user: str) -> Response:
        ctx = fh_config.new_context().user_key(user).build_sync()
        todos = user_todos(user)
        new_todos = []

        for todo in todos:
            new_todos.append(Todo(todo.todo_id, process_title(ctx, todo.title), todo.resolved).to_dict())

        return jsonify(new_todos)

    @app.route("/todo/<user>", methods = ["GET"])
    def get_list(user):
        return todo_list(user), 200

    return app

if __name__ == "__main__":
    if app is None:
        port = int(os.environ.get("PORT", 8099))
        app = create_app()
        app.run(host="0.0.0.0", port=port, use_reloader=False)
