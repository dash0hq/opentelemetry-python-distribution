# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Vendored, dependency-free replacements for the subset of ``packaging`` used
by the injector bootstrap script (``sitecustomize.py``).

This package exists so that the distribution's own code does not import
``packaging`` at runtime. Only the behaviour actually relied on by
``sitecustomize.py``'s dependency-conflict check is implemented, following
PEP 440 (versions and specifiers) and PEP 508 (requirements and environment
markers).

This is a verbatim copy (only the internal import paths are rewritten) of
``opentelemetry.instrumentation._packaging``, introduced upstream in
open-telemetry/opentelemetry-python-contrib#4883. It is vendored here because
that upstream removal is not guaranteed to land.

TO BE REMOVED: once the same local implementation is available in
``opentelemetry-instrumentation`` (i.e. it ships ``_packaging`` in a release
this distribution pins), delete this vendored package together with its
``tests/test_packaging_*.py`` and repoint the imports in ``sitecustomize.py``
(and the tests) to ``opentelemetry.instrumentation._packaging`` instead.
"""
