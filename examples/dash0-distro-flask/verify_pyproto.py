"""Build-time probe: fail unless the agent tree is pure-Python pyproto.

The environment the distribution is injected into may legitimately contain
grpcio or google.protobuf as application dependencies, so their mere presence
proves nothing and must not fail the build. What must hold, and what this
probe checks, is that:

1. every package the agent pulls in, transitively, is either an
   ``opentelemetry-*`` package or one of a small, explicitly allowed set of
   pure-Python support libraries;
2. the OTLP exporter modules resolve to the pure-Python implementations;
3. importing those exporters imports neither grpc nor google.protobuf.

Check 1 is an allowlist, not a denylist of known-native packages: anything the
agent starts requiring that is not vetted here - grpcio and protobuf included,
but also anything new a version bump might drag in - fails the build until a
human decides it belongs.
"""

import re
import sys
from importlib.metadata import PackageNotFoundError, requires

AGENT_PACKAGES = (
    "opentelemetry-pyproto",
    "opentelemetry-exporter-otlp-pyproto-common",
    "opentelemetry-exporter-otlp-pyproto-http",
    "opentelemetry-exporter-otlp-pyproto-grpc",
    "dash0-opentelemetry-distro",
)
# The non-opentelemetry-* packages the agent is allowed to pull in transitively,
# as PEP 503-normalized names. Most are pure-Python support libraries of
# opentelemetry-api/sdk/instrumentation; psutil (required by
# opentelemetry-instrumentation-system-metrics) is the one exception - it carries
# a compiled extension but is deliberately accepted so the curated set can ship
# system metrics. Everything else - including grpcio and protobuf - is rejected.
# Keep this list in sync when bumping the pinned opentelemetry versions in
# dash0-opentelemetry-distro's pyproject.toml.
ALLOWED_NON_OTEL_REQUIREMENTS = (
    "asgiref",
    "packaging",
    "psutil",
    "typing-extensions",
    "wrapt",
)
FORBIDDEN_MODULES = ("grpc", "google.protobuf")


def _requirement_name(requirement):
    name = re.split(r"[\s\[<>=!~;(]", requirement.strip(), maxsplit=1)[0].lower()
    # Normalize per PEP 503 so e.g. "typing_extensions" matches "typing-extensions".
    return re.sub(r"[-_.]+", "-", name)


def check_requirements():
    """Walk the agent packages' transitive requirements against the allowlist."""
    seen = set()
    queue = list(AGENT_PACKAGES)
    while queue:
        package = queue.pop()
        if package in seen:
            continue
        seen.add(package)
        try:
            requirements = requires(package) or []
        except PackageNotFoundError:
            continue
        for requirement in requirements:
            # Requirements guarded by an extras marker are not installed by a
            # plain install, so they do not end up in the injected tree.
            if "extra ==" in requirement:
                continue
            name = _requirement_name(requirement)
            assert (
                name.startswith("opentelemetry-")
                or name in ALLOWED_NON_OTEL_REQUIREMENTS
            ), (
                f"{package} requires {name}, which is neither an "
                f"opentelemetry-* package nor an explicitly allowed "
                f"pure-Python dependency - NOT pure-Python pyproto"
            )
            queue.append(name)


def check_exporters():
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter as GrpcSpanExporter,
    )
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter as HttpSpanExporter,
    )

    assert HttpSpanExporter.__module__.startswith(
        "opentelemetry.exporter.otlp._proto.http"
    ), HttpSpanExporter.__module__
    assert GrpcSpanExporter.__module__.startswith(
        "opentelemetry.exporter.otlp._proto.grpc"
    ), GrpcSpanExporter.__module__

    # Importing the exporters must not have imported the native modules; this
    # holds whether or not the application has them installed.
    for module in FORBIDDEN_MODULES:
        assert module not in sys.modules, (
            f"importing the exporters imported {module} - NOT pure-Python pyproto"
        )
    return HttpSpanExporter, GrpcSpanExporter


check_requirements()
http_exporter, grpc_exporter = check_exporters()
print(
    "pyproto verified: every requirement is opentelemetry-* or an allowed "
    "pure-Python library, no grpc/protobuf import; exporters from",
    http_exporter.__module__,
    "and",
    grpc_exporter.__module__,
)
