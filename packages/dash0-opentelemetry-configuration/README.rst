Dash0 OpenTelemetry Declarative Configuration
=============================================

Declarative (file-based) SDK configuration for the Dash0 OpenTelemetry Python
distribution, read from ``OTEL_CONFIG_FILE``.

This package is a Dash0-owned build of ``opentelemetry-configuration``. The
implementation lives under ``opentelemetry._configuration``; the modules under
``opentelemetry.configuration`` re-export it so the SDK's declarative path and
any third-party caller resolve to this build. The ``UPSTREAM`` file records the
repository, commit and source directory the code was taken from.

The package is experimental, tracking a configuration format that is still at
``1.0-rc.1``.
