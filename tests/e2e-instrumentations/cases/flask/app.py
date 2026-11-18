"""Exercise opentelemetry-instrumentation-flask and exit.

The request goes through Flask's test client rather than a socket. The
instrumentation wraps ``Flask.wsgi_app``, which the test client calls, so the
server span is produced by the same code path a real request takes, without a
port to bind or a thread to join.
"""

from flask import Flask, jsonify
from werkzeug.wrappers.response import Response

app: Flask = Flask(__name__)


@app.route("/items/<int:item_id>")
def read_item(item_id: int) -> Response:
    return jsonify({"id": item_id, "name": "widget"})


def main() -> None:
    with app.test_client() as client:
        response = client.get("/items/7")
        assert response.status_code == 200, response.status_code
        assert response.get_json() == {"id": 7, "name": "widget"}


main()
