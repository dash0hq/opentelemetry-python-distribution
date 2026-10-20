"""A Flask application with no OpenTelemetry dependency of its own.

The point of the end-to-end test is that this file never mentions
OpenTelemetry. Everything the exported telemetry contains arrives because the
injected tree was prepended to ``PYTHONPATH``, which is what the operator and
the OpenTelemetry injector do in production.

This copy is installed as the distribution ``checkout-service`` 2.4.0 and
started through its ``checkout`` console script, so the distribution reports
``service.name=checkout-service`` and ``service.version=2.4.0`` rather than the
entrypoint basename. The sibling at ``app/checkout.py`` is the same program run
as a plain script, which is what makes the two deployments comparable.
"""

from flask import Flask, jsonify

app: Flask = Flask(__name__)


@app.get("/")
def index() -> tuple[str, int]:
    return "ok", 200


@app.get("/order/<item>")
def order(item: str):
    return jsonify({"ordered": item})


def main() -> None:
    app.run(host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
