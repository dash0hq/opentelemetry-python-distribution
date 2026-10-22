"""Resource detection for the Dash0 distribution.

Ports the two custom detectors the Node.js distribution ships (a Kubernetes pod
UID detector and a service-name fallback) plus the ``telemetry.distro.*``
attributes, and injects them into the standard OpenTelemetry environment
variables *before* the SDK builds its Resource.

Injecting via ``OTEL_RESOURCE_ATTRIBUTES``/``OTEL_SERVICE_NAME`` (rather than
registering SDK resource detectors) keeps this working across OTel SDK versions:
the distro's ``_configure`` runs before the configurator, and the SDK's own
``Resource.create`` reads these variables.

Declarative configuration (``OTEL_CONFIG_FILE``) deliberately ignores those
environment variables, so the same attributes are also exposed as standard SDK
resource detectors, registered under the ``opentelemetry_resource_detector``
entry-point group (see ``pyproject.toml``):
:class:`Dash0DistributionResourceDetector`,
:class:`Dash0KubernetesResourceDetector` and
:class:`Dash0ServiceNameResourceDetector`.
"""

import re
import sys
from importlib.metadata import distributions, packages_distributions
from os import environ, path
from pathlib import Path

from opentelemetry.sdk.resources import (
    Resource,
    ResourceDetector,
    ServiceInstanceIdResourceDetector,
)

from ._environment_variables import (
    DASH0_AUTOMATIC_SERVICE_NAME,
    OTEL_RESOURCE_ATTRIBUTES,
    OTEL_SERVICE_NAME,
)
from .settings import is_false
from .version import __version__

_SERVICE_NAME = "service.name"
_SERVICE_VERSION = "service.version"
_K8S_POD_UID = "k8s.pod.uid"
_DISTRO_NAME = "telemetry.distro.name"
_DISTRO_VERSION = "telemetry.distro.version"

_RUNNER_PROGRAMS = frozenset(
    {
        "celery",
        "daphne",
        "django-admin",
        "dramatiq",
        "flask",
        "granian",
        "gunicorn",
        "honcho",
        "huey_consumer",
        "hypercorn",
        "manage",
        "nox",
        "pdm",
        "pipenv",
        "pipx",
        "poetry",
        "pytest",
        "python",
        "python3",
        "rq",
        "rqworker",
        "supervisord",
        "tox",
        "uv",
        "uvicorn",
        "uvx",
        "waitress-serve",
    }
)

_ETC_HOSTS = "/etc/hosts"
_K8S_HOSTS_MARKER = "# Kubernetes-managed hosts file"
_CGROUP_V1_MOUNTINFO = "/proc/self/mountinfo"
_CGROUP_V2_CGROUP = "/proc/self/cgroup"
_POD_MOUNT_MARKER = "/pods/"
_POD_UID_LEN = 36
_CONTAINER_ID_LEN = 64
_POD_LABEL = "pod"
# matches cgroup v2 slices like kubepods-pode462ffed_94ce_4806_a52e_d2726f448f15.slice
_POD_UID_IN_CGROUP = re.compile(
    r"^[a-z_-]*pod(?P<uid>[0-9a-f]{8}[-_][0-9a-f]{4}[-_][0-9a-f]{4}"
    r"[-_][0-9a-f]{4}[-_][0-9a-f]{12})\.slice$"
)


def distribution_resource_attributes(version):
    attributes = {_DISTRO_NAME: "dash0-python"}
    if version:
        attributes[_DISTRO_VERSION] = version
    return attributes


def _read_candidate_lines(filename, minimum_length):
    try:
        with open(filename, encoding="utf8") as file:
            content = file.read()
    except OSError:
        return []
    return [
        line.strip()
        for line in content.splitlines()
        if len(line.strip()) > minimum_length
    ]


def running_in_kubernetes():
    try:
        with open(_ETC_HOSTS, encoding="utf8") as file:
            first_line = file.readline()
    except OSError:
        return False
    return first_line.startswith(_K8S_HOSTS_MARKER)


def pod_uid_from_cgroup_v1():
    for line in _read_candidate_lines(_CGROUP_V1_MOUNTINFO, _POD_UID_LEN):
        marker_index = line.find(_POD_MOUNT_MARKER)
        if marker_index > 0:
            after_marker = line[marker_index + len(_POD_MOUNT_MARKER) :]
            if len(after_marker) >= _POD_UID_LEN:
                return after_marker[:_POD_UID_LEN]
    return None


def pod_uid_from_cgroup_v2():
    for line in _read_candidate_lines(_CGROUP_V2_CGROUP, _CONTAINER_ID_LEN):
        segments = line.split("/")
        if len(segments) <= 2:
            continue
        penultimate = segments[-2]
        expected_length = _POD_UID_LEN + len(_POD_LABEL)
        if penultimate.startswith(_POD_LABEL) and len(penultimate) == expected_length:
            return penultimate[len(_POD_LABEL) :]
        match = _POD_UID_IN_CGROUP.match(penultimate)
        if match:
            return match.group("uid").replace("_", "-")
    return None


def detect_kubernetes_pod_uid():
    if not running_in_kubernetes():
        return None
    return pod_uid_from_cgroup_v1() or pod_uid_from_cgroup_v2()


def _service_name_already_configured():
    if environ.get(OTEL_SERVICE_NAME, "").strip():
        return True
    for pair in environ.get(OTEL_RESOURCE_ATTRIBUTES, "").split(","):
        key, _, value = pair.partition("=")
        if key.strip() == _SERVICE_NAME and value.strip().strip('"'):
            return True
    return False


def module_run_with_dash_m():
    """The module name of a ``python -m module`` command line, if this is one.

    Detection runs from ``sitecustomize`` at interpreter startup, before
    ``runpy`` has built the real ``__main__`` or rewritten ``sys.argv``. At that
    moment ``__main__.__package__`` is ``None`` and ``sys.argv`` is
    ``["-m", *program_arguments]``, so the module name survives only in
    ``sys.orig_argv``.

    CPython replaces the ``-m module`` pair with the single token ``-m`` and
    keeps every program argument after it, so the module name sits
    ``len(sys.orig_argv) - len(sys.argv)`` places into the original command
    line. That offset holds for every spelling, including ``python -um module``
    and ``python -W ignore -m module``, which is why the interpreter flags are
    never parsed.

    Returns ``None`` when the process was not started with ``-m``.
    """
    if not sys.argv or sys.argv[0] != "-m":
        return None
    orig_argv = getattr(sys, "orig_argv", [])
    index = len(orig_argv) - len(sys.argv)
    if not 0 < index < len(orig_argv):
        return None
    module = orig_argv[index]
    if not module or module.startswith("-"):
        return None
    return module


def detect_fallback_service_name():
    """Best-effort service name from the running program.

    The last resort in :func:`detect_service_metadata`, used when the process
    cannot be traced back to an installed distribution or a ``pyproject.toml``.

    Returns ``None`` for a generic runner such as ``gunicorn``, whose name
    identifies the launcher rather than the service it launched, and for an
    argument that is an interpreter flag rather than a program. Letting the SDK
    report ``unknown_service`` beats reporting a name that names no service.
    """
    module = module_run_with_dash_m()
    if module:
        return module.partition(".")[0] or None

    argv0 = sys.argv[0] if sys.argv else ""
    if not argv0:
        return None
    name = path.basename(argv0)
    if name.endswith(".py"):
        name = name[: -len(".py")]
    if not name or name.startswith("-") or name in _RUNNER_PROGRAMS:
        return None
    return name


def distribution_of_running_program():
    """The installed distribution this process was started from, if any.

    Two signals, which the command line makes mutually exclusive. A console
    script leaves its own name in ``sys.argv[0]``, and the distribution that
    declared that script owns the process. Otherwise ``python -m package``
    names the package, which ``packages_distributions`` maps back to the
    distribution that installed it.

    A console script that is a generic runner, such as ``gunicorn``, claims
    nothing: it declares no identity beyond its own, and reporting its version
    as the service version would describe the launcher rather than the service.

    Returns ``None`` for a process started as a plain script, which no
    installed distribution claims.
    """
    module = module_run_with_dash_m()
    if module is None:
        script = path.basename(sys.argv[0] if sys.argv else "")
        if script and not script.endswith(".py") and script not in _RUNNER_PROGRAMS:
            for distribution in distributions():
                for entry_point in distribution.entry_points:
                    if (
                        entry_point.group == "console_scripts"
                        and entry_point.name == script
                    ):
                        return distribution
        return None

    package = module.partition(".")[0]
    if not package:
        return None
    for name in packages_distributions().get(package, []):
        for distribution in distributions():
            if _normalized(distribution.metadata["Name"]) == _normalized(name):
                return distribution
    return None


def _normalized(name):
    return re.sub(r"[-_.]+", "-", name or "").lower()


def service_metadata_from_pyproject():
    """``[project]`` name and version from the nearest ``pyproject.toml``.

    Walks up from the directory holding the entrypoint script, not from the
    working directory, because ``python path/to/app.py`` is run from anywhere.
    The walk stops at a ``.git`` directory or at the filesystem root, so a
    monorepo yields the ``pyproject.toml`` that owns the entrypoint rather than
    the one at the top of the checkout.

    Returns ``(None, None)`` on any Python without ``tomllib``, which is every
    version before 3.11, rather than taking a dependency on ``tomli``.
    """
    try:
        from tomllib import loads as toml_loads
    except ImportError:
        return None, None

    argv0 = sys.argv[0] if sys.argv else ""
    if not argv0:
        return None, None
    try:
        directory = Path(argv0).resolve().parent
    except OSError:
        return None, None

    for candidate in [directory, *directory.parents]:
        manifest = candidate / "pyproject.toml"
        if manifest.is_file():
            try:
                project = toml_loads(manifest.read_text(encoding="utf8")).get(
                    "project", {}
                )
            except (OSError, ValueError):
                return None, None
            name = project.get("name")
            version = project.get("version")
            return (name or None), (version or None)
        if (candidate / ".git").exists():
            return None, None
    return None, None


def detect_service_metadata():
    """Best-effort ``service.name`` and ``service.version`` for this process.

    The order is the one the Java Spring Boot starter uses, adapted to Python:
    the installed distribution first, because a deployed application often
    ships no source manifest, then ``pyproject.toml`` for a source checkout,
    then the entrypoint basename.

    ``service.version`` has no entrypoint-derived fallback. An absent version
    is reported as ``None``, since a wrong version is worse than no version.
    """
    distribution = distribution_of_running_program()
    if distribution is not None:
        name = distribution.metadata["Name"]
        if name:
            return name, distribution.metadata["Version"] or None

    name, version = service_metadata_from_pyproject()
    if name:
        return name, version

    return detect_fallback_service_name(), None


def _merge_into_resource_attributes(attributes):
    existing = environ.get(OTEL_RESOURCE_ATTRIBUTES, "")
    present_keys = {
        pair.partition("=")[0].strip() for pair in existing.split(",") if pair.strip()
    }
    additions = [
        f"{key}={value}" for key, value in attributes.items() if key not in present_keys
    ]
    if not additions:
        return
    parts = [existing] if existing.strip() else []
    parts.extend(additions)
    environ[OTEL_RESOURCE_ATTRIBUTES] = ",".join(parts)


def apply_detected_resource_attributes(version):
    attributes = distribution_resource_attributes(version)

    if not is_false(environ.get(DASH0_AUTOMATIC_SERVICE_NAME)) and (
        not _service_name_already_configured()
    ):
        name, service_version = detect_service_metadata()
        if name:
            environ[OTEL_SERVICE_NAME] = name
        if service_version:
            attributes[_SERVICE_VERSION] = service_version

    pod_uid = detect_kubernetes_pod_uid()
    if pod_uid:
        attributes[_K8S_POD_UID] = pod_uid
    _merge_into_resource_attributes(attributes)


def _detected_service_metadata():
    """The service attributes the environment-variable path would produce.

    ``OTEL_SERVICE_NAME`` wins (mirroring the declarative ``service`` detector,
    which also reads it) and carries no version with it. The detected name and
    version apply only when no service name is configured anywhere in the
    environment and ``DASH0_AUTOMATIC_SERVICE_NAME`` is not ``false``. A
    ``service.name`` embedded in ``OTEL_RESOURCE_ATTRIBUTES`` suppresses
    detection but is not resurrected here, because declarative configuration
    ignores that variable by design.
    """
    explicit = environ.get(OTEL_SERVICE_NAME, "").strip()
    if explicit:
        return explicit, None
    if is_false(environ.get(DASH0_AUTOMATIC_SERVICE_NAME)):
        return None, None
    if _service_name_already_configured():
        return None, None
    return detect_service_metadata()


class Dash0DistributionResourceDetector(ResourceDetector):
    """Reports ``telemetry.distro.name`` and ``telemetry.distro.version``.

    The environment-variable injection above does not survive declarative
    configuration: when ``OTEL_CONFIG_FILE`` is set, the declarative resource
    builder ignores ``OTEL_RESOURCE_ATTRIBUTES``/``OTEL_SERVICE_NAME`` and only
    runs detectors named in the config file, resolved via the
    ``opentelemetry_resource_detector`` entry-point group. This detector and
    its two siblings below are registered there (``dash0_distribution``,
    ``dash0_kubernetes``, ``dash0_service_name``) and work with
    ``OTEL_EXPERIMENTAL_RESOURCE_DETECTORS`` as well.
    """

    def detect(self):
        return Resource(distribution_resource_attributes(__version__))


class Dash0KubernetesResourceDetector(ResourceDetector):
    """Reports ``k8s.pod.uid``, detected from ``/etc/hosts`` and the cgroups."""

    def detect(self):
        pod_uid = detect_kubernetes_pod_uid()
        if pod_uid:
            return Resource({_K8S_POD_UID: pod_uid})
        return Resource.get_empty()


class Dash0ServiceNameResourceDetector(ResourceDetector):
    """Service detection: the upstream behavior plus the Dash0 fallback.

    Wraps what upstream service detection provides — a stable
    ``service.instance.id`` (via the SDK's ``ServiceInstanceIdResourceDetector``)
    and ``service.name`` from ``OTEL_SERVICE_NAME`` — and adds the distro's
    detected ``service.name`` and ``service.version`` when no service name is
    configured (see :func:`_detected_service_metadata`).
    """

    def detect(self):
        attributes = dict(ServiceInstanceIdResourceDetector().detect().attributes)
        service_name, service_version = _detected_service_metadata()
        if service_name:
            attributes[_SERVICE_NAME] = service_name
        if service_version:
            attributes[_SERVICE_VERSION] = service_version
        return Resource(attributes)
