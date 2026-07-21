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
from os import environ, path

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


def detect_fallback_service_name():
    """Best-effort service name from the running program.

    The Node.js distribution reads ``package.json``; Python has no universal
    equivalent, so this derives a name from the entrypoint script.
    """
    argv0 = sys.argv[0] if sys.argv else ""
    if not argv0:
        return None
    name = path.basename(argv0)
    if name.endswith(".py"):
        name = name[: -len(".py")]
    return name or None


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
    if not is_false(environ.get(DASH0_AUTOMATIC_SERVICE_NAME)) and (
        not _service_name_already_configured()
    ):
        fallback = detect_fallback_service_name()
        if fallback:
            environ[OTEL_SERVICE_NAME] = fallback

    attributes = distribution_resource_attributes(version)
    pod_uid = detect_kubernetes_pod_uid()
    if pod_uid:
        attributes[_K8S_POD_UID] = pod_uid
    _merge_into_resource_attributes(attributes)


def _detected_service_name():
    """The ``service.name`` the environment-variable path would produce.

    ``OTEL_SERVICE_NAME`` wins (mirroring the declarative ``service`` detector,
    which also reads it); the entrypoint-derived fallback applies only when no
    service name is configured anywhere in the environment and
    ``DASH0_AUTOMATIC_SERVICE_NAME`` is not ``false``. A ``service.name``
    embedded in ``OTEL_RESOURCE_ATTRIBUTES`` suppresses the fallback but is not
    resurrected here — declarative configuration ignores that variable by
    design.
    """
    explicit = environ.get(OTEL_SERVICE_NAME, "").strip()
    if explicit:
        return explicit
    if is_false(environ.get(DASH0_AUTOMATIC_SERVICE_NAME)):
        return None
    if _service_name_already_configured():
        return None
    return detect_fallback_service_name()


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
    entrypoint-derived ``service.name`` fallback when no service name is
    configured (see :func:`_detected_service_name`).
    """

    def detect(self):
        attributes = dict(ServiceInstanceIdResourceDetector().detect().attributes)
        service_name = _detected_service_name()
        if service_name:
            attributes[_SERVICE_NAME] = service_name
        return Resource(attributes)
