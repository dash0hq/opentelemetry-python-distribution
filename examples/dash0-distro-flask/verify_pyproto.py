"""Build-time probe: fail unless the agent tree is pure-Python pyproto.

The environment the distribution is injected into may legitimately contain
grpcio or google.protobuf as application dependencies, so their mere presence
proves nothing and must not fail the build. What must hold, and what this
probe checks, is that:

1. no agent package requires grpcio or protobuf, directly or transitively;
2. the OTLP exporter modules resolve to the pure-Python implementations;
3. importing those exporters imports neither grpc nor google.protobuf.
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
FORBIDDEN_REQUIREMENTS = ("protobuf", "grpcio")
FORBIDDEN_MODULES = ("grpc", "google.protobuf")


def _requirement_name(requirement):
    return re.split(r"[\s\[<>=!~;(]", requirement.strip(), maxsplit=1)[0].lower()


def check_requirements():
    """Walk the agent packages' transitive requirements."""
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
            assert name not in FORBIDDEN_REQUIREMENTS, (
                f"{package} requires {name} - NOT pure-Python pyproto"
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
    "pyproto verified: no grpcio/protobuf requirement or import; exporters from",
    http_exporter.__module__,
    "and",
    grpc_exporter.__module__,
)
