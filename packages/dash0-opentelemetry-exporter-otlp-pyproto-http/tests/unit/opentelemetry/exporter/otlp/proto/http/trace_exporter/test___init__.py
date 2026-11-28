# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# pylint: disable=protected-access

import unittest
from contextlib import contextmanager
from http.client import BadStatusLine, InvalidURL, RemoteDisconnected
from os import environ
from socket import AF_INET, SOCK_STREAM, SOL_SOCKET, SO_REUSEADDR, socket
from threading import Thread
from time import sleep
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import URLError

from opentelemetry.exporter.otlp.proto.http import Compression
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    DEFAULT_ENDPOINT,
    DEFAULT_TIMEOUT,
    DEFAULT_TRACES_EXPORT_PATH,
    OTLPSpanExporter,
    _MAX_RETRYS,
    _append_trace_path,
)
from opentelemetry.sdk.trace.export import SpanExportResult
from opentelemetry.semconv.attributes.http_attributes import (
    HTTP_RESPONSE_STATUS_CODE,
)

_UNIFORM = "opentelemetry.exporter.otlp.proto.http.trace_exporter.uniform"


def _exporter_metrics_that_keep_every_result(results):
    @contextmanager
    def export_operation(num_items):
        result = SimpleNamespace(error=None, error_attrs=None)
        results.append(result)
        yield result

    return SimpleNamespace(export_operation=export_operation)


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


class TestOTLPSpanExporter(unittest.TestCase):

    # ── constructor ───────────────────────────────────────────────────────────

    def test_constructor_defaults(self):
        exporter = OTLPSpanExporter()
        self.assertEqual(
            exporter._endpoint,
            DEFAULT_ENDPOINT + DEFAULT_TRACES_EXPORT_PATH,
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
            exporter = OTLPSpanExporter()
        self.assertEqual(exporter._endpoint, "http://collector:4318/v1/traces")
        exporter.shutdown()

    def test_traces_endpoint_overrides_generic(self):
        with patch.dict("os.environ", {
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://generic:4318",
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "http://traces:4318/v1/traces",
        }):
            exporter = OTLPSpanExporter()
        self.assertEqual(exporter._endpoint, "http://traces:4318/v1/traces")
        exporter.shutdown()

    def test_constructor_arg_overrides_env(self):
        with patch.dict("os.environ", {
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "http://env:4318/v1/traces",
        }):
            exporter = OTLPSpanExporter(endpoint="http://arg:4318/v1/traces")
        self.assertEqual(exporter._endpoint, "http://arg:4318/v1/traces")
        exporter.shutdown()

    def test_timeout_generic_env_var(self):
        with patch.dict("os.environ", {"OTEL_EXPORTER_OTLP_TIMEOUT": "20"}):
            exporter = OTLPSpanExporter()
        self.assertEqual(exporter._timeout, 20.0)
        exporter.shutdown()

    def test_timeout_traces_env_var_overrides_generic(self):
        with patch.dict("os.environ", {
            "OTEL_EXPORTER_OTLP_TIMEOUT": "20",
            "OTEL_EXPORTER_OTLP_TRACES_TIMEOUT": "5",
        }):
            exporter = OTLPSpanExporter()
        self.assertEqual(exporter._timeout, 5.0)
        exporter.shutdown()

    def test_timeout_arg_overrides_env(self):
        with patch.dict("os.environ", {"OTEL_EXPORTER_OTLP_TRACES_TIMEOUT": "99"}):
            exporter = OTLPSpanExporter(timeout=3)
        self.assertEqual(exporter._timeout, 3)
        exporter.shutdown()

    def test_compression_env_var_gzip(self):
        with patch.dict("os.environ", {"OTEL_EXPORTER_OTLP_COMPRESSION": "gzip"}):
            exporter = OTLPSpanExporter()
        self.assertEqual(exporter._compression, Compression.Gzip)
        self.assertEqual(exporter._request_headers.get("Content-Encoding"), "gzip")
        exporter.shutdown()

    def test_compression_env_var_deflate(self):
        with patch.dict("os.environ", {"OTEL_EXPORTER_OTLP_COMPRESSION": "deflate"}):
            exporter = OTLPSpanExporter()
        self.assertEqual(exporter._compression, Compression.Deflate)
        self.assertEqual(exporter._request_headers.get("Content-Encoding"), "deflate")
        exporter.shutdown()

    def test_compression_traces_env_overrides_generic(self):
        with patch.dict("os.environ", {
            "OTEL_EXPORTER_OTLP_COMPRESSION": "gzip",
            "OTEL_EXPORTER_OTLP_TRACES_COMPRESSION": "deflate",
        }):
            exporter = OTLPSpanExporter()
        self.assertEqual(exporter._compression, Compression.Deflate)
        exporter.shutdown()

    def test_compression_arg_gzip(self):
        exporter = OTLPSpanExporter(compression=Compression.Gzip)
        self.assertEqual(exporter._compression, Compression.Gzip)
        self.assertEqual(exporter._request_headers.get("Content-Encoding"), "gzip")
        exporter.shutdown()

    def test_no_compression_header_for_none_compression(self):
        exporter = OTLPSpanExporter(compression=Compression.NoCompression)
        self.assertNotIn("Content-Encoding", exporter._request_headers)
        exporter.shutdown()

    # ── export ────────────────────────────────────────────────────────────────

    def test_export_success(self):
        exporter = OTLPSpanExporter()
        with patch.object(exporter, "_export", return_value=_ok()):
            result = exporter.export([])
        self.assertEqual(result, SpanExportResult.SUCCESS)
        exporter.shutdown()

    def test_export_after_shutdown_returns_failure(self):
        exporter = OTLPSpanExporter()
        exporter.shutdown()
        result = exporter.export([])
        self.assertEqual(result, SpanExportResult.FAILURE)

    def test_export_non_retryable_failure(self):
        exporter = OTLPSpanExporter()
        with patch.object(exporter, "_export", return_value=_404()):
            result = exporter.export([])
        self.assertEqual(result, SpanExportResult.FAILURE)
        exporter.shutdown()

    def test_export_retry_then_deadline_exceeded(self):
        # backoff(100) > remaining timeout(0.01) → exits on first retry
        exporter = OTLPSpanExporter(timeout=0.01)
        with patch.object(exporter, "_export", return_value=_503()):
            with patch(_UNIFORM, return_value=100.0):
                result = exporter.export([])
        self.assertEqual(result, SpanExportResult.FAILURE)
        exporter.shutdown()

    def test_export_max_retries_exhausted(self):
        exporter = OTLPSpanExporter(timeout=100)
        with patch.object(exporter, "_export", return_value=_503()):
            with patch(_UNIFORM, return_value=0.0001):
                with patch.object(exporter._shutdown_in_progress, "wait", return_value=False):
                    result = exporter.export([])
        self.assertEqual(result, SpanExportResult.FAILURE)
        exporter.shutdown()

    def test_shutdown_interrupts_retry(self):
        exporter = OTLPSpanExporter(timeout=100)
        results = []
        exporter._metrics = _exporter_metrics_that_keep_every_result(results)
        with patch.object(exporter, "_export", return_value=_503()):
            with patch(_UNIFORM, return_value=0.0001):
                with patch.object(exporter._shutdown_in_progress, "wait", return_value=True):
                    result = exporter.export([])
        self.assertEqual(result, SpanExportResult.FAILURE)
        self.assertEqual(results[0].error_attrs, {HTTP_RESPONSE_STATUS_CODE: 503})
        exporter.shutdown()

    def test_connection_error_is_retryable(self):
        # URLError from _export goes into the retry path; deadline kills it fast.
        exporter = OTLPSpanExporter(timeout=0.01)
        with patch.object(exporter, "_export", side_effect=URLError("refused")):
            with patch(_UNIFORM, return_value=100.0):
                result = exporter.export([])
        self.assertEqual(result, SpanExportResult.FAILURE)
        exporter.shutdown()

    def _export_with_each_attempt_raising(self, error):
        exporter = OTLPSpanExporter(timeout=100)
        with patch.object(exporter, "_export", side_effect=error) as export:
            with patch(_UNIFORM, return_value=0.0001):
                with patch.object(exporter._shutdown_in_progress, "wait", return_value=False):
                    result = exporter.export([])
        exporter.shutdown()
        return result, export.call_count

    def test_read_timeout_returns_failure_instead_of_escaping_export(self):
        exporter = OTLPSpanExporter(timeout=0.01)
        with patch.object(exporter, "_export", side_effect=TimeoutError("timed out")):
            with patch(_UNIFORM, return_value=100.0):
                result = exporter.export([])
        self.assertEqual(result, SpanExportResult.FAILURE)
        exporter.shutdown()

    def test_remote_disconnected_is_retried_until_the_budget_is_spent(self):
        result, attempts = self._export_with_each_attempt_raising(
            RemoteDisconnected("Remote end closed connection without response")
        )
        self.assertEqual(result, SpanExportResult.FAILURE)
        self.assertEqual(attempts, _MAX_RETRYS)

    def test_connection_reset_is_retried_until_the_budget_is_spent(self):
        result, attempts = self._export_with_each_attempt_raising(
            ConnectionResetError(104, "Connection reset by peer")
        )
        self.assertEqual(result, SpanExportResult.FAILURE)
        self.assertEqual(attempts, _MAX_RETRYS)

    def test_bad_status_line_is_retried_until_the_budget_is_spent(self):
        result, attempts = self._export_with_each_attempt_raising(
            BadStatusLine("not an http response")
        )
        self.assertEqual(result, SpanExportResult.FAILURE)
        self.assertEqual(attempts, _MAX_RETRYS)

    def test_malformed_endpoint_is_not_retried(self):
        result, attempts = self._export_with_each_attempt_raising(
            InvalidURL("nonnumeric port: 'abc'")
        )
        self.assertEqual(result, SpanExportResult.FAILURE)
        self.assertEqual(attempts, 1)

    def test_a_collector_closing_after_the_body_is_retried_over_a_real_socket(self):
        server, served = _server_that_closes_after_reading_the_request()
        self.addCleanup(server.close)
        endpoint = f"http://127.0.0.1:{server.getsockname()[1]}/v1/traces"
        exporter = OTLPSpanExporter(endpoint=endpoint, timeout=100)
        with patch.dict(environ, {"no_proxy": "*"}):
            with patch(_UNIFORM, return_value=0.0001):
                with patch.object(
                    exporter._shutdown_in_progress, "wait", return_value=False
                ):
                    result = exporter.export([])
        self.assertEqual(result, SpanExportResult.FAILURE)
        self.assertEqual(len(served), _MAX_RETRYS)
        exporter.shutdown()

    def test_a_backoff_that_overshoots_the_deadline_makes_no_further_attempt(self):
        exporter = OTLPSpanExporter(timeout=0.5)
        results = []
        exporter._metrics = _exporter_metrics_that_keep_every_result(results)
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
                    exporter._shutdown_in_progress, "wait", side_effect=wait_longer_than_asked
                ):
                    result = exporter.export([])
        self.assertEqual(result, SpanExportResult.FAILURE)
        self.assertEqual(len(budgets), 1)
        self.assertTrue(all(budget > 0 for budget in budgets))
        self.assertIsInstance(results[0].error, URLError)
        exporter.shutdown()

    def test_a_deadline_already_spent_records_a_timeout_without_an_attempt(self):
        exporter = OTLPSpanExporter(timeout=100)
        results = []
        exporter._metrics = _exporter_metrics_that_keep_every_result(results)
        exporter._timeout = 0

        with patch.object(exporter, "_export") as export:
            result = exporter.export([])
        self.assertEqual(result, SpanExportResult.FAILURE)
        self.assertEqual(export.call_count, 0)
        self.assertIsInstance(results[0].error, TimeoutError)
        self.assertIsNone(results[0].error_attrs)
        exporter.shutdown()

    # ── shutdown ──────────────────────────────────────────────────────────────

    def test_shutdown_sets_flag(self):
        exporter = OTLPSpanExporter()
        self.assertFalse(exporter._shutdown)
        exporter.shutdown()
        self.assertTrue(exporter._shutdown)

    def test_shutdown_twice_logs_warning(self):
        exporter = OTLPSpanExporter()
        exporter.shutdown()
        with self.assertLogs(level="WARNING") as cm:
            exporter.shutdown()
        self.assertTrue(any("already shutdown" in msg for msg in cm.output))

    def test_force_flush_returns_true(self):
        exporter = OTLPSpanExporter()
        self.assertTrue(exporter.force_flush())
        exporter.shutdown()


class TestAppendTracePath(unittest.TestCase):
    def test_with_trailing_slash(self):
        self.assertEqual(
            _append_trace_path("http://localhost:4318/"),
            "http://localhost:4318/v1/traces",
        )

    def test_without_trailing_slash(self):
        self.assertEqual(
            _append_trace_path("http://localhost:4318"),
            "http://localhost:4318/v1/traces",
        )
