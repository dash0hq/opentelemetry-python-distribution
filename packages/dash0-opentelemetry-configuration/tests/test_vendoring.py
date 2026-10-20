"""Checks on the vendoring, not on the configuration semantics.

Upstream's suite covers what a configuration file means, and the fork's
``tests/test_generated_validator.py`` covers whether the generated validator
agrees with ``jsonschema``. Neither runs here. What is specific to this
repository is the packaging: that the shims resolve, that the dependency the
whole exercise exists to avoid is really absent, and that a configuration file
drives the distribution end to end.
"""

from importlib.metadata import requires
from pathlib import Path

import pytest
from opentelemetry import configuration as public
from opentelemetry._configuration import _generated_validator
from opentelemetry._configuration.file._loader import _validate_schema
from opentelemetry._logs import get_logger_provider
from opentelemetry.configuration import (
    ConfigurationError,
    configure_sdk,
    load_config_file,
)
from opentelemetry.metrics import get_meter_provider
from opentelemetry.propagate import get_global_textmap
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import get_tracer_provider

_VALID: str = """
file_format: "1.0-rc.1"
tracer_provider:
  processors:
    - simple:
        exporter:
          console: {}
"""

_EVERY_GLOBAL: str = """
file_format: "1.0-rc.1"
tracer_provider:
  processors:
    - simple:
        exporter:
          console: {}
meter_provider:
  readers:
    - periodic:
        exporter:
          console: {}
logger_provider:
  processors:
    - simple:
        exporter:
          console: {}
propagator:
  composite:
    - tracecontext: {}
    - baggage: {}
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


def test_the_public_path_resolves_to_the_private_tree() -> None:
    assert public.configure_sdk.__module__.startswith("opentelemetry._configuration")
    assert public.load_config_file.__module__.startswith("opentelemetry._configuration")


def test_the_package_does_not_depend_on_jsonschema() -> None:
    declared: list[str] = requires("dash0-opentelemetry-configuration") or []

    assert not [r for r in declared if r.lower().startswith("jsonschema")]


def test_the_validator_needs_no_third_party_import() -> None:
    source: str = Path(_generated_validator.__file__).read_text()
    imported: set[str] = {
        line.split()[1].split(".")[0]
        for line in source.splitlines()
        if line.startswith(("import ", "from "))
    }

    assert imported == {"decimal", "opentelemetry"}


def test_a_valid_file_loads(tmp_path: Path) -> None:
    config_file: Path = tmp_path / "otel-config.yaml"
    config_file.write_text(_VALID)

    assert load_config_file(str(config_file)) is not None


def test_a_file_naming_the_dash0_detectors_loads(tmp_path: Path) -> None:
    config_file: Path = tmp_path / "otel-config.yaml"
    config_file.write_text(_DASH0_DETECTORS)

    config = load_config_file(str(config_file))

    assert len(config.resource.detection_development.detectors) == 3


def test_configure_sdk_sets_every_global_against_the_pinned_sdk(
    tmp_path: Path,
) -> None:
    """Run the vendored code against the SDK this distribution actually pins.

    The vendored tree uses SDK internals that move between releases, and the
    fork's own suite runs against whatever SDK the fork pins. This is the only
    place the two meet, so it is the only check that the package works with the
    SDK that ships. Loading a file is not enough: the provider builders are
    where the internals are touched, and ``configure_sdk`` is what calls them.
    """
    config_file: Path = tmp_path / "otel-config.yaml"
    config_file.write_text(_EVERY_GLOBAL)

    configure_sdk(load_config_file(str(config_file)))

    assert isinstance(get_tracer_provider(), TracerProvider)
    assert isinstance(get_meter_provider(), MeterProvider)
    assert isinstance(get_logger_provider(), LoggerProvider)
    assert [type(p).__name__ for p in get_global_textmap()._propagators] == [
        "TraceContextTextMapPropagator",
        "W3CBaggagePropagator",
    ]


def test_an_invalid_document_is_rejected_with_the_property_named() -> None:
    with pytest.raises(ConfigurationError) as caught:
        _validate_schema({"tracer_provider": {"processors": []}})

    assert "must contain ['file_format'] properties" in str(caught.value)
