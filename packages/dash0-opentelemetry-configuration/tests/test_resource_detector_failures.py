"""A resource detector that fails must not cost the application its providers.

``configure_sdk`` builds the resource before it installs the tracer, meter and
logger providers and before it sets the propagator, so an exception raised out
of a detector used to leave the whole SDK unconfigured. The fork runs each
detector under a handler that logs and continues, and these tests pin that
behavior until upstream does the same.

Two of the tests go through a subprocess because ``configure_sdk`` installs
global providers that a process accepts only once, and the claim they make is
about what the global tracer provider is afterwards.
"""

from pathlib import Path
from socket import gethostname
from subprocess import run
from sys import executable
from unittest.mock import MagicMock

import pytest
from opentelemetry._configuration._resource import (
    _RESOURCE_DETECTOR_REGISTRY,
    create_resource,
)
from opentelemetry._configuration.models import (
    ExperimentalResourceDetection,
    ExperimentalResourceDetector,
)
from opentelemetry._configuration.models import Resource as ResourceConfig
from opentelemetry.sdk.resources import (
    CONTAINER_ID,
    HOST_NAME,
    TELEMETRY_SDK_LANGUAGE,
)

_CONFIG_FILE: str = """\
file_format: "1.0"
tracer_provider:
  processors:
    - simple:
        exporter:
          console: {}
resource:
  detection/development:
    detectors:
      - container: {}
"""

_MAKE_THE_DETECTOR_RAISE: str = """\
from unittest.mock import MagicMock, patch

detector = MagicMock()
detector.return_value.detect.side_effect = RuntimeError("no cgroup here")
entry_point = MagicMock()
entry_point.load.return_value = detector
patch(
    "opentelemetry._configuration._common.entry_points",
    return_value=[entry_point],
).start()
"""

_PROGRAM: str = """\
{preamble}
from opentelemetry.configuration import configure_sdk, load_config_file
from opentelemetry.trace import get_tracer_provider

configure_sdk(load_config_file({path!r}))
print(type(get_tracer_provider()).__name__)
"""


def _config_listing(**detectors: object) -> ResourceConfig:
    return ResourceConfig(
        detection_development=ExperimentalResourceDetection(
            detectors=[ExperimentalResourceDetector(**detectors)]
        )
    )


def _tracer_provider_after_configure_sdk(tmp_path: Path, preamble: str) -> str:
    config_file = tmp_path / "otel-config.yaml"
    config_file.write_text(_CONFIG_FILE, encoding="utf8")
    program = _PROGRAM.format(preamble=preamble, path=str(config_file))

    completed = run(
        [executable, "-c", program], capture_output=True, text=True, timeout=60
    )

    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip().splitlines()[-1]


def test_a_detector_that_is_not_installed_still_yields_a_resource(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``container`` names a schema field whose contrib package this distro omits."""
    with caplog.at_level("WARNING", logger="opentelemetry._configuration._resource"):
        resource = create_resource(_config_listing(container={}))

    assert resource.attributes[TELEMETRY_SDK_LANGUAGE] == "python"
    assert CONTAINER_ID not in resource.attributes
    assert [record.levelname for record in caplog.records] == ["WARNING"]
    assert caplog.records[0].exc_info is None
    message = caplog.records[0].getMessage()
    assert message.startswith("Skipping resource detector 'container' in ")
    assert "Make sure the package providing this plugin is installed." in message


def test_a_detector_that_raises_inside_detect_still_yields_a_resource(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``load_entry_point`` never sees a failure that happens after the class loads."""
    detector = MagicMock()
    detector.return_value.detect.side_effect = RuntimeError("no cgroup here")
    entry_point = MagicMock()
    entry_point.load.return_value = detector
    monkeypatch.setattr(
        "opentelemetry._configuration._common.entry_points",
        lambda *args, **kwargs: [entry_point],
    )

    with caplog.at_level("ERROR", logger="opentelemetry._configuration._resource"):
        resource = create_resource(_config_listing(container={}))

    assert resource.attributes[TELEMETRY_SDK_LANGUAGE] == "python"
    assert CONTAINER_ID not in resource.attributes
    assert [record.levelname for record in caplog.records] == ["ERROR"]
    assert caplog.records[0].exc_info is not None
    assert "'container'" in caplog.records[0].getMessage()


def test_a_detector_the_schema_does_not_declare_still_yields_a_resource(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A name outside the four schema fields arrives through ``additional_properties``."""
    with caplog.at_level("WARNING", logger="opentelemetry._configuration._resource"):
        resource = create_resource(_config_listing(**{"aws_ecs": {}}))

    assert resource.attributes[TELEMETRY_SDK_LANGUAGE] == "python"
    assert [record.levelname for record in caplog.records] == ["WARNING"]
    assert "'aws_ecs'" in caplog.records[0].getMessage()


def test_a_built_in_detector_that_raises_still_yields_a_resource(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``host``, ``process`` and ``service`` run from the registry, not an entry point."""
    monkeypatch.setitem(
        _RESOURCE_DETECTOR_REGISTRY,
        "process",
        MagicMock(side_effect=RuntimeError("no proc table here")),
    )

    with caplog.at_level("ERROR", logger="opentelemetry._configuration._resource"):
        resource = create_resource(_config_listing(process={}, host={}))

    assert resource.attributes[HOST_NAME] == gethostname()
    assert [record.levelname for record in caplog.records] == ["ERROR"]
    assert caplog.records[0].exc_info is not None
    assert "'process'" in caplog.records[0].getMessage()


def test_a_detector_that_is_not_installed_does_not_stop_later_detectors() -> None:
    """The handler wraps one detector, so a later one still contributes attributes."""
    resource = create_resource(_config_listing(container={}, host={}))

    assert CONTAINER_ID not in resource.attributes
    assert resource.attributes[HOST_NAME] == gethostname()


def test_a_detector_that_raises_inside_detect_does_not_stop_later_detectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The second failure route has to be contained per detector too."""
    detector = MagicMock()
    detector.return_value.detect.side_effect = RuntimeError("no cgroup here")
    entry_point = MagicMock()
    entry_point.load.return_value = detector
    monkeypatch.setattr(
        "opentelemetry._configuration._common.entry_points",
        lambda *args, **kwargs: [entry_point],
    )

    resource = create_resource(_config_listing(container={}, host={}))

    assert CONTAINER_ID not in resource.attributes
    assert resource.attributes[HOST_NAME] == gethostname()


def test_configure_sdk_still_installs_a_tracer_provider_when_a_detector_is_absent(
    tmp_path: Path,
) -> None:
    assert _tracer_provider_after_configure_sdk(tmp_path, "") == "TracerProvider"


def test_configure_sdk_still_installs_a_tracer_provider_when_a_detector_raises(
    tmp_path: Path,
) -> None:
    assert (
        _tracer_provider_after_configure_sdk(tmp_path, _MAKE_THE_DETECTOR_RAISE)
        == "TracerProvider"
    )
