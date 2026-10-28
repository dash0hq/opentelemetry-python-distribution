// Copyright Dash0 Inc.
// SPDX-License-Identifier: Apache-2.0

// Package harness runs one instrumentation case and hands the test what the
// case exported.
//
// A case is a directory under cases/ holding an app.py that exercises exactly
// one instrumented library and then exits, plus a requirements.txt naming the
// library to install. The harness builds that app into an image from this
// checkout, runs it under opentelemetry-instrument against an OTLP sink, and
// waits for the signals to arrive. Everything a test asserts is therefore
// observed at the sink, so a case cannot pass unless the distribution really
// emitted it.
//
// The sink and its query API are upstream's, imported rather than copied. The
// container plumbing is local because upstream's RunPackageTest derives the
// Docker build context from the nearest go.mod, which here would be this
// directory rather than the repository root, and the image has to install the
// workspace packages from the checkout.
package harness

import (
	"context"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/open-telemetry/opentelemetry-packaging/testutil/otelsink"
	"github.com/stretchr/testify/require"
	"github.com/testcontainers/testcontainers-go"
	"github.com/testcontainers/testcontainers-go/wait"
)

// ExportTimeout bounds how long to wait for a signal to reach the sink after
// the case has exited. A clean interpreter exit flushes the batch processors,
// so this covers transport rather than a flush interval.
const ExportTimeout = 60 * time.Second

// StartupTimeout bounds how long the container may take to report ready. The
// image build is not counted against it.
const StartupTimeout = 2 * time.Minute

// RunTimeout bounds how long the case may take to exit once it is running.
const RunTimeout = 5 * time.Minute

// ServiceName is the service name every case reports, set explicitly so the
// distribution's own fallback detection is not what the assertions depend on.
const ServiceName = "instrumentation-case"

// PythonVersion is the interpreter the cases run on.
const PythonVersion = "3.13"

// readyMarker is the line run_case.py writes before it waits for the sink, and
// it has to stay equal to READY_MARKER there.
//
// testcontainers only builds the reverse tunnel that carries the sink to the
// container once the container reports ready, so a case that exported at
// startup would export into a tunnel that does not exist yet. Readiness here
// is the case announcing it has not started exporting, and run_case.py then
// blocks until the tunnel answers.
const readyMarker = "instrumentation-case-runner-ready"

// Run builds the named case from this checkout, runs it to completion, and
// returns the sink its telemetry was exported to.
//
// The case is expected to exit zero on its own. A non-zero exit fails the test
// and prints the container output, which is where an instrumentation that
// raised on import says so.
func Run(t *testing.T, ctx context.Context, name string) *otelsink.Sink {
	t.Helper()

	sink := otelsink.Start(t)
	env := sink.Env()
	env["OTEL_SERVICE_NAME"] = ServiceName
	env["DASH0_OTEL_COLLECTOR_BASE_URL"] = env["OTEL_EXPORTER_OTLP_ENDPOINT"]
	env["OTEL_METRICS_EXPORTER"] = "none"

	pythonVersion := PythonVersion
	caseName := name

	req := testcontainers.ContainerRequest{
		FromDockerfile: testcontainers.FromDockerfile{
			Context:    repoRoot(t),
			Dockerfile: filepath.Join("tests", "e2e-instrumentations", "Dockerfile"),
			BuildArgs: map[string]*string{
				"case":           &caseName,
				"python_version": &pythonVersion,
			},
			KeepImage:     true,
			PrintBuildLog: testing.Verbose(),
		},
		Env:             env,
		HostAccessPorts: sink.HostAccessPorts(),
		WaitingFor:      wait.ForLog(readyMarker).WithStartupTimeout(StartupTimeout),
	}

	container, err := testcontainers.GenericContainer(ctx, testcontainers.GenericContainerRequest{
		ContainerRequest: req,
		Started:          true,
	})
	require.NoError(t, err, "could not build or start the %q case", name)
	t.Cleanup(func() { _ = container.Terminate(context.Background()) })

	require.NoError(t,
		wait.ForExit().WithExitTimeout(RunTimeout).WaitUntilReady(ctx, container),
		"the %q case did not exit within %s", name, RunTimeout)

	output := containerOutput(t, ctx, container)
	state, err := container.State(ctx)
	require.NoError(t, err)
	require.Equal(t, 0, state.ExitCode,
		"the %q case exited %d.\n\nOutput:\n%s", name, state.ExitCode, output)

	t.Cleanup(func() {
		if t.Failed() {
			t.Logf("output of the %q case:\n%s", name, output)
		}
	})

	return sink
}

// repoRoot is the directory the Docker build context has to be, found by
// walking up from the test's working directory until the workspace root is
// recognisable.
//
// It cannot be the nearest go.mod, which is this module, because the image
// installs the distribution from packages/ and so needs the whole checkout.
func repoRoot(t *testing.T) string {
	t.Helper()

	dir, err := os.Getwd()
	require.NoError(t, err)
	for {
		_, pyprojectErr := os.Stat(filepath.Join(dir, "pyproject.toml"))
		_, packagesErr := os.Stat(filepath.Join(dir, "packages"))
		if pyprojectErr == nil && packagesErr == nil {
			return dir
		}
		parent := filepath.Dir(dir)
		require.NotEqual(t, dir, parent,
			"no directory above %s holds both pyproject.toml and packages/", dir)
		dir = parent
	}
}

// containerOutput is everything the case wrote to stdout and stderr.
func containerOutput(t *testing.T, ctx context.Context, container testcontainers.Container) string {
	t.Helper()

	logs, err := container.Logs(ctx)
	if err != nil {
		return fmt.Sprintf("(could not read the container output: %v)", err)
	}
	defer logs.Close()

	content, err := io.ReadAll(logs)
	if err != nil {
		return fmt.Sprintf("(could not read the container output: %v)", err)
	}
	return string(content)
}
