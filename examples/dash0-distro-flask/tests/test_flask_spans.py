"""Verify that the Dash0 distribution auto-instruments the Flask app (no OTel
imports in app.py) and exports via the pure-Python pyproto exporter."""

import json
from os.path import dirname, join


def _load_spans(traces_jsonl):
    """Parse all spans from the OTLP JSONL file produced by the file exporter."""
    spans = []
    with open(traces_jsonl) as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            batch = json.loads(line)
            for resource_spans in batch.get("resourceSpans", []):
                for scope_spans in resource_spans.get("scopeSpans", []):
                    spans.extend(scope_spans.get("spans", []))
    return spans


def _resource_attributes(traces_jsonl):
    """Return a merged {key: value} of all resource attributes seen."""
    attributes = {}
    with open(traces_jsonl) as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            batch = json.loads(line)
            for resource_spans in batch.get("resourceSpans", []):
                for kv in resource_spans.get("resource", {}).get("attributes", []):
                    value = kv["value"]
                    attributes[kv["key"]] = (
                        value.get("stringValue")
                        or value.get("intValue")
                        or value.get("boolValue")
                        or value.get("doubleValue")
                    )
    return attributes


def _attr(span, key):
    for kv in span.get("attributes", []):
        if kv["key"] == key:
            value = kv["value"]
            return (
                value.get("stringValue")
                or value.get("intValue")
                or value.get("boolValue")
                or value.get("doubleValue")
            )
    return None


class TestFlaskSpans:
    def test_traces_file_exists(self, output_dir):
        path = join(output_dir, "traces.jsonl")
        assert open(path).read().strip(), (
            "traces.jsonl is empty — no spans were exported"
        )

    def test_flask_spans_present(self, output_dir):
        spans = _load_spans(join(output_dir, "traces.jsonl"))
        assert spans, "No spans found in traces.jsonl"
        names = {span["name"] for span in spans}
        assert any("GET" in name for name in names), (
            f"No GET spans found. Span names: {sorted(names)}\n"
            "FlaskInstrumentor was not activated — check that the Dash0 distro "
            "loaded and instrumented Flask."
        )

    def test_flask_span_has_http_route(self, output_dir):
        spans = _load_spans(join(output_dir, "traces.jsonl"))
        routes = [
            _attr(span, "http.route") or _attr(span, "url.path")
            for span in spans
            if "GET" in span.get("name", "")
        ]
        assert any(routes), (
            "Flask spans found but none carry http.route or url.path. "
            f"Span names: {[span['name'] for span in spans]}"
        )

    def test_items_route_traced(self, output_dir):
        spans = _load_spans(join(output_dir, "traces.jsonl"))
        item_spans = [
            span
            for span in spans
            if "items" in span.get("name", "").lower()
            or _attr(span, "http.route") in ("/items/<int:item_id>", "/items/<item_id>")
        ]
        assert item_spans, (
            "No span for the /items/<item_id> route found. "
            f"All span names: {[span['name'] for span in spans]}"
        )

    def test_excluded_url_not_traced(self, output_dir):
        """OTEL_PYTHON_FLASK_EXCLUDED_URLS=items/42 (set in docker-compose.yml)
        is honored by the auto-instrumentation the distro activates, so the
        /items/42 request must produce no span even though the app serves it."""
        spans = _load_spans(join(output_dir, "traces.jsonl"))
        excluded = [
            span
            for span in spans
            if (_attr(span, "url.path") or _attr(span, "http.target")) == "/items/42"
        ]
        assert not excluded, (
            "A span for /items/42 was exported, but "
            "OTEL_PYTHON_FLASK_EXCLUDED_URLS: 'items/42' should have suppressed "
            "it. Span targets: "
            f"{[_attr(s, 'url.path') or _attr(s, 'http.target') for s in spans]}"
        )

    def test_dash0_distro_configured_the_sdk(self, output_dir):
        """The Dash0 distribution injects telemetry.distro.name=dash0-python
        into the resource; its presence proves the distro (not a bare SDK) set
        things up."""
        attributes = _resource_attributes(join(output_dir, "traces.jsonl"))
        assert attributes.get("telemetry.distro.name") == "dash0-python", (
            "telemetry.distro.name=dash0-python not found in resource "
            f"attributes: {attributes}"
        )
        assert attributes.get("service.name") == "dash0-distro-flask-demo", (
            f"unexpected service.name in resource attributes: {attributes}"
        )

    def test_no_otel_import_in_app(self):
        """Sanity-check: app.py must not import OpenTelemetry directly."""
        app_path = join(dirname(dirname(__file__)), "app.py")
        imports = [
            line
            for line in open(app_path).read().splitlines()
            if line.strip().startswith(("import opentelemetry", "from opentelemetry"))
        ]
        assert not imports, (
            "app.py imports OpenTelemetry directly — the whole point of this "
            f"demo is that the app is unmodified. Offending lines: {imports}"
        )
