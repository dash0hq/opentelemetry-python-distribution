# -*- coding: utf-8 -*-
# Bootstrap script for injector-based activation of the Dash0 OpenTelemetry distribution for Python.
#
# This file ships inside the dash0-opentelemetry wheel, but it is not meant to be imported from its packaged
# location (importing it executes it). Consumers that build an injectable tree — such as the dash0-operator's
# instrumentation image build — install the distribution into a self-contained directory
# (`pip install --target <dir> dash0-opentelemetry`) and copy this file from its packaged location to
# `<dir>/sitecustomize.py`. The OpenTelemetry injector (https://github.com/open-telemetry/opentelemetry-injector) then
# prepends `<dir>` to the PYTHONPATH environment variable of the processes to instrument, so that Python's `site`
# machinery imports this script on interpreter startup. The script initializes the OpenTelemetry
# auto-instrumentation after a set of safety checks, and deactivates itself (also for child processes) when any of
# them fails.
#
# The dependency-conflict check reads `<dir>/all-dependencies.txt`, a flattened list of every requirement of the
# injected tree (one PEP 508 requirement per line). The consumer generates that file when building `<dir>`; the
# dash0-operator does so with pipdeptree (see images/instrumentation/python/extract-flattened-requirements.sh in the
# dash0-operator repository).
#
# IMPORTANT: This file must be valid Python 2.7+. The injector prepends its directory to the PYTHONPATH of any Python
# process, including processes running interpreters this distribution does not support; this script must at least
# parse there, so it can deactivate itself gracefully instead of crashing the process. The PEP-263 encoding
# declaration above must stay on the first or second line: without it, Python 2.7 rejects the file's non-ASCII
# characters at parse time.

from __future__ import print_function
import os
from os.path import dirname
import sys
from sys import path, version, version_info, stderr

required_python_major_version = 3
minimum_python_minor_version = 10

# Packages of the OpenTelemetry API layer. Applications legitimately depend on them for manual instrumentation
# without being auto-instrumented, so finding them in the application does not indicate double instrumentation.
# (Version conflicts with them are still caught by the dependency conflict check.)
double_instrumentation_check_excluded_packages = [
    "opentelemetry-api",
    "opentelemetry-semantic-conventions",
]

debug_enabled = os.environ.get("OTEL_INJECTOR_LOG_LEVEL") == "debug"


def _log_as_json_to_stderr(level, message):
    log_body = '{{"level": "{}", "message": "{}", "logger_name": "dash0"'.format(level, message)
    if level == "warn":
        # All warnings are Dash0 telemetry collection issues, hence adding the respective marker.
        log_body += ', "dash0.monitoring.telemetry_collection_issue": true'
    log_body += '}'
    print(log_body, file=stderr)


def _log_warn(message):
    _log_as_json_to_stderr("warn", message)


def _log_debug(message):
    if debug_enabled:
        _log_as_json_to_stderr("debug", message)


_log_debug("running sitecustomize.py")
_log_debug("PYTHONPATH: {}".format(os.environ.get("PYTHONPATH")))


def _print_cannot_auto_instrument_message(reason):
    if hasattr(sys, "argv"):
        # If sys.argv is available, add the full command line (" ".join(sys.argv)) to the log message, so users know
        # which Python process this is about.
        _log_warn("cannot auto-instrument Python process: {} [{}]".format(reason, " ".join(sys.argv)))
    else:
        _log_warn("cannot auto-instrument Python process: {}".format(reason))


def _self_deactivate(current_site):
    # Starting child processes is quite common in Python (e.g. gunicorn etc.), and in particular, the OpenTelemetry
    # instrumentation wrapper (e.g. opentelemetry-instrument python app.py, see
    # https://opentelemetry.io/docs/zero-code/python) does this. When self-deactivating, we need to make sure that we
    # do not only self-deactivate for the current process but also directly deactivate the OpenTelemetry injector's
    # auto-instrumentation for Python for child processes.
    # Failing to do so, in particular when the application is already instrumented with the opentelemetry-instrument
    # wrapper, might crash the child process in case of conflicting opentelemetry-* dependency versions. The reason is
    # that the child process started by opentelemetry-instrument will run e.g.
    # https://github.com/open-telemetry/opentelemetry-python-contrib/blob/v0.53b0/opentelemetry-instrumentation/src/opentelemetry/instrumentation/auto_instrumentation/_load.py
    # in the version brought in by the application. But _load.py then loads other opentelemetry-* dependencies from
    # /__otel_auto_instrumentation/agents/python/glibc/opentelemetry/instrumentation/auto_instrumentation/_load.py,
    # that is, from the packages that we provide. This happens _before_ this sitecustomize.py script runs in the child
    # process. Hence, we cannot rely on sitecustomize.py to self-deactivate in the child process, but must enforce
    # self-deactivation via environment variables.

    # Remove this site from PYTHONPATH so child processes do not attempt to load packages from us. PYTHONPATH entries
    # are separated by os.pathsep (":" on POSIX).
    current_pythonpath = os.environ.get("PYTHONPATH", "")
    pythonpath_entries = [entry for entry in current_pythonpath.split(os.pathsep) if entry != current_site]
    new_pythonpath = os.pathsep.join(pythonpath_entries)
    _log_debug('setting PYTHONPATH in _self_deactivate: "{}"'.format(new_pythonpath))
    os.environ["PYTHONPATH"] = new_pythonpath

    # The OpenTelemetry injector will also run for child processes, and it would bring back the PYTHONPATH modification
    # which we have just removed. Instruct it to not do that by disabling Python auto-instrumentation.
    _log_debug("clearing PYTHON_AUTO_INSTRUMENTATION_AGENT_PATH_PREFIX in _self_deactivate")
    os.environ["PYTHON_AUTO_INSTRUMENTATION_AGENT_PATH_PREFIX"] = ""

    if current_site in path:
        # Remove this site from the _current_ Python process, so our packages do not interfere with the application's
        # dependencies.
        path.remove(current_site)


def _shipped_opentelemetry_package_names(current_site):
    # The OpenTelemetry packages this distribution ships: the injected tree at current_site is exactly the pinned
    # dependency closure of dash0-opentelemetry (see its pyproject.toml), so enumerate the packages installed
    # there instead of maintaining a hardcoded list. Only the OpenTelemetry-related packages count for the double
    # instrumentation check; overlap on the general-purpose support packages we also ship (wrapt, psutil, ...) is
    # common and is handled by the dependency version conflict check instead.
    import importlib.metadata
    names = set()
    for dist in importlib.metadata.distributions(path=[current_site]):
        name = dist.metadata["Name"]
        if name is None:
            continue
        name = name.lower()
        if name in double_instrumentation_check_excluded_packages:
            continue
        if name.startswith(("opentelemetry-", "dash0-")):
            names.add(name)
    return names


def _check_for_double_instrumentation(current_site):
    import importlib.metadata
    packages_we_ship = _shipped_opentelemetry_package_names(current_site)
    offending_packages = []
    for dist in importlib.metadata.distributions():
        name = dist.metadata["Name"]
        if name is not None and name.lower() in packages_we_ship:
            offending_packages.append(str(dist._path))
    if offending_packages:
        _self_deactivate(current_site)
        _print_cannot_auto_instrument_message(
            "The application has OpenTelemetry dependencies which indicate that it is already instrumented. The " +
            "following problematic dependencies have been found: {}. ".format(", ".join(offending_packages)) +
            "Skipping the Dash0 Python auto-instrumentation to avoid double instrumentation. Remove the mentioned "
            "dependencies and make sure the opentelemetry-instrument wrapper executable is not used if you want to " +
            "use Dash0's Python auto-instrumentation")
        return True
    return False


def _read_all_dependencies():
    """Read all flattened dependencies from all-dependencies.txt. Returns list of requirement strings or None on error."""
    dependencies_file = os.path.join(dirname(__file__), "all-dependencies.txt")
    requirements_to_check = []
    try:
        with open(dependencies_file, "r") as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue
                requirements_to_check.append(line)
        return requirements_to_check
    except (IOError, OSError):
        return None


def _check_dependency_version_conflict(req_string, version_conflicts):
    """Check for dependency version conflict for a given requirement.

    Args:
        req_string: Requirement string (e.g., "package-name >=1.0.0")
        version_conflicts: Dictionary to accumulate version conflicts (modified in place)
    """
    import importlib.metadata
    # _packaging is a vendored, dependency-free copy of the packaging subset we
    # need. TO BE REMOVED: once opentelemetry-instrumentation ships the same
    # local implementation (opentelemetry.instrumentation._packaging) in a
    # release this distribution pins, import Requirement/Version from there and
    # delete the vendored copy. See dash0/opentelemetry/injector/_packaging.
    from dash0.opentelemetry.injector._packaging.requirements import Requirement
    from dash0.opentelemetry.injector._packaging.version import Version

    _log_debug("_check_dependency_version_conflict({})".format(req_string))
    req = Requirement(req_string)

    # Skip extras/markers for simplicity in conflict detection
    if req.marker and not req.marker.evaluate():
        return

    if req.name == "pip":
        # A lot of applications depend on pip implicitly, without actually importing it, ignore pip for the dependency
        # conflict check.
        return

    try:
        installed_distribution = importlib.metadata.distribution(req.name)
        installed_version = Version(installed_distribution.version)
        _log_debug("installed_version: {}".format(installed_version))

        # Check if installed version satisfies the requirement. Use
        # SpecifierSet.contains() rather than the `in` operator: the vendored
        # _packaging specifiers deliberately do not implement __contains__.
        if req.specifier and not req.specifier.contains(installed_version):
            _log_debug("adding version conflict for {}".format(req.name))
            version_conflicts[req.name] = {
                "version_required": str(req.specifier),
                "version_found": str(installed_version),
            }
    except importlib.metadata.PackageNotFoundError:
        _log_debug("adding version error for {}".format(req.name))
        version_conflicts[req.name] = {"error": "required package not found"}


def import_distro():
    _log_debug("checking Python version")
    current_site = dirname(__file__)

    # We cannot use `sys.version_info.major` or other named attributes, as they only got introduced only in Python 3.1.
    if version_info[0] != required_python_major_version or version_info[1] < minimum_python_minor_version:
        _self_deactivate(current_site)
        _print_cannot_auto_instrument_message("unsupported Python version: {}".format(version))
        return
    _log_debug("found eligible Python version: {}".format(version_info))

    # The Dash0 Python distribution requires DASH0_OTEL_COLLECTOR_BASE_URL to activate and derives its OTLP endpoint
    # from it. The Dash0 operator sets OTEL_EXPORTER_OTLP_ENDPOINT; bridge it here so the distribution activates
    # without requiring operator-side changes.
    if not os.environ.get("DASH0_OTEL_COLLECTOR_BASE_URL"):
        otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        if otlp_endpoint:
            _log_debug("bridging OTEL_EXPORTER_OTLP_ENDPOINT to DASH0_OTEL_COLLECTOR_BASE_URL: {}".format(otlp_endpoint))
            os.environ["DASH0_OTEL_COLLECTOR_BASE_URL"] = otlp_endpoint

    _log_debug("checking for double instrumentation")

    # Temporarily remove this site to be able to check for problematic dependencies in all other available sites.
    # Without the current site it is easier to differentiate between "our" dependencies and dependencies brought in by
    # the application under monitoring.
    # Maintenance note: After checking for double instrumentation scenarios, we add back the current site, via
    # path.append(current_site). The remove here together with the append also deliberately reorders sys.path to put
    # this site last, before evaluating conflicting dependency versions. See below for more details on that.
    path.remove(current_site)

    if _check_for_double_instrumentation(current_site):
        return

    _log_debug("no double instrumentation detected")
    _log_debug("checking for dependency conflicts")

    # This "path.append(current_site)" together with "path.remove(current_site)" executed a couple of lines above
    # effectively reorders sys.path to put this site last. This is necessary to evaluate potential conflicting
    # dependency versions.
    #
    # We will leave this reordering in effect when importing and initializing opentelemetry.instrumentation. Since we
    # have already ruled out dependency conflicts, the order should not matter, but with this re-ordering we make sure
    # the application's package versions will win over the package versions we bring (in case there are overlapping
    # dependencies).
    path.append(current_site)

    version_conflicts = {}
    requirements_to_check = _read_all_dependencies()
    if requirements_to_check is None:
        _self_deactivate(current_site)
        _print_cannot_auto_instrument_message("cannot read all-dependencies.txt for dependency conflict checking")
        return

    for req_string in requirements_to_check:
        _check_dependency_version_conflict(req_string, version_conflicts)
        if version_conflicts:
            break

    if not version_conflicts:
        try:
            _log_debug("importing and initializing the Python auto-instrumentation now")
            from opentelemetry.instrumentation import auto_instrumentation
            auto_instrumentation.initialize()
        except Exception as e:
            _self_deactivate(current_site)
            _print_cannot_auto_instrument_message(
                "error when importing/initializing the Python OpenTelemetry auto-instrumentation: {}: {}".format(
                    type(e).__name__, e))
    else:
        # Remove this site for good, we do not want to trigger dependency conflict issues.
        _self_deactivate(current_site)
        _print_cannot_auto_instrument_message("dependency conflicts: {}".format(version_conflicts))


import_distro()
