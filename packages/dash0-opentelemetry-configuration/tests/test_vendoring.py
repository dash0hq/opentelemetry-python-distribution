"""Checks on the vendoring, not on the configuration semantics.

Upstream's suite covers what a configuration file means, and the fork's
``tests/test_generated_validator.py`` covers whether the generated validator
agrees with ``jsonschema``. Neither runs here. What is specific to this
repository is the packaging: that the shims resolve, that the dependency the
whole exercise exists to avoid is really absent, and that a configuration file
drives the distribution end to end.

The tests named for an unset or empty variable, for a bare propagator entry and
for a bare detector entry are the exception. They pin behaviour that a
re-vendor can reverse without a word, since the only check on the vendored
tree compares it with the fork rather than with what the previous release did.
"""

from importlib.metadata import requires
from pathlib import Path

import pytest
from opentelemetry import configuration as public
from opentelemetry._configuration import _generated_validator
from opentelemetry._configuration._propagator import create_propagator
from opentelemetry._configuration._resource import create_resource
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
  tracer_configurator/development:
    default_config:
      enabled: true
    tracers:
      - name: a.scope.this.test.never.creates.*
        config:
          enabled: false
meter_provider:
  readers:
    - periodic:
        exporter:
          console: {}
        cardinality_limits:
          default: 100
  views:
    - selector:
        instrument_name: an.instrument.this.test.never.creates
      stream:
        aggregation_cardinality_limit: 100
  meter_configurator/development:
    default_config:
      enabled: true
    meters:
      - name: a.scope.this.test.never.creates.*
        config:
          enabled: false
logger_provider:
  processors:
    - simple:
        exporter:
          console: {}
  logger_configurator/development:
    default_config:
      enabled: true
    loggers:
      - name: a.scope.this.test.never.creates.*
        config:
          enabled: false
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

_UNSET_VARIABLE: str = """
file_format: "1.0-rc.1"
tracer_provider:
  processors:
    - simple:
        exporter:
          otlp_http:
            endpoint: ${DASH0_TEST_ENDPOINT_THAT_IS_NEVER_SET}
"""

_SUBSTITUTED_ATTRIBUTES: str = """
file_format: "1.0-rc.1"
resource:
  attributes:
    - name: bare
      value: ${DASH0_TEST_SUBSTITUTION}
    - name: with_default
      value: ${DASH0_TEST_SUBSTITUTION:-fallback}
"""

_BARE_PROPAGATORS: str = """
file_format: "1.0-rc.1"
propagator:
  composite:
    - tracecontext:
    - baggage:
"""

_BARE_DETECTORS: str = """
file_format: "1.0-rc.1"
resource:
  detection/development:
    detectors:
      - host:
      - process:
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


def test_an_unset_variable_with_no_default_leaves_the_setting_null(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reference the environment does not answer no longer fails the load.

    It substitutes an empty value, which the parser reads as null, so the
    setting falls back instead of standing the distribution down.
    """
    monkeypatch.delenv("DASH0_TEST_ENDPOINT_THAT_IS_NEVER_SET", raising=False)
    config_file: Path = tmp_path / "otel-config.yaml"
    config_file.write_text(_UNSET_VARIABLE)

    config = load_config_file(str(config_file))

    exporter = config.tracer_provider.processors[0].simple.exporter
    assert exporter.otlp_http.endpoint is None


def _substituted_attributes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str | None
) -> dict[str, object]:
    if value is None:
        monkeypatch.delenv("DASH0_TEST_SUBSTITUTION", raising=False)
    else:
        monkeypatch.setenv("DASH0_TEST_SUBSTITUTION", value)
    config_file: Path = tmp_path / "otel-config.yaml"
    config_file.write_text(_SUBSTITUTED_ATTRIBUTES)

    config = load_config_file(str(config_file))

    return {attribute.name: attribute.value for attribute in config.resource.attributes}


def test_an_empty_variable_with_a_default_substitutes_the_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A variable present with an empty value reaches its fallback.

    The specification substitutes the default when the variable is null, empty
    or undefined, so a Kubernetes manifest written with ``value: ""`` keeps the
    fallback the configuration file declares.
    """
    attributes = _substituted_attributes(tmp_path, monkeypatch, "")

    assert attributes["with_default"] == "fallback"


def test_an_empty_variable_without_a_default_leaves_the_setting_null(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With nothing to fall back to, an empty variable still reads as null."""
    attributes = _substituted_attributes(tmp_path, monkeypatch, "")

    assert attributes["bare"] is None


def test_an_unset_variable_with_a_default_substitutes_the_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attributes = _substituted_attributes(tmp_path, monkeypatch, None)

    assert attributes["with_default"] == "fallback"


def test_a_variable_holding_a_value_is_substituted_without_a_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attributes = _substituted_attributes(tmp_path, monkeypatch, "checkout")

    assert attributes["bare"] == "checkout"


def test_a_variable_holding_a_value_wins_over_its_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attributes = _substituted_attributes(tmp_path, monkeypatch, "checkout")

    assert attributes["with_default"] == "checkout"


def test_a_propagator_written_with_an_empty_value_is_installed(
    tmp_path: Path,
) -> None:
    """``- tracecontext:`` selects the propagator rather than being skipped.

    A key present with an empty value means an empty object, so a composite
    list written without ``{}`` propagates context instead of leaving the
    process with the noop propagator.
    """
    config_file: Path = tmp_path / "otel-config.yaml"
    config_file.write_text(_BARE_PROPAGATORS)

    propagator = create_propagator(load_config_file(str(config_file)).propagator)

    assert sorted(propagator.fields) == ["baggage", "traceparent", "tracestate"]


def test_a_detector_written_with_an_empty_value_runs(tmp_path: Path) -> None:
    """``- host:`` selects the detector rather than being skipped.

    The same empty-value rule as the bare propagator entry, on the path that
    widens the resource carried by every span, metric and log record.
    """
    config_file: Path = tmp_path / "otel-config.yaml"
    config_file.write_text(_BARE_DETECTORS)

    resource = create_resource(load_config_file(str(config_file)).resource)

    assert "host.arch" in resource.attributes
    assert "process.pid" in resource.attributes


def test_an_invalid_document_is_rejected_with_the_property_named() -> None:
    with pytest.raises(ConfigurationError) as caught:
        _validate_schema({"tracer_provider": {"processors": []}})

    assert "must contain ['file_format'] properties" in str(caught.value)
