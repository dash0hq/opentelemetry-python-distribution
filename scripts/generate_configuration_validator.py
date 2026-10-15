"""Regenerate the declarative-configuration JSON Schema validator.

``dash0-opentelemetry-configuration`` validates ``OTEL_CONFIG_FILE`` documents
against the OpenTelemetry configuration JSON Schema. Upstream does that with
``jsonschema``, which pulls in ``attrs``, ``referencing``, ``rpds-py`` and
``jsonschema-specifications``. Every one of those lands in the tree the
injector puts on an application's ``sys.path``, and ``rpds-py`` is a compiled
extension, so the injected tree would stop being pure Python.

``fastjsonschema`` instead turns a schema into plain Python source at build
time. This script performs that generation, so the checked-in
``_generated_validator.py`` has a reproducible origin. The generated module
imports nothing but ``decimal`` and the vendored exception classes, which means
validation at runtime costs no third-party package at all.

``detailed_exceptions=False`` keeps the generated module at roughly a fifth of
the size the detailed variant would be, which halves its cold import time. The
one thing it costs is the message for a missing required property, which
degrades to a bare ``data must contain`` naming no property at all. Since a
missing required key is the mistake a configuration file is most likely to
contain, this script restores those messages afterwards: every such check is
generated as an ``if <x>__missing_keys:`` guard whose variable already holds
the missing names, so the raise is rewritten to name them.

Run it after changing ``schema.json``::

    uv run --with fastjsonschema==2.22.2 \
        python scripts/generate_configuration_validator.py

Then run the package's tests; ``tests/test_vendoring.py`` asserts the generated
module's import closure has not grown.
"""

from json import loads
from pathlib import Path
from re import subn
from sys import exit as sys_exit

from fastjsonschema import compile_to_code
from fastjsonschema import exceptions as fastjsonschema_exceptions

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
PACKAGE_ROOT: Path = (
    REPO_ROOT
    / "packages"
    / "dash0-opentelemetry-configuration"
    / "src"
    / "opentelemetry"
    / "_configuration"
)
SCHEMA: Path = PACKAGE_ROOT / "schema.json"
VALIDATOR: Path = PACKAGE_ROOT / "_generated_validator.py"
EXCEPTIONS: Path = PACKAGE_ROOT / "_validation_exceptions.py"

LICENSE_HEADER: str = (
    "# Copyright The OpenTelemetry Authors\n# SPDX-License-Identifier: Apache-2.0\n\n"
)
TRUNCATED_REQUIRED_MESSAGE: str = ' must contain ")'
MISSING_KEYS_RAISE: str = (
    r"(?P<guard>[ ]*if (?P<variable>\w+__missing_keys):\n"
    r'[ ]*raise JsonSchemaValueException\(.*?) must contain "\)'
)
NAMED_KEYS_RAISE: str = (
    r'\g<guard> must contain " + str(sorted(\g<variable>)) + " properties")'
)
VENDORED_IMPORT: str = (
    "from opentelemetry._configuration._validation_exceptions import (\n"
    "    JsonSchemaValueException,\n"
    "    JsonSchemaValuesException,\n"
    ")"
)


def main() -> int:
    code: str = compile_to_code(loads(SCHEMA.read_text()), detailed_exceptions=False)

    upstream_imports: list[str] = [
        line
        for line in code.splitlines()
        if line.startswith("from fastjsonschema import")
    ]
    if len(upstream_imports) != 1:
        print(
            f"expected exactly one 'from fastjsonschema import' line in the "
            f"generated code, found {len(upstream_imports)}: {upstream_imports}"
        )
        return 1

    truncated: int = code.count(TRUNCATED_REQUIRED_MESSAGE)
    code, rewritten = subn(MISSING_KEYS_RAISE, NAMED_KEYS_RAISE, code)
    if rewritten != truncated:
        print(
            f"expected every one of the {truncated} truncated 'must contain' "
            f"messages to sit under an '__missing_keys' guard, but only "
            f"{rewritten} did; fastjsonschema's code generation has changed"
        )
        return 1

    VALIDATOR.write_text(
        LICENSE_HEADER + code.replace(upstream_imports[0], VENDORED_IMPORT)
    )
    EXCEPTIONS.write_text(Path(fastjsonschema_exceptions.__file__).read_text())

    size: int = VALIDATOR.stat().st_size
    print(f"wrote {VALIDATOR.relative_to(REPO_ROOT)} ({size} bytes)")
    print(f"wrote {EXCEPTIONS.relative_to(REPO_ROOT)}")
    print(f"named the missing properties in {rewritten} required-key messages")
    return 0


if __name__ == "__main__":
    sys_exit(main())
