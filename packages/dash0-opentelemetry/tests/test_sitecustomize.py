"""Unit tests for the injector bootstrap script (sitecustomize.py).

The script is not importable as a regular module (importing it executes it), so
every test loads it from its packaged location and executes it under mocks.
"""

import importlib.metadata
import importlib.util
import os
import sys
import unittest
from io import StringIO
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


def make_dist(name, dist_path):
    """Build a mock importlib.metadata distribution."""
    dist = Mock()
    dist.metadata = {"Name": name}
    dist._path = dist_path
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
            " dependency conflicts: {'packaging': {'version_required': '>=20.0',"
            " 'version_found': '19.0'}}",
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
            " /app/site-packages/opentelemetry_sdk-1.0.0.dist-info. Skipping the"
            " Dash0 Python auto-instrumentation to avoid double instrumentation.",
            output,
        )
        self.assertIn("/app/site-packages/opentelemetry_sdk-1.0.0.dist-info", output)
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
        self.assertIn("/app/site-packages/opentelemetry_sdk-1.0.0.dist-info", output)
        self.assertIn(
            "/app/site-packages/opentelemetry_instrumentation-1.0.0.dist-info", output
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


if __name__ == "__main__":
    unittest.main()
