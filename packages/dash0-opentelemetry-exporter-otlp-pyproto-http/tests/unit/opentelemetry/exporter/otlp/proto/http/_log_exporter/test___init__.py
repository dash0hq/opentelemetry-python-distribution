# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# pylint: disable=protected-access

import unittest
from http.client import BadStatusLine, InvalidURL, RemoteDisconnected
from os import environ
from socket import AF_INET, SOCK_STREAM, SOL_SOCKET, SO_REUSEADDR, socket
from threading import Thread
from time import sleep
from unittest.mock import patch
from urllib.error import URLError

from opentelemetry.exporter.otlp.proto.http import Compression
from opentelemetry.exporter.otlp.proto.http._log_exporter import (
    DEFAULT_ENDPOINT,
    DEFAULT_LOGS_EXPORT_PATH,
    DEFAULT_TIMEOUT,
    OTLPLogExporter,
    _MAX_RETRYS,
    _append_logs_path,
)
from opentelemetry.sdk._logs.export import LogRecordExportResult

_UNIFORM = "opentelemetry.exporter.otlp.proto.http._log_exporter.uniform"


def _server_that_closes_after_reading_the_request():
    server = socket(AF_INET, SOCK_STREAM)
    server.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(16)
    server.settimeout(0.1)
    served = []

    def close_every_connection_without_answering():
        while server.fileno() != -1:
            try:
                connection, _ = server.accept()
            except OSError:
                continue
            served.append(connection)
            request = b""
            while b"\r\n\r\n" not in request:
                chunk = connection.recv(65536)
                if not chunk:
                    break
                request += chunk
            connection.close()

    Thread(target=close_every_connection_without_answering, daemon=True).start()
    return server, served


def _ok():
    return (200, "OK")


def _503():
    return (503, "Service Unavailable")


def _404():
    return (404, "Not Found")


class TestOTLPLogExporter(unittest.TestCase):

    # ── constructor ───────────────────────────────────────────────────────────

    def test_constructor_defaults(self):
        exporter = OTLPLogExporter()
        self.assertEqual(
            exporter._endpoint,
            DEFAULT_ENDPOINT + DEFAULT_LOGS_EXPORT_PATH,
        )
        self.assertEqual(exporter._timeout, DEFAULT_TIMEOUT)
        self.assertEqual(exporter._compression, Compression.NoCompression)
        self.assertEqual(
            exporter._request_headers["Content-Type"], "application/x-protobuf"
        )
        self.assertFalse(exporter._shutdown)
        exporter.shutdown()

    def test_generic_endpoint_env_var(self):
        with patch.dict("os.environ", {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector:4318"}):
            exporter = OTLPLogExporter()
        self.assertEqual(exporter._endpoint, "http://collector:4318/v1/logs")
        exporter.shutdown()

    def test_logs_endpoint_overrides_generic(self):
        with patch.dict("os.environ", {
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://generic:4318",
            "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "http://logs:4318/v1/logs",
        }):
            exporter = OTLPLogExporter()
        self.assertEqual(exporter._endpoint, "http://logs:4318/v1/logs")
        exporter.shutdown()

    def test_constructor_arg_overrides_env(self):
        with patch.dict("os.environ", {
            "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "http://env:4318/v1/logs",
        }):
            exporter = OTLPLogExporter(endpoint="http://arg:4318/v1/logs")
        self.assertEqual(exporter._endpoint, "http://arg:4318/v1/logs")
        exporter.shutdown()

    def test_timeout_generic_env_var(self):
        with patch.dict("os.environ", {"OTEL_EXPORTER_OTLP_TIMEOUT": "20"}):
            exporter = OTLPLogExporter()
        self.assertEqual(exporter._timeout, 20.0)
        exporter.shutdown()

    def test_timeout_logs_env_var_overrides_generic(self):
        with patch.dict("os.environ", {
            "OTEL_EXPORTER_OTLP_TIMEOUT": "20",
            "OTEL_EXPORTER_OTLP_LOGS_TIMEOUT": "5",
        }):
            exporter = OTLPLogExporter()
        self.assertEqual(exporter._timeout, 5.0)
        exporter.shutdown()

    def test_timeout_arg_overrides_env(self):
        with patch.dict("os.environ", {"OTEL_EXPORTER_OTLP_LOGS_TIMEOUT": "99"}):
            exporter = OTLPLogExporter(timeout=3)
        self.assertEqual(exporter._timeout, 3)
        exporter.shutdown()

    def test_compression_env_var_gzip(self):
        with patch.dict("os.environ", {"OTEL_EXPORTER_OTLP_COMPRESSION": "gzip"}):
            exporter = OTLPLogExporter()
        self.assertEqual(exporter._compression, Compression.Gzip)
        self.assertEqual(exporter._request_headers.get("Content-Encoding"), "gzip")
        exporter.shutdown()

    def test_compression_env_var_deflate(self):
        with patch.dict("os.environ", {"OTEL_EXPORTER_OTLP_COMPRESSION": "deflate"}):
            exporter = OTLPLogExporter()
        self.assertEqual(exporter._compression, Compression.Deflate)
        self.assertEqual(exporter._request_headers.get("Content-Encoding"), "deflate")
        exporter.shutdown()

    def test_compression_logs_env_overrides_generic(self):
        with patch.dict("os.environ", {
            "OTEL_EXPORTER_OTLP_COMPRESSION": "gzip",
            "OTEL_EXPORTER_OTLP_LOGS_COMPRESSION": "deflate",
        }):
            exporter = OTLPLogExporter()
        self.assertEqual(exporter._compression, Compression.Deflate)
        exporter.shutdown()

    def test_compression_arg_gzip(self):
        exporter = OTLPLogExporter(compression=Compression.Gzip)
        self.assertEqual(exporter._compression, Compression.Gzip)
        self.assertEqual(exporter._request_headers.get("Content-Encoding"), "gzip")
        exporter.shutdown()

    def test_no_compression_header_for_none_compression(self):
        exporter = OTLPLogExporter(compression=Compression.NoCompression)
        self.assertNotIn("Content-Encoding", exporter._request_headers)
        exporter.shutdown()

    # ── export ────────────────────────────────────────────────────────────────

    def test_export_success(self):
        exporter = OTLPLogExporter()
        with patch.object(exporter, "_export", return_value=_ok()):
            result = exporter.export([])
        self.assertEqual(result, LogRecordExportResult.SUCCESS)
        exporter.shutdown()

    def test_export_after_shutdown_returns_failure(self):
        exporter = OTLPLogExporter()
        exporter.shutdown()
        result = exporter.export([])
        self.assertEqual(result, LogRecordExportResult.FAILURE)

    def test_export_non_retryable_failure(self):
        exporter = OTLPLogExporter()
        with patch.object(exporter, "_export", return_value=_404()):
            result = exporter.export([])
        self.assertEqual(result, LogRecordExportResult.FAILURE)
        exporter.shutdown()

    def test_export_retry_then_deadline_exceeded(self):
        exporter = OTLPLogExporter(timeout=0.01)
        with patch.object(exporter, "_export", return_value=_503()):
            with patch(_UNIFORM, return_value=100.0):
                result = exporter.export([])
        self.assertEqual(result, LogRecordExportResult.FAILURE)
        exporter.shutdown()

    def test_export_max_retries_exhausted(self):
        exporter = OTLPLogExporter(timeout=100)
        with patch.object(exporter, "_export", return_value=_503()):
            with patch(_UNIFORM, return_value=0.0001):
                with patch.object(exporter._shutdown_is_occuring, "wait", return_value=False):
                    result = exporter.export([])
        self.assertEqual(result, LogRecordExportResult.FAILURE)
        exporter.shutdown()

    def test_shutdown_interrupts_retry(self):
        exporter = OTLPLogExporter(timeout=100)
        with patch.object(exporter, "_export", return_value=_503()):
            with patch(_UNIFORM, return_value=0.0001):
                with patch.object(exporter._shutdown_is_occuring, "wait", return_value=True):
                    result = exporter.export([])
        self.assertEqual(result, LogRecordExportResult.FAILURE)
        exporter.shutdown()

    def test_connection_error_is_retryable(self):
        exporter = OTLPLogExporter(timeout=0.01)
        with patch.object(exporter, "_export", side_effect=URLError("refused")):
            with patch(_UNIFORM, return_value=100.0):
                result = exporter.export([])
        self.assertEqual(result, LogRecordExportResult.FAILURE)
        exporter.shutdown()

    def _export_with_each_attempt_raising(self, error):
        exporter = OTLPLogExporter(timeout=100)
        with patch.object(exporter, "_export", side_effect=error) as export:
            with patch(_UNIFORM, return_value=0.0001):
                with patch.object(exporter._shutdown_is_occuring, "wait", return_value=False):
                    result = exporter.export([])
        exporter.shutdown()
        return result, export.call_count

    def test_read_timeout_returns_failure_instead_of_escaping_export(self):
        exporter = OTLPLogExporter(timeout=0.01)
        with patch.object(exporter, "_export", side_effect=TimeoutError("timed out")):
            with patch(_UNIFORM, return_value=100.0):
                result = exporter.export([])
        self.assertEqual(result, LogRecordExportResult.FAILURE)
        exporter.shutdown()

    def test_remote_disconnected_is_retried_until_the_budget_is_spent(self):
        result, attempts = self._export_with_each_attempt_raising(
            RemoteDisconnected("Remote end closed connection without response")
        )
        self.assertEqual(result, LogRecordExportResult.FAILURE)
        self.assertEqual(attempts, _MAX_RETRYS)

    def test_connection_reset_is_retried_until_the_budget_is_spent(self):
        result, attempts = self._export_with_each_attempt_raising(
            ConnectionResetError(104, "Connection reset by peer")
        )
        self.assertEqual(result, LogRecordExportResult.FAILURE)
        self.assertEqual(attempts, _MAX_RETRYS)

    def test_bad_status_line_is_retried_until_the_budget_is_spent(self):
        result, attempts = self._export_with_each_attempt_raising(
            BadStatusLine("not an http response")
        )
        self.assertEqual(result, LogRecordExportResult.FAILURE)
        self.assertEqual(attempts, _MAX_RETRYS)

    def test_malformed_endpoint_is_not_retried(self):
        result, attempts = self._export_with_each_attempt_raising(
            InvalidURL("nonnumeric port: 'abc'")
        )
        self.assertEqual(result, LogRecordExportResult.FAILURE)
        self.assertEqual(attempts, 1)

    def test_a_collector_closing_after_the_body_is_retried_over_a_real_socket(self):
        server, served = _server_that_closes_after_reading_the_request()
        self.addCleanup(server.close)
        endpoint = f"http://127.0.0.1:{server.getsockname()[1]}/v1/logs"
        exporter = OTLPLogExporter(endpoint=endpoint, timeout=100)
        with patch.dict(environ, {"no_proxy": "*"}):
            with patch(_UNIFORM, return_value=0.0001):
                with patch.object(
                    exporter._shutdown_is_occuring, "wait", return_value=False
                ):
                    result = exporter.export([])
        self.assertEqual(result, LogRecordExportResult.FAILURE)
        self.assertEqual(len(served), _MAX_RETRYS)
        exporter.shutdown()

    def test_a_backoff_that_overshoots_never_hands_export_a_negative_timeout(self):
        exporter = OTLPLogExporter(timeout=0.5)
        budgets = []

        def record_the_budget_and_fail(serialized_data, timeout_sec=None):
            budgets.append(timeout_sec)
            raise URLError("refused")

        def wait_longer_than_asked(seconds):
            sleep(seconds + 0.4)
            return False

        with patch.object(exporter, "_export", side_effect=record_the_budget_and_fail):
            with patch(_UNIFORM, return_value=0.25):
                with patch.object(
                    exporter._shutdown_is_occuring, "wait", side_effect=wait_longer_than_asked
                ):
                    result = exporter.export([])
        self.assertEqual(result, LogRecordExportResult.FAILURE)
        self.assertGreater(len(budgets), 1)
        self.assertTrue(all(budget >= 0 for budget in budgets))
        exporter.shutdown()

    # ── shutdown ──────────────────────────────────────────────────────────────

    def test_shutdown_sets_flag(self):
        exporter = OTLPLogExporter()
        self.assertFalse(exporter._shutdown)
        exporter.shutdown()
        self.assertTrue(exporter._shutdown)

    def test_shutdown_twice_logs_warning(self):
        exporter = OTLPLogExporter()
        exporter.shutdown()
        with self.assertLogs(level="WARNING") as cm:
            exporter.shutdown()
        self.assertTrue(any("already shutdown" in msg for msg in cm.output))

    def test_force_flush_returns_true(self):
        exporter = OTLPLogExporter()
        self.assertTrue(exporter.force_flush())
        exporter.shutdown()


class TestAppendLogsPath(unittest.TestCase):
    def test_with_trailing_slash(self):
        self.assertEqual(
            _append_logs_path("http://localhost:4318/"),
            "http://localhost:4318/v1/logs",
        )

    def test_without_trailing_slash(self):
        self.assertEqual(
            _append_logs_path("http://localhost:4318"),
            "http://localhost:4318/v1/logs",
        )
