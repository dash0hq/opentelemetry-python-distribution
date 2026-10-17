"""Unit tests for the injector bootstrap script (sitecustomize.py).

The script is not importable as a regular module (importing it executes it), so
every test loads it from its packaged location and executes it under mocks.
"""

import importlib.metadata
import importlib.util
import json
import os
import sys
import unittest
from io import StringIO
from os.path import dirname as real_dirname
from unittest.mock import MagicMock, Mock, patch

# Pre-load the vendored packaging replacement into sys.modules: the tests
# execute sitecustomize.py with sys.path patched to mock entries, so the script
# could not import these modules from disk.
from dash0.opentelemetry.injector._packaging.requirements import (  # noqa: F401
    Requirement,
)
from dash0.opentelemetry.injector._packaging.version import Version  # noqa: F401

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SITECUSTOMIZE_PATH = os.path.join(
    TESTS_DIR,
    "..",
    "src",
    "dash0",
    "opentelemetry",
    "injector",
    "sitecustomize.py",
)


def load_sitecustomize_module():
    """Helper to load the sitecustomize module."""
    spec = importlib.util.spec_from_file_location(
        "sitecustomize_for_test", SITECUSTOMIZE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    return module, spec


def mocked_opentelemetry_modules():
    """sys.modules entries that satisfy the script's final import of
    opentelemetry.instrumentation.auto_instrumentation."""
    return {
        "opentelemetry": MagicMock(),
        "opentelemetry.instrumentation": MagicMock(),
        "opentelemetry.instrumentation.auto_instrumentation": MagicMock(),
    }


def auto_instrumentation_mock(modules):
    """The auto_instrumentation object the script actually ends up with.

    ``from opentelemetry.instrumentation import auto_instrumentation`` resolves
    by attribute lookup on the already-present ``opentelemetry.instrumentation``
    entry, so it is that mock's child that records the ``initialize`` call, not
    the ``opentelemetry.instrumentation.auto_instrumentation`` entry."""
    return modules["opentelemetry.instrumentation"].auto_instrumentation


def make_dist(name, dist_path, version="1.0.0"):
    """Build a mock importlib.metadata distribution.

    locate_file("") reports the directory the distribution is installed in,
    which is what the real Distribution API returns and what the script names
    in its deactivation message. real_dirname is used rather than os.path
    .dirname because several tests patch the latter."""
    dist = Mock()
    dist.metadata = {"Name": name}
    dist.version = version
    dist.locate_file = Mock(return_value=real_dirname(dist_path))
    return dist


def create_distributions_side_effect(shipped_dists, app_dists):
    """Side effect for importlib.metadata.distributions: the script enumerates
    the injected site with path=[current_site] and the application's sites with
    no arguments."""

    def distributions_side_effect(*args, **kwargs):
        if args or kwargs.get("path") is not None:
            return shipped_dists
        return app_dists

    return distributions_side_effect


def create_dirname_side_effect(mock_site):
    """Create a side_effect function for os.path.dirname that returns mock_site
    on the first call, but delegates to the actual dirname function for
    subsequent calls."""
    from os.path import dirname as original_dirname

    first_call = [True]

    def dirname_side_effect(path):
        if first_call[0]:
            first_call[0] = False
            return mock_site
        return original_dirname(path)

    return dirname_side_effect


def create_sitecustomize_dirname_side_effect(mock_site):
    """os.path.dirname side effect that reports mock_site for the script's own
    __file__ every time it is asked, and delegates otherwise.

    create_dirname_side_effect answers only the first call, which is enough for
    tests whose script run reaches dirname(__file__) once. The last-resort
    handler at the bottom of the script calls it a second time, to deactivate
    after an exception escaped import_distro(), and that call has to resolve to
    the same site as the first or the assertions watch the wrong path."""
    from os.path import dirname as original_dirname

    def dirname_side_effect(path):
        if str(path).endswith("sitecustomize.py"):
            return mock_site
        return original_dirname(path)

    return dirname_side_effect


class TestImportDistro(unittest.TestCase):
    """Test suite for the import_distro function in sitecustomize.py."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        # Store original environment variables
        self.original_env = os.environ.copy()
        # Store original sys.path
        self.original_sys_path = sys.path.copy()
        # Clear relevant environment variables for clean test state
        for key in [
            "OTEL_INJECTOR_LOG_LEVEL",
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "DASH0_OTEL_COLLECTOR_BASE_URL",
        ]:
            os.environ.pop(key, None)

    def tearDown(self):
        """Clean up after each test method."""
        # Restore original environment
        os.environ.clear()
        os.environ.update(self.original_env)
        # Restore original sys.path
        sys.path = self.original_sys_path.copy()

    @patch("sys.stderr", new_callable=StringIO)
    @patch("sys.version_info", (2, 7, 0, "final", 0))
    @patch("sys.version", "2.7.0")
    def test_python_2_7_too_old(self, mock_stderr):
        """Test that Python versions older than 3.10 are rejected."""
        mock_site = "/mock/site-packages"

        with patch(
            "os.path.dirname", side_effect=create_dirname_side_effect(mock_site)
        ):
            with patch("sys.path", [mock_site]):
                module, spec = load_sitecustomize_module()
                spec.loader.exec_module(module)

        output = mock_stderr.getvalue()
        self.assertIn(
            '"level": "warn", "message": "cannot auto-instrument Python process:'
            " unsupported Python version: 2.7.0",
            output,
        )

    @patch("sys.stderr", new_callable=StringIO)
    @patch("sys.version_info", (3, 9, 0, "final", 0))
    @patch("sys.version", "3.9.0")
    def test_python_3_9_too_old(self, mock_stderr):
        """Test that Python 3.9 is rejected (needs 3.10+)."""
        mock_site = "/mock/site-packages"

        with patch(
            "os.path.dirname", side_effect=create_dirname_side_effect(mock_site)
        ):
            with patch("sys.path", [mock_site]):
                module, spec = load_sitecustomize_module()
                spec.loader.exec_module(module)

        output = mock_stderr.getvalue()
        self.assertIn(
            '"level": "warn", "message": "cannot auto-instrument Python process:'
            " unsupported Python version: 3.9.0",
            output,
        )

    @patch("sys.stderr", new_callable=StringIO)
    @patch("sys.version_info", (3, 8, 0, "final", 0))
    @patch("sys.version", "3.8.0")
    def test_self_deactivate_removes_site_from_pythonpath_no_other_sites(
        self, mock_stderr
    ):
        """Test that self-deactivation removes the current site from PYTHONPATH
        and clears PYTHON_AUTO_INSTRUMENTATION_AGENT_PATH_PREFIX."""
        mock_site = "/mock/site-packages"
        os.environ["PYTHONPATH"] = "/mock/site-packages"

        with patch(
            "os.path.dirname", side_effect=create_dirname_side_effect(mock_site)
        ):
            with patch("sys.path", [mock_site]):
                module, spec = load_sitecustomize_module()
                spec.loader.exec_module(module)

        self.assertEqual(os.environ.get("PYTHONPATH"), "")
        self.assertEqual(
            os.environ.get("PYTHON_AUTO_INSTRUMENTATION_AGENT_PATH_PREFIX"), ""
        )

    @patch("sys.stderr", new_callable=StringIO)
    @patch("sys.version_info", (3, 8, 0, "final", 0))
    @patch("sys.version", "3.8.0")
    def test_self_deactivate_removes_site_from_pythonpath_other_sites_present(
        self, mock_stderr
    ):
        """Test that self-deactivation removes the current site from PYTHONPATH
        and clears PYTHON_AUTO_INSTRUMENTATION_AGENT_PATH_PREFIX."""
        mock_site = "/mock/site-packages"
        os.environ["PYTHONPATH"] = os.pathsep.join(
            ["/other/path", "/mock/site-packages", "/another/path"]
        )

        with patch(
            "os.path.dirname", side_effect=create_dirname_side_effect(mock_site)
        ):
            with patch("sys.path", [mock_site]):
                module, spec = load_sitecustomize_module()
                spec.loader.exec_module(module)

        self.assertEqual(
            os.environ.get("PYTHONPATH"),
            os.pathsep.join(["/other/path", "/another/path"]),
        )
        self.assertEqual(
            os.environ.get("PYTHON_AUTO_INSTRUMENTATION_AGENT_PATH_PREFIX"), ""
        )

    @patch("sys.stderr", new_callable=StringIO)
    @patch("sys.version_info", (3, 10, 0, "final", 0))
    def test_bridges_otlp_endpoint_to_dash0_collector_base_url(self, mock_stderr):
        """Test that OTEL_EXPORTER_OTLP_ENDPOINT is bridged to
        DASH0_OTEL_COLLECTOR_BASE_URL."""
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://collector.local:4318"
        mock_site = "/mock/site-packages"

        mock_packaging = Mock()
        mock_packaging.version = "21.0"

        with patch(
            "os.path.dirname", side_effect=create_dirname_side_effect(mock_site)
        ):
            with patch("sys.path", [mock_site]):
                with patch(
                    "builtins.open",
                    unittest.mock.mock_open(read_data="packaging >=20.0\n"),
                ):
                    with patch("importlib.metadata.distribution") as mock_dist:
                        mock_dist.return_value = mock_packaging
                        with patch.dict("sys.modules", mocked_opentelemetry_modules()):
                            module, spec = load_sitecustomize_module()
                            spec.loader.exec_module(module)

        self.assertEqual(
            os.environ.get("DASH0_OTEL_COLLECTOR_BASE_URL"),
            "http://collector.local:4318",
        )

    @patch("sys.stderr", new_callable=StringIO)
    @patch("sys.version_info", (3, 10, 0, "final", 0))
    def test_does_not_override_existing_dash0_collector_base_url(self, mock_stderr):
        """Test that a pre-existing DASH0_OTEL_COLLECTOR_BASE_URL is not
        overwritten."""
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://collector.local:4318"
        os.environ["DASH0_OTEL_COLLECTOR_BASE_URL"] = "http://pre-configured.local:4318"
        mock_site = "/mock/site-packages"

        mock_packaging = Mock()
        mock_packaging.version = "21.0"

        with patch(
            "os.path.dirname", side_effect=create_dirname_side_effect(mock_site)
        ):
            with patch("sys.path", [mock_site]):
                with patch(
                    "builtins.open",
                    unittest.mock.mock_open(read_data="packaging >=20.0\n"),
                ):
                    with patch("importlib.metadata.distribution") as mock_dist:
                        mock_dist.return_value = mock_packaging
                        with patch.dict("sys.modules", mocked_opentelemetry_modules()):
                            module, spec = load_sitecustomize_module()
                            spec.loader.exec_module(module)

        self.assertEqual(
            os.environ.get("DASH0_OTEL_COLLECTOR_BASE_URL"),
            "http://pre-configured.local:4318",
        )

    @patch("sys.stderr", new_callable=StringIO)
    @patch("sys.version_info", (3, 10, 0, "final", 0))
    def test_dependency_conflict_detection(self, mock_stderr):
        """Test that dependency version conflicts are detected."""
        mock_site = "/mock/site-packages"

        # Create mock distribution with conflicting version
        mock_packaging = Mock()
        mock_packaging.version = "19.0"  # Too old

        with patch(
            "os.path.dirname", side_effect=create_dirname_side_effect(mock_site)
        ):
            with patch("sys.path", [mock_site]):
                # Mock _read_all_dependencies to return a requirement that will
                # conflict
                with patch(
                    "builtins.open",
                    unittest.mock.mock_open(read_data="packaging >=20.0\n"),
                ):
                    with patch("importlib.metadata.distribution") as mock_dist:

                        def dist_side_effect(name):
                            if name == "packaging":
                                return mock_packaging
                            # Return mocks for other packages
                            return Mock()

                        mock_dist.side_effect = dist_side_effect

                        module, spec = load_sitecustomize_module()
                        spec.loader.exec_module(module)

        output = mock_stderr.getvalue()
        # Should report dependency conflicts
        self.assertIn(
            '"level": "warn", "message": "cannot auto-instrument Python process:'
            " dependency conflicts: packaging (requires >=20.0, found 19.0)",
            output,
        )

    @patch("sys.stderr", new_callable=StringIO)
    @patch("sys.version_info", (3, 10, 0, "final", 0))
    def test_successful_initialization(self, mock_stderr):
        """Test successful auto-instrumentation initialization."""
        os.environ["OTEL_INJECTOR_LOG_LEVEL"] = "debug"
        mock_site = "/mock/site-packages"

        # Create mock distribution with matching version
        mock_packaging = Mock()
        mock_packaging.version = "21.0"  # Satisfies >=20.0

        with patch(
            "os.path.dirname", side_effect=create_dirname_side_effect(mock_site)
        ):
            with patch("sys.path", [mock_site]):
                # Mock _read_all_dependencies to return a requirement that is
                # satisfied
                with patch(
                    "builtins.open",
                    unittest.mock.mock_open(read_data="packaging >=20.0\n"),
                ):
                    with patch("importlib.metadata.distribution") as mock_dist:
                        mock_dist.return_value = mock_packaging
                        with patch.dict("sys.modules", mocked_opentelemetry_modules()):
                            module, spec = load_sitecustomize_module()
                            spec.loader.exec_module(module)

        output = mock_stderr.getvalue()
        self.assertIn(
            '"level": "debug", "message": "importing and initializing the Python'
            " auto-instrumentation now",
            output,
        )

    @patch("sys.stderr", new_callable=StringIO)
    @patch("sys.version_info", (3, 10, 0, "final", 0))
    def test_package_not_found_in_dependency_tree(self, mock_stderr):
        """Test dependency conflict when a required package is missing."""
        mock_site = "/mock/site-packages"

        with patch(
            "os.path.dirname", side_effect=create_dirname_side_effect(mock_site)
        ):
            with patch("sys.path", [mock_site]):
                # Mock _read_all_dependencies to return a requirement for a
                # missing package
                with patch(
                    "builtins.open",
                    unittest.mock.mock_open(read_data="missing-package >=1.0\n"),
                ):
                    with patch("importlib.metadata.distribution") as mock_dist:

                        def dist_side_effect(name):
                            if name == "missing-package":
                                # This dependency is not found
                                raise importlib.metadata.PackageNotFoundError()
                            # Other packages exist
                            return Mock()

                        mock_dist.side_effect = dist_side_effect

                        module, spec = load_sitecustomize_module()
                        spec.loader.exec_module(module)

        output = mock_stderr.getvalue()
        # Should report dependency conflicts for the missing required package
        self.assertIn(
            '"level": "warn", "message": "cannot auto-instrument Python process:'
            " dependency conflicts",
            output,
        )

    @patch("sys.stderr", new_callable=StringIO)
    @patch("sys.version_info", (3, 10, 0, "final", 0))
    def test_double_instrumentation_detected_single_package(self, mock_stderr):
        """Test that double instrumentation is detected when the application
        ships an OpenTelemetry package that the injected tree also ships."""
        mock_site = "/mock/site-packages"

        shipped = [
            make_dist(
                "opentelemetry-sdk",
                "/mock/site-packages/opentelemetry_sdk-1.44.0.dist-info",
            )
        ]
        app = [
            make_dist(
                "opentelemetry-sdk",
                "/app/site-packages/opentelemetry_sdk-1.0.0.dist-info",
            )
        ]

        with patch(
            "os.path.dirname", side_effect=create_dirname_side_effect(mock_site)
        ):
            with patch("sys.path", [mock_site]):
                with patch(
                    "importlib.metadata.distributions",
                    side_effect=create_distributions_side_effect(shipped, app),
                ):
                    module, spec = load_sitecustomize_module()
                    spec.loader.exec_module(module)

        output = mock_stderr.getvalue()
        self.assertIn(
            '"level": "warn", "message": "cannot auto-instrument Python process:'
            " The application has OpenTelemetry dependencies which indicate that"
            " it is already instrumented. The following problematic dependencies"
            " have been found:"
            " opentelemetry-sdk 1.0.0 (/app/site-packages). Skipping the"
            " Dash0 Python auto-instrumentation to avoid double instrumentation.",
            output,
        )
        self.assertIn("opentelemetry-sdk 1.0.0 (/app/site-packages)", output)
        # Verify self-deactivation happened
        self.assertEqual(
            os.environ.get("PYTHON_AUTO_INSTRUMENTATION_AGENT_PATH_PREFIX"), ""
        )

    @patch("sys.stderr", new_callable=StringIO)
    @patch("sys.version_info", (3, 10, 0, "final", 0))
    def test_double_instrumentation_detected_multiple_packages(self, mock_stderr):
        """Test that all offending packages are listed when multiple are found."""
        mock_site = "/mock/site-packages"

        shipped = [
            make_dist(
                "opentelemetry-sdk",
                "/mock/site-packages/opentelemetry_sdk-1.44.0.dist-info",
            ),
            make_dist(
                "opentelemetry-instrumentation",
                "/mock/site-packages/opentelemetry_instrumentation-0.65b0.dist-info",
            ),
        ]
        app = [
            make_dist(
                "opentelemetry-sdk",
                "/app/site-packages/opentelemetry_sdk-1.0.0.dist-info",
            ),
            make_dist(
                "opentelemetry-instrumentation",
                "/app/site-packages/opentelemetry_instrumentation-1.0.0.dist-info",
            ),
        ]

        with patch(
            "os.path.dirname", side_effect=create_dirname_side_effect(mock_site)
        ):
            with patch("sys.path", [mock_site]):
                with patch(
                    "importlib.metadata.distributions",
                    side_effect=create_distributions_side_effect(shipped, app),
                ):
                    module, spec = load_sitecustomize_module()
                    spec.loader.exec_module(module)

        output = mock_stderr.getvalue()
        self.assertIn(
            '"level": "warn", "message": "cannot auto-instrument Python process:'
            " The application has OpenTelemetry dependencies which indicate that"
            " it is already instrumented. The following problematic dependencies"
            " have been found:",
            output,
        )
        self.assertIn("opentelemetry-sdk 1.0.0 (/app/site-packages)", output)
        self.assertIn(
            "opentelemetry-instrumentation 1.0.0 (/app/site-packages)", output
        )

    @patch("sys.stderr", new_callable=StringIO)
    @patch("sys.version_info", (3, 10, 0, "final", 0))
    def test_no_double_instrumentation_with_no_otel_packages(self, mock_stderr):
        """Test that unrelated packages do not trigger double instrumentation."""
        os.environ["OTEL_INJECTOR_LOG_LEVEL"] = "debug"
        mock_site = "/mock/site-packages"

        shipped = [
            make_dist(
                "opentelemetry-sdk",
                "/mock/site-packages/opentelemetry_sdk-1.44.0.dist-info",
            )
        ]
        app = [make_dist("flask", "/app/site-packages/flask-2.0.0.dist-info")]

        mock_packaging = Mock()
        mock_packaging.version = "21.0"

        with patch(
            "os.path.dirname", side_effect=create_dirname_side_effect(mock_site)
        ):
            with patch("sys.path", [mock_site]):
                with patch(
                    "importlib.metadata.distributions",
                    side_effect=create_distributions_side_effect(shipped, app),
                ):
                    with patch(
                        "builtins.open",
                        unittest.mock.mock_open(read_data="packaging >=20.0\n"),
                    ):
                        with patch("importlib.metadata.distribution") as mock_dist_fn:
                            mock_dist_fn.return_value = mock_packaging
                            with patch.dict(
                                "sys.modules", mocked_opentelemetry_modules()
                            ):
                                module, spec = load_sitecustomize_module()
                                spec.loader.exec_module(module)

        output = mock_stderr.getvalue()
        self.assertIn(
            '"level": "debug", "message": "no double instrumentation detected',
            output,
        )
        self.assertIn(
            '"level": "debug", "message": "importing and initializing the Python'
            " auto-instrumentation now",
            output,
        )

    @patch("sys.stderr", new_callable=StringIO)
    @patch("sys.version_info", (3, 10, 0, "final", 0))
    def test_no_double_instrumentation_with_api_layer_packages(self, mock_stderr):
        """Test that API-layer packages (used for manual instrumentation) in the
        application do not trigger double instrumentation, even though the
        injected tree ships them too."""
        os.environ["OTEL_INJECTOR_LOG_LEVEL"] = "debug"
        mock_site = "/mock/site-packages"

        shipped = [
            make_dist(
                "opentelemetry-api",
                "/mock/site-packages/opentelemetry_api-1.44.0.dist-info",
            ),
            make_dist(
                "opentelemetry-sdk",
                "/mock/site-packages/opentelemetry_sdk-1.44.0.dist-info",
            ),
        ]
        app = [
            make_dist(
                "opentelemetry-api",
                "/app/site-packages/opentelemetry_api-1.44.0.dist-info",
            ),
            make_dist(
                "opentelemetry-semantic-conventions",
                "/app/site-packages/opentelemetry_semantic_conventions-0.65b0.dist-info",
            ),
        ]

        mock_packaging = Mock()
        mock_packaging.version = "21.0"

        with patch(
            "os.path.dirname", side_effect=create_dirname_side_effect(mock_site)
        ):
            with patch("sys.path", [mock_site]):
                with patch(
                    "importlib.metadata.distributions",
                    side_effect=create_distributions_side_effect(shipped, app),
                ):
                    with patch(
                        "builtins.open",
                        unittest.mock.mock_open(read_data="packaging >=20.0\n"),
                    ):
                        with patch("importlib.metadata.distribution") as mock_dist_fn:
                            mock_dist_fn.return_value = mock_packaging
                            with patch.dict(
                                "sys.modules", mocked_opentelemetry_modules()
                            ):
                                module, spec = load_sitecustomize_module()
                                spec.loader.exec_module(module)

        output = mock_stderr.getvalue()
        self.assertIn(
            '"level": "debug", "message": "no double instrumentation detected',
            output,
        )
        self.assertIn(
            '"level": "debug", "message": "importing and initializing the Python'
            " auto-instrumentation now",
            output,
        )


class DistributionFromAnotherFinder:
    """A distribution that does not come from the path-based finder.

    importlib.metadata.Distribution defines locate_file() but not _path, which
    belongs to the path-based implementation alone, so reading _path here raises
    AttributeError the way it does for any other finder."""

    def __init__(self, name, location, version="1.0.0"):
        self.metadata = {"Name": name}
        self.version = version
        self._location = location

    def locate_file(self, path):
        return self._location


class TestOffendingPackagesAreReportedViaThePublicApi(unittest.TestCase):
    """The deactivation message has to be built from API a Distribution is
    guaranteed to have, and has to say enough to act on."""

    def setUp(self):
        self.original_env = os.environ.copy()
        self.original_sys_path = sys.path.copy()
        for key in [
            "OTEL_INJECTOR_LOG_LEVEL",
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "DASH0_OTEL_COLLECTOR_BASE_URL",
        ]:
            os.environ.pop(key, None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)
        sys.path = self.original_sys_path.copy()

    def run_script_with_application_distribution(self, app_distribution):
        mock_site = "/mock/site-packages"
        shipped = [
            make_dist(
                "opentelemetry-sdk",
                "/mock/site-packages/opentelemetry_sdk-1.44.0.dist-info",
                version="1.44.0",
            ),
            make_dist(
                "opentelemetry-instrumentation",
                "/mock/site-packages/opentelemetry_instrumentation-0.65b0.dist-info",
                version="0.65b0",
            ),
        ]

        stream = StringIO()
        with patch("sys.stderr", stream):
            with patch("sys.version_info", (3, 10, 0, "final", 0)):
                with patch(
                    "os.path.dirname", side_effect=create_dirname_side_effect(mock_site)
                ):
                    with patch("sys.path", [mock_site]):
                        with patch(
                            "importlib.metadata.distributions",
                            side_effect=create_distributions_side_effect(
                                shipped, [app_distribution]
                            ),
                        ):
                            module, spec = load_sitecustomize_module()
                            spec.loader.exec_module(module)
        return stream.getvalue()

    def test_a_distribution_from_another_finder_is_still_reported(self):
        """Reading the private _path raised AttributeError for any finder other
        than the path-based one."""
        output = self.run_script_with_application_distribution(
            DistributionFromAnotherFinder(
                "opentelemetry-sdk", "/app/site-packages", version="1.0.0"
            )
        )
        self.assertIn("already instrumented", output)
        self.assertIn("opentelemetry-sdk 1.0.0 (/app/site-packages)", output)

    def test_the_report_names_the_package_and_its_version(self):
        """A bare .dist-info path left the operator to work out which package
        to remove."""
        output = self.run_script_with_application_distribution(
            make_dist(
                "opentelemetry-instrumentation",
                "/app/site-packages/opentelemetry_instrumentation-0.60b0.dist-info",
                version="0.60b0",
            )
        )
        self.assertIn(
            "opentelemetry-instrumentation 0.60b0 (/app/site-packages)", output
        )


class TestDiagnosticHelperNaming(unittest.TestCase):
    """The helper logs a warning, it does not print, and the repository's
    convention is that a name describes precisely what the function does."""

    def test_the_warning_helper_is_named_for_what_it_does(self):
        mock_site = "/mock/site-packages"
        with patch("sys.stderr", new_callable=StringIO):
            with patch("sys.version_info", (2, 7, 0, "final", 0)):
                with patch("sys.version", "2.7.0"):
                    with patch(
                        "os.path.dirname",
                        side_effect=create_dirname_side_effect(mock_site),
                    ):
                        with patch("sys.path", [mock_site]):
                            module, spec = load_sitecustomize_module()
                            spec.loader.exec_module(module)

        self.assertTrue(hasattr(module, "_log_cannot_auto_instrument_warning"))
        self.assertFalse(hasattr(module, "_print_cannot_auto_instrument_message"))


class TestDiagnosticRecords(unittest.TestCase):
    """Every diagnostic is one line, one JSON object, written only to stderr.

    The messages embed foreign text: a command line, an exception message, a
    package version. None of it may be able to break the record."""

    def setUp(self):
        self.original_env = os.environ.copy()
        self.original_sys_path = sys.path.copy()
        for key in [
            "OTEL_INJECTOR_LOG_LEVEL",
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "DASH0_OTEL_COLLECTOR_BASE_URL",
        ]:
            os.environ.pop(key, None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)
        sys.path = self.original_sys_path.copy()

    def run_script_rejecting_python_version(self, argv=None, stream=None):
        """Run the script through the version gate, which emits exactly one
        warning, embedding " ".join(sys.argv) in it."""
        mock_site = "/mock/site-packages"
        stream = StringIO() if stream is None else stream
        argv = ["python", "app.py"] if argv is None else argv

        with patch("sys.stderr", stream):
            with patch("sys.argv", argv):
                with patch("sys.version_info", (3, 9, 0, "final", 0)):
                    with patch("sys.version", "3.9.0"):
                        with patch(
                            "os.path.dirname",
                            side_effect=create_dirname_side_effect(mock_site),
                        ):
                            with patch("sys.path", [mock_site]):
                                module, spec = load_sitecustomize_module()
                                spec.loader.exec_module(module)
        return stream

    def parsed_records(self, text):
        """Every non-empty line must be a JSON object on its own."""
        records = []
        for line in text.splitlines():
            if not line.strip():
                continue
            records.append(json.loads(line))
        return records

    def test_quotes_and_backslashes_in_the_message_stay_parseable(self):
        """An everyday command line carries both: python -c 'print("hi")'."""
        argv = ["python", "-c", 'print("hi")', "--path", "C:\\tmp"]
        output = self.run_script_rejecting_python_version(argv=argv).getvalue()

        records = self.parsed_records(output)
        self.assertEqual(len(records), 1)
        self.assertIn('python -c print("hi") --path C:\\tmp', records[0]["message"])

    def test_a_multi_line_message_stays_one_record(self):
        """Exception text routinely spans several lines, and a JSON-per-line
        consumer would see one unparsable fragment followed by more."""
        mock_site = "/mock/site-packages"
        modules = mocked_opentelemetry_modules()
        auto_instrumentation = modules["opentelemetry.instrumentation"]
        auto_instrumentation.auto_instrumentation.initialize.side_effect = ValueError(
            "first line\nsecond line\nthird line"
        )

        stream = StringIO()
        with patch("sys.stderr", stream):
            with patch("sys.version_info", (3, 10, 0, "final", 0)):
                with patch(
                    "os.path.dirname", side_effect=create_dirname_side_effect(mock_site)
                ):
                    with patch("sys.path", [mock_site]):
                        with patch(
                            "builtins.open",
                            unittest.mock.mock_open(read_data="packaging >=20.0\n"),
                        ):
                            with patch("importlib.metadata.distribution") as mock_dist:
                                mock_dist.return_value = Mock(version="26.3")
                                with patch.dict("sys.modules", modules):
                                    module, spec = load_sitecustomize_module()
                                    spec.loader.exec_module(module)

        output = stream.getvalue()
        records = self.parsed_records(output)
        self.assertEqual(len(records), 1)
        self.assertIn("first line\nsecond line\nthird line", records[0]["message"])

    def test_warnings_carry_the_telemetry_collection_issue_marker(self):
        """A guard that deactivates the distribution is a collection issue."""
        output = self.run_script_rejecting_python_version().getvalue()
        record = self.parsed_records(output)[0]
        self.assertEqual(record["level"], "warn")
        self.assertEqual(record["logger_name"], "dash0")
        self.assertTrue(record["dash0.monitoring.telemetry_collection_issue"])

    def test_debug_records_do_not_carry_the_marker(self):
        """Debug output describes normal progress, not a collection issue."""
        os.environ["OTEL_INJECTOR_LOG_LEVEL"] = "debug"
        output = self.run_script_rejecting_python_version().getvalue()
        debug_records = [
            r for r in self.parsed_records(output) if r["level"] == "debug"
        ]
        self.assertTrue(debug_records)
        for record in debug_records:
            self.assertNotIn("dash0.monitoring.telemetry_collection_issue", record)

    def test_nothing_is_written_to_stdout_when_stderr_is_none(self):
        """sys.stderr is None under pythonw and in daemonized processes, and
        print(file=None) falls through to stdout, corrupting any program whose
        stdout is its actual output."""
        mock_site = "/mock/site-packages"
        captured_stdout = StringIO()

        with patch("sys.stderr", None):
            with patch("sys.stdout", captured_stdout):
                with patch("sys.version_info", (3, 9, 0, "final", 0)):
                    with patch("sys.version", "3.9.0"):
                        with patch(
                            "os.path.dirname",
                            side_effect=create_dirname_side_effect(mock_site),
                        ):
                            with patch("sys.path", [mock_site]):
                                module, spec = load_sitecustomize_module()
                                spec.loader.exec_module(module)

        self.assertEqual(captured_stdout.getvalue(), "")

    def test_a_closed_stderr_does_not_raise(self):
        """A write to a closed descriptor would otherwise escape into
        interpreter start-up."""
        closed_stream = StringIO()
        closed_stream.close()
        try:
            self.run_script_rejecting_python_version(stream=closed_stream)
        except Exception as error:
            self.fail(f"writing a diagnostic to a closed stderr raised {error!r}")


class TestInjectorLogLevel(unittest.TestCase):
    """OTEL_INJECTOR_LOG_LEVEL names a level, so every standard level name has
    to be accepted, and a value that is not one must say so rather than read as
    "off"."""

    def setUp(self):
        self.original_env = os.environ.copy()
        self.original_sys_path = sys.path.copy()
        for key in [
            "OTEL_INJECTOR_LOG_LEVEL",
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "DASH0_OTEL_COLLECTOR_BASE_URL",
        ]:
            os.environ.pop(key, None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)
        sys.path = self.original_sys_path.copy()

    def run_script_at_level(self, level):
        """Run the script through the version gate, which emits one warning and
        nothing else, so the stderr text shows exactly which levels survive."""
        if level is not None:
            os.environ["OTEL_INJECTOR_LOG_LEVEL"] = level
        mock_site = "/mock/site-packages"

        stream = StringIO()
        with patch("sys.stderr", stream):
            with patch("sys.version_info", (3, 9, 0, "final", 0)):
                with patch("sys.version", "3.9.0"):
                    with patch(
                        "os.path.dirname",
                        side_effect=create_dirname_side_effect(mock_site),
                    ):
                        with patch("sys.path", [mock_site]):
                            module, spec = load_sitecustomize_module()
                            spec.loader.exec_module(module)
        return stream.getvalue()

    def test_debug_is_accepted_case_insensitively(self):
        """DEBUG and Debug are the same level as debug. Only the exact
        lowercase spelling used to do anything."""
        for spelling in ["debug", "DEBUG", "Debug", "  debug  "]:
            with self.subTest(spelling=spelling):
                os.environ.pop("OTEL_INJECTOR_LOG_LEVEL", None)
                output = self.run_script_at_level(spelling)
                self.assertIn('"level": "debug"', output)

    def test_levels_above_debug_suppress_debug_records(self):
        """info and warning are real levels, not synonyms for debug."""
        for level in ["info", "warning", "warn", "error", "critical"]:
            with self.subTest(level=level):
                os.environ.pop("OTEL_INJECTOR_LOG_LEVEL", None)
                output = self.run_script_at_level(level)
                self.assertNotIn('"level": "debug"', output)

    def test_no_level_can_silence_a_deactivation_warning(self):
        """The warning is the only report an operator gets when a guard
        deactivates the distribution, so critical must not suppress it."""
        for level in [None, "debug", "info", "warning", "error", "critical"]:
            with self.subTest(level=level):
                os.environ.pop("OTEL_INJECTOR_LOG_LEVEL", None)
                output = self.run_script_at_level(level)
                self.assertIn(
                    "cannot auto-instrument Python process:"
                    " unsupported Python version: 3.9.0",
                    output,
                )

    def test_unrecognized_level_is_reported_and_falls_back_to_warning(self):
        """Silence would leave the operator unable to tell a rejected value
        from a working one that had nothing to say."""
        output = self.run_script_at_level("verbose")
        self.assertIn("OTEL_INJECTOR_LOG_LEVEL='verbose' is not a level", output)
        self.assertIn("Supported levels:", output)
        self.assertIn("critical, debug, error, info, warn, warning", output)
        self.assertNotIn('"level": "debug"', output)

    def test_blank_level_is_treated_as_unset(self):
        """An empty or whitespace value is not a typo worth reporting."""
        for blank in ["", "   "]:
            with self.subTest(blank=blank):
                os.environ.pop("OTEL_INJECTOR_LOG_LEVEL", None)
                output = self.run_script_at_level(blank)
                self.assertNotIn("is not a level", output)
                self.assertNotIn('"level": "debug"', output)


class TestInjectedPathIsComparedNormalized(unittest.TestCase):
    """The injected entry is whatever string the injector was configured with,
    while current_site comes from dirname(__file__) and never carries a
    trailing separator. The two must still be recognised as the same site."""

    def setUp(self):
        self.original_env = os.environ.copy()
        self.original_sys_path = sys.path.copy()
        for key in [
            "OTEL_INJECTOR_LOG_LEVEL",
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "DASH0_OTEL_COLLECTOR_BASE_URL",
        ]:
            os.environ.pop(key, None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)
        sys.path = self.original_sys_path.copy()

    def test_trailing_separator_does_not_break_activation(self):
        """An exact-match path.remove() raised ValueError here, which escaped
        import_distro() and left the process with a traceback instead of
        instrumentation."""
        mock_site = "/mock/site-packages"
        modules = mocked_opentelemetry_modules()
        initialize = modules["opentelemetry.instrumentation"].auto_instrumentation

        stream = StringIO()
        with patch("sys.stderr", stream):
            with patch("sys.version_info", (3, 10, 0, "final", 0)):
                with patch(
                    "os.path.dirname", side_effect=create_dirname_side_effect(mock_site)
                ):
                    with patch("sys.path", [mock_site + os.sep]):
                        with patch(
                            "builtins.open",
                            unittest.mock.mock_open(read_data="packaging >=20.0\n"),
                        ):
                            with patch("importlib.metadata.distribution") as mock_dist:
                                mock_dist.return_value = Mock(version="26.3")
                                with patch.dict("sys.modules", modules):
                                    module, spec = load_sitecustomize_module()
                                    spec.loader.exec_module(module)

        self.assertNotIn("cannot auto-instrument", stream.getvalue())
        self.assertTrue(initialize.initialize.called)

    def test_trailing_separator_entry_is_removed_from_pythonpath(self):
        """Left in place, child processes keep loading the injected tree after
        this process decided not to."""
        mock_site = "/mock/site-packages"
        os.environ["PYTHONPATH"] = os.pathsep.join(
            ["/other/path", mock_site + os.sep, "/another/path"]
        )

        with patch("sys.stderr", new_callable=StringIO):
            with patch("sys.version_info", (2, 7, 0, "final", 0)):
                with patch("sys.version", "2.7.0"):
                    with patch(
                        "os.path.dirname",
                        side_effect=create_dirname_side_effect(mock_site),
                    ):
                        with patch("sys.path", [mock_site + os.sep]):
                            module, spec = load_sitecustomize_module()
                            spec.loader.exec_module(module)

        self.assertEqual(
            os.environ.get("PYTHONPATH"),
            os.pathsep.join(["/other/path", "/another/path"]),
        )

    def test_every_occurrence_is_removed_from_sys_path(self):
        """path.remove() drops only the first match, so a site listed twice
        stayed half-active after deactivation."""
        mock_site = "/mock/site-packages"
        os.environ["PYTHONPATH"] = mock_site
        path_entries = [mock_site + os.sep, "/app/site-packages", mock_site]

        with patch("sys.stderr", new_callable=StringIO):
            with patch("sys.version_info", (2, 7, 0, "final", 0)):
                with patch("sys.version", "2.7.0"):
                    with patch(
                        "os.path.dirname",
                        side_effect=create_dirname_side_effect(mock_site),
                    ):
                        with patch("sys.path", path_entries):
                            module, spec = load_sitecustomize_module()
                            spec.loader.exec_module(module)

        self.assertEqual(path_entries, ["/app/site-packages"])


class TestUnexpectedErrorIsContained(unittest.TestCase):
    """An exception escaping import_distro() must not leave the injected site
    active, and must not propagate out of interpreter start-up."""

    def setUp(self):
        self.original_env = os.environ.copy()
        self.original_sys_path = sys.path.copy()
        for key in [
            "OTEL_INJECTOR_LOG_LEVEL",
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "DASH0_OTEL_COLLECTOR_BASE_URL",
        ]:
            os.environ.pop(key, None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)
        sys.path = self.original_sys_path.copy()

    def run_script_with_the_distribution_scan_failing(self):
        """Reproduce a real failure inside import_distro(): the double
        instrumentation check enumerates the installed distributions, and that
        enumeration raises somewhere no guard in the script expects it.

        Returns the stderr text."""
        mock_site = "/mock/site-packages"
        os.environ["PYTHONPATH"] = mock_site

        stream = StringIO()
        with patch("sys.stderr", stream):
            with patch("sys.version_info", (3, 10, 0, "final", 0)):
                with patch(
                    "os.path.dirname",
                    side_effect=create_sitecustomize_dirname_side_effect(mock_site),
                ):
                    with patch("sys.path", [mock_site]):
                        with patch(
                            "importlib.metadata.distributions",
                            side_effect=ValueError("the distribution scan failed"),
                        ):
                            module, spec = load_sitecustomize_module()
                            spec.loader.exec_module(module)
        return stream.getvalue()

    def test_unexpected_error_does_not_propagate(self):
        """site.execsitecustomize() reports an escaping exception as one line
        that never names this distribution, so it must not escape."""
        try:
            self.run_script_with_the_distribution_scan_failing()
        except Exception as error:
            self.fail(f"the script let {error!r} escape interpreter start-up")

    def test_unexpected_error_is_reported(self):
        """The operator needs the exception type and message, since the script
        is the only thing that knows this was the injector."""
        output = self.run_script_with_the_distribution_scan_failing()
        self.assertIn(
            '"level": "warn", "message": "cannot auto-instrument Python process:'
            " unexpected error while deciding whether to auto-instrument:"
            " ValueError:",
            output,
        )

    def test_unexpected_error_deactivates_for_child_processes(self):
        """Without this, every child process that execs an interpreter retries
        the same failure."""
        self.run_script_with_the_distribution_scan_failing()
        self.assertEqual(os.environ.get("PYTHONPATH"), "")
        self.assertEqual(
            os.environ.get("PYTHON_AUTO_INSTRUMENTATION_AGENT_PATH_PREFIX"), ""
        )

    def test_reporting_happens_before_deactivating(self):
        """If _self_deactivate is the step that fails, the diagnostic must
        already have been written."""
        mock_site = "/mock/site-packages"
        os.environ["PYTHONPATH"] = mock_site

        stream = StringIO()
        real_environ = os.environ

        class EnvironFailingOnWrite(dict):
            def __setitem__(self, key, value):
                raise RuntimeError("the environment is not writable here")

        failing_environ = EnvironFailingOnWrite(real_environ)

        with patch("sys.stderr", stream):
            with patch("sys.version_info", (3, 10, 0, "final", 0)):
                with patch(
                    "os.path.dirname",
                    side_effect=create_sitecustomize_dirname_side_effect(mock_site),
                ):
                    with patch("sys.path", [mock_site + os.sep]):
                        with patch("os.environ", failing_environ):
                            module, spec = load_sitecustomize_module()
                            spec.loader.exec_module(module)

        self.assertIn(
            "unexpected error while deciding whether to auto-instrument",
            stream.getvalue(),
        )


class TestPackageNamesAreComparedCanonically(unittest.TestCase):
    """distributions() reports the Name each package declared, verbatim, and
    non-canonical spellings are ordinary in the wild. PEP 503 says runs of "-",
    "_" and "." all collapse to a single "-" before two names are compared."""

    def setUp(self):
        self.original_env = os.environ.copy()
        self.original_sys_path = sys.path.copy()
        for key in [
            "OTEL_INJECTOR_LOG_LEVEL",
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "DASH0_OTEL_COLLECTOR_BASE_URL",
        ]:
            os.environ.pop(key, None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)
        sys.path = self.original_sys_path.copy()

    def run_script_with_distributions(self, shipped, app):
        mock_site = "/mock/site-packages"
        stream = StringIO()
        with patch("sys.stderr", stream):
            with patch("sys.version_info", (3, 10, 0, "final", 0)):
                with patch(
                    "os.path.dirname", side_effect=create_dirname_side_effect(mock_site)
                ):
                    with patch("sys.path", [mock_site]):
                        with patch(
                            "importlib.metadata.distributions",
                            side_effect=create_distributions_side_effect(shipped, app),
                        ):
                            with patch(
                                "builtins.open",
                                unittest.mock.mock_open(read_data="packaging >=20.0\n"),
                            ):
                                with patch(
                                    "importlib.metadata.distribution"
                                ) as mock_dist:
                                    mock_dist.return_value = Mock(version="26.3")
                                    with patch.dict(
                                        "sys.modules", mocked_opentelemetry_modules()
                                    ):
                                        module, spec = load_sitecustomize_module()
                                        spec.loader.exec_module(module)
        return stream.getvalue()

    def test_non_canonical_application_name_is_still_detected(self):
        """OpenTelemetry_SDK is PEP 503 equivalent to opentelemetry-sdk, so
        activating on top of it is the double instrumentation the check exists
        to prevent."""
        shipped = [
            make_dist(
                "opentelemetry-sdk",
                "/mock/site-packages/opentelemetry_sdk-1.44.0.dist-info",
            )
        ]
        app = [
            make_dist(
                "OpenTelemetry_SDK",
                "/app/site-packages/opentelemetry_sdk-1.0.0.dist-info",
            )
        ]
        output = self.run_script_with_distributions(shipped, app)
        self.assertIn("already instrumented", output)
        self.assertIn("OpenTelemetry_SDK 1.0.0 (/app/site-packages)", output)

    def test_non_canonical_shipped_name_is_still_detected(self):
        """The shipped side is read from the injected tree and is just as free
        to declare a non-canonical Name."""
        shipped = [
            make_dist(
                "OpenTelemetry.SDK",
                "/mock/site-packages/opentelemetry_sdk-1.44.0.dist-info",
            )
        ]
        app = [
            make_dist(
                "opentelemetry-sdk",
                "/app/site-packages/opentelemetry_sdk-1.0.0.dist-info",
            )
        ]
        output = self.run_script_with_distributions(shipped, app)
        self.assertIn("already instrumented", output)

    def test_non_canonical_api_layer_name_is_still_excluded(self):
        """Applications legitimately depend on the API layer for manual
        instrumentation, and must not be reported for declaring it as
        opentelemetry_api."""
        shipped = [
            make_dist(
                "opentelemetry-api",
                "/mock/site-packages/opentelemetry_api-1.44.0.dist-info",
            ),
            make_dist(
                "opentelemetry-sdk",
                "/mock/site-packages/opentelemetry_sdk-1.44.0.dist-info",
            ),
        ]
        app = [
            make_dist(
                "opentelemetry_api",
                "/app/site-packages/opentelemetry_api-1.44.0.dist-info",
            ),
            make_dist(
                "OpenTelemetry.Semantic_Conventions",
                "/app/site-packages/opentelemetry_semantic_conventions-0.65b0.dist-info",
            ),
        ]
        output = self.run_script_with_distributions(shipped, app)
        self.assertNotIn("already instrumented", output)

    def test_unrelated_packages_are_unaffected(self):
        """Normalisation must not turn an unrelated distribution into a match."""
        shipped = [
            make_dist(
                "opentelemetry-sdk",
                "/mock/site-packages/opentelemetry_sdk-1.44.0.dist-info",
            )
        ]
        app = [
            make_dist("PyYAML", "/app/site-packages/PyYAML-6.0.dist-info"),
            make_dist("ruamel.yaml", "/app/site-packages/ruamel.yaml-0.18.dist-info"),
            make_dist(
                "typing_extensions",
                "/app/site-packages/typing_extensions-4.16.0.dist-info",
            ),
        ]
        output = self.run_script_with_distributions(shipped, app)
        self.assertNotIn("already instrumented", output)


WORKSPACE_ROOT = os.path.normpath(os.path.join(TESTS_DIR, "..", "..", ".."))


class TestShadowedUpstreamPackagesAreDetected(unittest.TestCase):
    """The pyproto packages ship under Dash0-owned distribution names while
    keeping the upstream import paths, so the application's copy of the
    upstream distribution has a different name and the same import path."""

    def setUp(self):
        self.original_env = os.environ.copy()
        self.original_sys_path = sys.path.copy()
        for key in [
            "OTEL_INJECTOR_LOG_LEVEL",
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "DASH0_OTEL_COLLECTOR_BASE_URL",
        ]:
            os.environ.pop(key, None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)
        sys.path = self.original_sys_path.copy()

    def shipped_pyproto_distributions(self):
        return [
            make_dist(
                "dash0-opentelemetry-pyproto",
                "/mock/site-packages/dash0_opentelemetry_pyproto.dist-info",
            ),
            make_dist(
                "dash0-opentelemetry-exporter-otlp-pyproto-common",
                "/mock/site-packages/dash0_otlp_pyproto_common.dist-info",
            ),
            make_dist(
                "dash0-opentelemetry-exporter-otlp-pyproto-grpc",
                "/mock/site-packages/dash0_otlp_pyproto_grpc.dist-info",
            ),
            make_dist(
                "dash0-opentelemetry-exporter-otlp-pyproto-http",
                "/mock/site-packages/dash0_otlp_pyproto_http.dist-info",
            ),
        ]

    def run_script_with_application_package(self, application_package_name):
        """Returns the stderr text and the way the deactivation message is
        expected to name the application package: its name, its version and the
        directory it is installed in."""
        mock_site = "/mock/site-packages"
        app_path = "/app/site-packages/{}-1.44.0.dist-info".format(
            application_package_name.replace("-", "_")
        )
        app = [make_dist(application_package_name, app_path)]
        expected_report = f"{application_package_name} 1.0.0 (/app/site-packages)"

        stream = StringIO()
        with patch("sys.stderr", stream):
            with patch("sys.version_info", (3, 10, 0, "final", 0)):
                with patch(
                    "os.path.dirname", side_effect=create_dirname_side_effect(mock_site)
                ):
                    with patch("sys.path", [mock_site]):
                        with patch(
                            "importlib.metadata.distributions",
                            side_effect=create_distributions_side_effect(
                                self.shipped_pyproto_distributions(), app
                            ),
                        ):
                            with patch(
                                "builtins.open",
                                unittest.mock.mock_open(read_data="packaging >=20.0\n"),
                            ):
                                with patch(
                                    "importlib.metadata.distribution"
                                ) as mock_dist:
                                    mock_dist.return_value = Mock(version="26.3")
                                    with patch.dict(
                                        "sys.modules", mocked_opentelemetry_modules()
                                    ):
                                        module, spec = load_sitecustomize_module()
                                        spec.loader.exec_module(module)
        return stream.getvalue(), expected_report

    def test_upstream_exporters_shadowed_by_pyproto_are_detected(self):
        """Each of these owns an import path one of the shipped packages also
        owns, so both in one process is double instrumentation."""
        shadowed = [
            "opentelemetry-proto",
            "opentelemetry-exporter-otlp-proto-common",
            "opentelemetry-exporter-otlp-proto-grpc",
            "opentelemetry-exporter-otlp-proto-http",
            "opentelemetry-exporter-otlp",
        ]
        for package_name in shadowed:
            with self.subTest(package=package_name):
                output, expected_report = self.run_script_with_application_package(
                    package_name
                )
                self.assertIn("already instrumented", output)
                self.assertIn(expected_report, output)

    def test_an_unrelated_package_is_still_not_reported(self):
        """The mapping must not widen the check into unrelated distributions."""
        output, _ = self.run_script_with_application_package("flask")
        self.assertNotIn("already instrumented", output)

    def test_every_shipped_pyproto_package_has_a_mapping(self):
        """The workspace is the source of truth: a pyproto package added to
        packages/ without an entry here would silently stop being detected."""
        mock_site = "/mock/site-packages"
        with patch("sys.stderr", new_callable=StringIO):
            with patch("sys.version_info", (2, 7, 0, "final", 0)):
                with patch("sys.version", "2.7.0"):
                    with patch(
                        "os.path.dirname",
                        side_effect=create_dirname_side_effect(mock_site),
                    ):
                        with patch("sys.path", [mock_site]):
                            module, spec = load_sitecustomize_module()
                            spec.loader.exec_module(module)

        mapping = module.upstream_packages_shadowed_by_shipped_packages
        shipped_pyproto_packages = sorted(
            entry
            for entry in os.listdir(os.path.join(WORKSPACE_ROOT, "packages"))
            if "pyproto" in entry
        )
        self.assertTrue(shipped_pyproto_packages)
        for package_directory in shipped_pyproto_packages:
            with self.subTest(package=package_directory):
                self.assertIn(package_directory, mapping)
                self.assertTrue(mapping[package_directory])


def make_unreadable_dist(dist_path, error=None):
    """A distribution whose METADATA cannot be decoded.

    importlib.metadata decodes METADATA as UTF-8, and a Latin-1 author field
    written by older tooling is the usual cause of this in the wild."""
    if error is None:
        error = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
    dist = Mock()
    dist.locate_file = Mock(return_value=real_dirname(dist_path))
    type(dist).metadata = property(lambda self: (_ for _ in ()).throw(error))
    return dist


class TestUnreadableInputIsSkipped(unittest.TestCase):
    """A problem in one foreign package, or in one manifest line, makes that
    one item unverifiable. It must not deactivate the whole process, and it
    must not escape into interpreter start-up."""

    def setUp(self):
        self.original_env = os.environ.copy()
        self.original_sys_path = sys.path.copy()
        for key in [
            "OTEL_INJECTOR_LOG_LEVEL",
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "DASH0_OTEL_COLLECTOR_BASE_URL",
        ]:
            os.environ.pop(key, None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)
        sys.path = self.original_sys_path.copy()

    def run_script(
        self,
        shipped=None,
        app=None,
        manifest="packaging >=20.0\n",
        installed_version="26.3",
        open_error=None,
    ):
        mock_site = "/mock/site-packages"
        modules = mocked_opentelemetry_modules()
        initialize = modules["opentelemetry.instrumentation"].auto_instrumentation

        if shipped is None:
            shipped = [
                make_dist(
                    "opentelemetry-sdk",
                    "/mock/site-packages/opentelemetry_sdk-1.44.0.dist-info",
                )
            ]
        if app is None:
            app = [make_dist("flask", "/app/site-packages/flask-2.0.0.dist-info")]

        if open_error is None:
            open_mock = unittest.mock.mock_open(read_data=manifest)
        else:
            open_mock = Mock(side_effect=open_error)

        stream = StringIO()
        with patch("sys.stderr", stream):
            with patch("sys.version_info", (3, 10, 0, "final", 0)):
                with patch(
                    "os.path.dirname", side_effect=create_dirname_side_effect(mock_site)
                ):
                    with patch("sys.path", [mock_site]):
                        with patch(
                            "importlib.metadata.distributions",
                            side_effect=create_distributions_side_effect(shipped, app),
                        ):
                            with patch("builtins.open", open_mock):
                                with patch(
                                    "importlib.metadata.distribution"
                                ) as mock_dist:
                                    mock_dist.return_value = Mock(
                                        version=installed_version
                                    )
                                    with patch.dict("sys.modules", modules):
                                        module, spec = load_sitecustomize_module()
                                        spec.loader.exec_module(module)
        return stream.getvalue(), initialize.initialize

    def test_an_unreadable_application_package_does_not_deactivate(self):
        """One package with non-UTF-8 METADATA used to abort the scan and take
        auto-instrumentation down with it."""
        app = [
            make_unreadable_dist("/app/site-packages/legacy-1.0.dist-info"),
            make_dist("flask", "/app/site-packages/flask-2.0.0.dist-info"),
        ]
        output, initialize = self.run_script(app=app)
        self.assertNotIn("cannot auto-instrument", output)
        self.assertTrue(initialize.called)

    def test_an_unreadable_application_package_is_named_in_a_warning(self):
        """The operator needs to know which package could not be checked."""
        app = [make_unreadable_dist("/app/site-packages/legacy-1.0.dist-info")]
        output, _ = self.run_script(app=app)
        self.assertIn("installed in /app/site-packages", output)
        self.assertIn("cannot be checked for double instrumentation", output)

    def test_readable_packages_are_still_checked_after_an_unreadable_one(self):
        """Skipping must not turn into stopping."""
        app = [
            make_unreadable_dist("/app/site-packages/legacy-1.0.dist-info"),
            make_dist(
                "opentelemetry-sdk",
                "/app/site-packages/opentelemetry_sdk-1.0.0.dist-info",
            ),
        ]
        output, _ = self.run_script(app=app)
        self.assertIn("already instrumented", output)
        self.assertIn("opentelemetry-sdk 1.0.0 (/app/site-packages)", output)

    def test_an_unreadable_shipped_package_does_not_deactivate(self):
        """The injected tree is scanned the same way and deserves the same
        treatment."""
        shipped = [
            make_unreadable_dist("/mock/site-packages/broken-1.0.dist-info"),
            make_dist(
                "opentelemetry-sdk",
                "/mock/site-packages/opentelemetry_sdk-1.44.0.dist-info",
            ),
        ]
        output, initialize = self.run_script(shipped=shipped)
        self.assertNotIn("cannot auto-instrument", output)
        self.assertTrue(initialize.called)

    def test_an_undecodable_manifest_deactivates_with_its_own_message(self):
        """UnicodeDecodeError was not caught, so it propagated instead of
        becoming the intended 'cannot read all-dependencies.txt'."""
        output, initialize = self.run_script(
            open_error=UnicodeDecodeError(
                "ascii", b"\xff", 0, 1, "ordinal not in range"
            )
        )
        self.assertIn(
            "cannot read all-dependencies.txt for dependency conflict checking", output
        )
        self.assertFalse(initialize.called)

    def test_an_unparsable_requirement_is_skipped_not_raised(self):
        """A line the parser rejects made Requirement() raise straight out of
        import_distro()."""
        output, initialize = self.run_script(
            manifest='alpha >="2.0"\npackaging >=20.0\n'
        )
        self.assertIn("cannot parse requirement", output)
        reported = [
            json.loads(line)["message"] for line in output.splitlines() if line.strip()
        ]
        self.assertTrue(any('alpha >="2.0"' in message for message in reported))
        self.assertNotIn("cannot auto-instrument", output)
        self.assertTrue(initialize.called)

    def test_an_unparsable_installed_version_is_skipped(self):
        """Distributions patched by Linux distributors can carry versions that
        are not valid PEP 440."""
        output, initialize = self.run_script(installed_version="not a version")
        self.assertIn("cannot parse the installed version 'not a version'", output)
        self.assertNotIn("cannot auto-instrument", output)
        self.assertTrue(initialize.called)


class TestEveryDependencyConflictIsReported(unittest.TestCase):
    """The operator has to fix all of them before the process will instrument,
    so naming one per deployment costs a deployment per conflict."""

    def setUp(self):
        self.original_env = os.environ.copy()
        self.original_sys_path = sys.path.copy()
        for key in [
            "OTEL_INJECTOR_LOG_LEVEL",
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "DASH0_OTEL_COLLECTOR_BASE_URL",
        ]:
            os.environ.pop(key, None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)
        sys.path = self.original_sys_path.copy()

    def run_script_with_manifest(self, manifest, installed_versions):
        """installed_versions maps a requirement name to the version installed,
        or to None for a package that is not installed at all."""
        mock_site = "/mock/site-packages"

        def distribution_side_effect(name):
            version = installed_versions.get(name)
            if version is None:
                raise importlib.metadata.PackageNotFoundError()
            return Mock(version=version)

        stream = StringIO()
        with patch("sys.stderr", stream):
            with patch("sys.version_info", (3, 10, 0, "final", 0)):
                with patch(
                    "os.path.dirname", side_effect=create_dirname_side_effect(mock_site)
                ):
                    with patch("sys.path", [mock_site]):
                        with patch(
                            "builtins.open",
                            unittest.mock.mock_open(read_data=manifest),
                        ):
                            with patch(
                                "importlib.metadata.distribution",
                                side_effect=distribution_side_effect,
                            ):
                                module, spec = load_sitecustomize_module()
                                spec.loader.exec_module(module)
        return stream.getvalue()

    def test_all_conflicting_packages_are_named(self):
        output = self.run_script_with_manifest(
            "alpha >=2.0\nbeta >=3.0\ngamma >=4.0\n",
            {"alpha": "1.0", "beta": "2.0", "gamma": "3.0"},
        )
        self.assertIn("alpha (requires >=2.0, found 1.0)", output)
        self.assertIn("beta (requires >=3.0, found 2.0)", output)
        self.assertIn("gamma (requires >=4.0, found 3.0)", output)

    def test_satisfied_requirements_are_not_named(self):
        output = self.run_script_with_manifest(
            "alpha >=2.0\nbeta >=3.0\n",
            {"alpha": "2.5", "beta": "2.0"},
        )
        self.assertNotIn("alpha", output)
        self.assertIn("beta (requires >=3.0, found 2.0)", output)

    def test_a_missing_package_is_reported_alongside_a_conflict(self):
        """A conflict earlier in the manifest used to stop the scan before the
        missing package was ever looked up."""
        output = self.run_script_with_manifest(
            "alpha >=2.0\nbeta >=3.0\n",
            {"alpha": "1.0", "beta": None},
        )
        self.assertIn("alpha (requires >=2.0, found 1.0)", output)
        self.assertIn("beta (required package not found)", output)

    def test_conflicts_are_rendered_in_a_stable_order(self):
        """The same set of conflicts must always read the same way, whatever
        order the manifest happens to list them in."""
        forwards = self.run_script_with_manifest(
            "alpha >=2.0\nbeta >=3.0\n", {"alpha": "1.0", "beta": "2.0"}
        )
        backwards = self.run_script_with_manifest(
            "beta >=3.0\nalpha >=2.0\n", {"alpha": "1.0", "beta": "2.0"}
        )
        self.assertIn(
            "alpha (requires >=2.0, found 1.0); beta (requires >=3.0, found 2.0)",
            forwards,
        )
        self.assertIn(
            "alpha (requires >=2.0, found 1.0); beta (requires >=3.0, found 2.0)",
            backwards,
        )

    def test_the_message_is_not_a_python_dict_repr(self):
        """The rendered text is what an operator reads, and a repr also put
        single quotes inside the JSON message field."""
        output = self.run_script_with_manifest("alpha >=2.0\n", {"alpha": "1.0"})
        self.assertNotIn("'version_required'", output)
        self.assertNotIn("'version_found'", output)


class TestInitializationFailure(unittest.TestCase):
    """initialize() must be allowed to raise, so a failed SDK start-up is
    reported and the injected site is taken back off sys.path."""

    def setUp(self):
        self.original_env = os.environ.copy()
        self.original_sys_path = sys.path.copy()
        for key in [
            "OTEL_INJECTOR_LOG_LEVEL",
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "DASH0_OTEL_COLLECTOR_BASE_URL",
        ]:
            os.environ.pop(key, None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)
        sys.path = self.original_sys_path.copy()

    def run_script_with_initialize(self, initialize_side_effect=None):
        """Execute the script far enough to reach initialize(), returning the
        stderr text and the initialize mock."""
        mock_site = "/mock/site-packages"
        os.environ["PYTHONPATH"] = mock_site
        modules = mocked_opentelemetry_modules()
        initialize = auto_instrumentation_mock(modules).initialize
        if initialize_side_effect is not None:
            initialize.side_effect = initialize_side_effect

        stream = StringIO()
        with patch("sys.stderr", stream):
            with patch("sys.version_info", (3, 10, 0, "final", 0)):
                with patch(
                    "os.path.dirname", side_effect=create_dirname_side_effect(mock_site)
                ):
                    with patch("sys.path", [mock_site]):
                        with patch(
                            "builtins.open",
                            unittest.mock.mock_open(read_data="packaging >=20.0\n"),
                        ):
                            with patch("importlib.metadata.distribution") as mock_dist:
                                mock_dist.return_value = Mock(version="26.3")
                                with patch.dict("sys.modules", modules):
                                    module, spec = load_sitecustomize_module()
                                    spec.loader.exec_module(module)
        return stream.getvalue(), initialize

    def test_initialize_is_asked_not_to_swallow_exceptions(self):
        """Without swallow_exceptions=False, initialize() logs and returns on
        failure, so the script's own error handling can never run."""
        _, initialize = self.run_script_with_initialize()
        initialize.assert_called_once_with(swallow_exceptions=False)

    def test_initialization_failure_is_reported(self):
        """A failure inside initialize() must name itself in the warning rather
        than leaving the process quietly uninstrumented."""
        output, _ = self.run_script_with_initialize(
            initialize_side_effect=ValueError("collector endpoint is not a URL")
        )
        self.assertIn(
            '"level": "warn", "message": "cannot auto-instrument Python process:'
            " error when importing/initializing the Python OpenTelemetry"
            " auto-instrumentation: ValueError: collector endpoint is not a URL",
            output,
        )

    def test_initialization_failure_deactivates_for_child_processes(self):
        """The site must come off PYTHONPATH and the injector prefix must be
        cleared, or every child process repeats the same failed start-up."""
        self.run_script_with_initialize(
            initialize_side_effect=RuntimeError("instrumentor blew up")
        )
        self.assertEqual(os.environ.get("PYTHONPATH"), "")
        self.assertEqual(
            os.environ.get("PYTHON_AUTO_INSTRUMENTATION_AGENT_PATH_PREFIX"), ""
        )


if __name__ == "__main__":
    unittest.main()
