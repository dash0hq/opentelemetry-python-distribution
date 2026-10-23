"""A Flask application with no OpenTelemetry dependency of its own.

The point of the end-to-end test is that this file never mentions
OpenTelemetry. Everything the exported telemetry contains arrives because the
injected tree was prepended to ``PYTHONPATH``, which is what the operator and
the OpenTelemetry injector do in production.

The module is named ``checkout.py`` on purpose: with no ``OTEL_SERVICE_NAME``
set, the distribution derives ``service.name`` from the basename of the
entrypoint script, so the test can assert on the value ``checkout``.
"""

from flask import Flask, jsonify

app: Flask = Flask(__name__)


@app.get("/")
def index() -> tuple[str, int]:
    return "ok", 200


@app.get("/order/<item>")
def order(item: str):
    return jsonify({"ordered": item})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
