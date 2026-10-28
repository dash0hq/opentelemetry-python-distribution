// Copyright Dash0 Inc.
// SPDX-License-Identifier: Apache-2.0

// Package instrumentations_test pins the shape of the telemetry the
// instrumentations this distribution ships actually emit.
//
// The unit tests in packages/dash0-opentelemetry check that the shipped set
// matches upstream and that the pins resolve. Neither says anything about what
// an instrumented library produces, so an upstream release that renames a span
// or drops an attribute passes everything this repository runs today. These
// tests run a real application per instrumentation and assert on the spans
// and log records that reach an OTLP sink. Metrics are not covered: the
// harness sets OTEL_METRICS_EXPORTER to none, so nothing emits them.
//
// One case per distinct telemetry shape is covered here rather than one per
// shipped package: a web framework producing a server span, an HTTP client
// producing a client span, a DB-API driver producing a client span with db
// attributes, and the log pipeline. Adding another instrumentation is a
// cases/<name>/app.py, a cases/<name>/requirements.txt, and a function here.
package instrumentations_test

import (
	"context"
	"testing"

	"github.com/open-telemetry/opentelemetry-packaging/testutil/otelsink"
	"github.com/stretchr/testify/assert"
	logspb "go.opentelemetry.io/proto/otlp/logs/v1"
	tracepb "go.opentelemetry.io/proto/otlp/trace/v1"

	"github.com/dash0hq/opentelemetry-python-distribution/tests/e2e-instrumentations/harness"
)

// TestFlask asserts the server span a request through an instrumented Flask
// application produces.
//
// The span name is the route template rather than the request target, which is
// what keeps the name bounded when the path carries an identifier.
func TestFlask(t *testing.T) {
	t.Parallel()
	ctx := context.Background()

	sink := harness.Run(t, ctx, "flask")

	traces := sink.WaitForTraces(t, harness.ExportTimeout, func(tr *otelsink.Traces) bool {
		return tr.WithKind(tracepb.Span_SPAN_KIND_SERVER).Len() > 0
	})
	server := traces.WithKind(tracepb.Span_SPAN_KIND_SERVER)

	assert.Equal(t, []string{"GET /items/<int:item_id>"}, server.Names(),
		"the server span is not named after the route template")
	assert.Positive(t, server.WithSpanAttributeValue("http.method", "GET").Len(),
		"the server span carries no http.method")
	assert.Positive(t, server.WithSpanAttributeValue("http.route", "/items/<int:item_id>").Len(),
		"the server span carries no http.route")
	assert.Positive(t, server.WithSpanAttributeValue("http.status_code", "200").Len(),
		"the server span carries no http.status_code")
	assertServiceName(t, sink)
}

// TestRequests asserts the client span an outbound call through an
// instrumented requests session produces.
func TestRequests(t *testing.T) {
	t.Parallel()
	ctx := context.Background()

	sink := harness.Run(t, ctx, "requests")

	traces := sink.WaitForTraces(t, harness.ExportTimeout, func(tr *otelsink.Traces) bool {
		return tr.WithKind(tracepb.Span_SPAN_KIND_CLIENT).Len() > 0
	})
	client := traces.WithKind(tracepb.Span_SPAN_KIND_CLIENT)

	assert.Equal(t, []string{"GET"}, client.Names(),
		"the client span is not named after the method")
	assert.Positive(t, client.WithSpanAttributeValue("http.method", "GET").Len(),
		"the client span carries no http.method")
	assert.Positive(t, client.WithSpanAttribute("http.url").Len(),
		"the client span carries no http.url")
	assert.Positive(t, client.WithSpanAttributeValue("http.status_code", "200").Len(),
		"the client span carries no http.status_code")
	assertServiceName(t, sink)
}

// TestSQLite3 asserts the client spans statements through an instrumented
// DB-API connection produce.
//
// sqlite3 is wrapped by the same opentelemetry-instrumentation-dbapi machinery
// every other driver in the distribution uses, so the attributes here are the
// shape of that whole family.
func TestSQLite3(t *testing.T) {
	t.Parallel()
	ctx := context.Background()

	sink := harness.Run(t, ctx, "sqlite3")

	traces := sink.WaitForTraces(t, harness.ExportTimeout, func(tr *otelsink.Traces) bool {
		return tr.WithKind(tracepb.Span_SPAN_KIND_CLIENT).Len() >= 3
	})
	client := traces.WithKind(tracepb.Span_SPAN_KIND_CLIENT)

	assert.ElementsMatch(t, []string{"CREATE", "INSERT", "SELECT"}, client.Names(),
		"the statement spans are not named after the operation")
	assert.Equal(t, 3, client.WithSpanAttributeValue("db.system", "sqlite").Len(),
		"not every statement span carries db.system=sqlite")
	assert.Equal(t, 3, client.WithSpanAttribute("db.statement").Len(),
		"not every statement span carries db.statement")
	assertServiceName(t, sink)
}

// TestLogging asserts that a record logged through the standard library
// reaches the sink, and that it carries the context of the span it was emitted
// inside.
//
// The application attaches no OpenTelemetry handler of its own, so a record
// arriving at all is what proves the distribution attached one.
func TestLogging(t *testing.T) {
	t.Parallel()
	ctx := context.Background()

	sink := harness.Run(t, ctx, "logging")

	logs := sink.WaitForLogs(t, harness.ExportTimeout, func(l *otelsink.Logs) bool {
		return l.WithBodyContaining("handled request").Len() > 0
	})
	handled := logs.WithBodyContaining("handled request")

	assert.Equal(t, []string{"handled request for item 7"}, handled.Bodies(),
		"the log record body is not the formatted message")
	assert.Positive(t, handled.WithSeverityAtLeast(logspb.SeverityNumber_SEVERITY_NUMBER_INFO).Len(),
		"the log record is below INFO severity")

	traces := sink.WaitForTraces(t, harness.ExportTimeout, func(tr *otelsink.Traces) bool {
		return tr.WithName("handle-request").Len() > 0
	})
	spans := traces.WithName("handle-request").Spans()
	assert.Len(t, spans, 1, "the application's span did not reach the sink")

	for _, record := range handled.Records() {
		assert.Equal(t, spans[0].Span.GetTraceId(), record.Record.GetTraceId(),
			"the log record does not carry the trace id of the span it was emitted inside")
	}
}

// assertServiceName checks the resource attribute every case sets explicitly,
// which is what shows the spans came from the application under test rather
// than from anything else sharing the sink.
func assertServiceName(t *testing.T, sink *otelsink.Sink) {
	t.Helper()

	traces := sink.Traces(t)
	assert.Positive(t, traces.WithResourceAttribute("service.name", harness.ServiceName).Len(),
		"no span carries service.name=%s", harness.ServiceName)
}
