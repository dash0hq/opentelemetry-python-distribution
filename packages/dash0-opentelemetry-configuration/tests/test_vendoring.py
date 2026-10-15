"""Checks on what the Dash0 build changes relative to upstream.

Upstream's own suite covers the configuration semantics. These cover the
vendoring itself: that the public import path resolves to the private tree,
that the generated validator still rejects what ``jsonschema`` rejected, and
that no compiled dependency re-enters the import closure.
"""

from importlib.metadata import requires
from pathlib import Path
from typing import Any

import pytest
from opentelemetry import configuration as public
from opentelemetry._configuration.file._loader import _validate_schema
from opentelemetry.configuration import ConfigurationError, load_config_file

_GOOD: str = """
file_format: "1.0-rc.1"
tracer_provider:
  processors:
    - simple:
        exporter:
          console: {}
"""

_DASH0_DETECTORS: str = """
file_format: "1.0-rc.1"
resource:
  detection/development:
    detectors:
      - dash0_distribution:
      - dash0_kubernetes:
      - dash0_service_name:
tracer_provider:
  processors:
    - simple:
        exporter:
          console: {}
"""

_REJECTED: list[tuple[str, dict[str, Any]]] = [
    ("unknown key", {"file_format": "1.0-rc.1", "resource": {"detectors": []}}),
    (
        "missing required field",
        {"file_format": "1.0-rc.1", "tracer_provider": {"limits": {}}},
    ),
    (
        "value below minimum",
        {
            "file_format": "1.0-rc.1",
            "tracer_provider": {
                "processors": [{"simple": {"exporter": {"console": {}}}}],
                "limits": {"attribute_count_limit": -5},
            },
        },
    ),
    (
        "sampling ratio out of range",
        {
            "file_format": "1.0-rc.1",
            "tracer_provider": {
                "processors": [{"simple": {"exporter": {"console": {}}}}],
                "sampler": {"trace_id_ratio_based": {"ratio": 50}},
            },
        },
    ),
    (
        "empty processor list",
        {"file_format": "1.0-rc.1", "tracer_provider": {"processors": []}},
    ),
    (
        "two exporters in one block",
        {
            "file_format": "1.0-rc.1",
            "tracer_provider": {
                "processors": [
                    {"simple": {"exporter": {"console": {}, "otlp_http": {}}}}
                ]
            },
        },
    ),
]


def test_the_public_path_resolves_to_the_private_tree() -> None:
    assert public.configure_sdk.__module__.startswith("opentelemetry._configuration")
    assert public.load_config_file.__module__.startswith("opentelemetry._configuration")


def test_the_package_does_not_depend_on_jsonschema() -> None:
    declared: list[str] = requires("dash0-opentelemetry-configuration") or []

    assert not [r for r in declared if r.lower().startswith("jsonschema")]


def test_the_validator_needs_no_third_party_import() -> None:
    from opentelemetry._configuration import _generated_validator

    source: str = Path(_generated_validator.__file__).read_text()
    imported: set[str] = {
        line.split()[1].split(".")[0]
        for line in source.splitlines()
        if line.startswith(("import ", "from "))
    }

    assert imported == {"decimal", "opentelemetry"}


@pytest.mark.parametrize("label,document", _REJECTED, ids=[c[0] for c in _REJECTED])
def test_invalid_documents_are_rejected(label: str, document: dict[str, Any]) -> None:
    with pytest.raises(ConfigurationError):
        _validate_schema(document)


def test_a_missing_required_property_is_named_in_the_message() -> None:
    with pytest.raises(ConfigurationError) as caught:
        _validate_schema({"tracer_provider": {"processors": []}})

    assert "must contain ['file_format'] properties" in str(caught.value)


def test_a_valid_document_is_accepted(tmp_path: Path) -> None:
    config_file: Path = tmp_path / "otel-config.yaml"
    config_file.write_text(_GOOD)

    assert load_config_file(str(config_file)) is not None


def test_a_configuration_naming_the_dash0_detectors_loads(tmp_path: Path) -> None:
    config_file: Path = tmp_path / "otel-config.yaml"
    config_file.write_text(_DASH0_DETECTORS)

    config = load_config_file(str(config_file))

    assert len(config.resource.detection_development.detectors) == 3
