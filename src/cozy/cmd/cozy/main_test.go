package main

import (
	"bytes"
	"encoding/json"
	"net"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"cozy/internal/service"
)

func TestRunHelp(t *testing.T) {
	var stdout, stderr bytes.Buffer
	if code := run([]string{"--help"}, &stdout, &stderr); code != 0 {
		t.Fatalf("help exit code = %d; stderr = %q", code, stderr.String())
	}
	if !strings.Contains(stdout.String(), "cozy <up|down|status|logs|open|check|refresh|restart>") {
		t.Fatalf("help does not describe the available commands: %q", stdout.String())
	}
	if !strings.Contains(stdout.String(), "cozy refresh") || !strings.Contains(stdout.String(), "cozy restart [site]") {
		t.Fatalf("help does not describe authenticated live operations: %q", stdout.String())
	}
	if strings.Contains(stdout.String(), "__agtask_dashboard") {
		t.Fatalf("help exposes the internal dashboard launcher: %q", stdout.String())
	}
}

func TestParseOptionsUsesCozyConfigEnvironment(t *testing.T) {
	configPath := filepath.Join(t.TempDir(), "devtools", "config", "cozy", "config.yaml")
	t.Setenv("COZY_CONFIG", configPath)
	var stderr bytes.Buffer
	opts, err := parseOptions("check", []string{"--state-dir", t.TempDir()}, &stderr)
	if err != nil {
		t.Fatalf("parse environment-backed configuration: %v", err)
	}
	if opts.configPath != configPath {
		t.Fatalf("configuration path = %q, want COZY_CONFIG %q", opts.configPath, configPath)
	}
}

func TestParseOptionsFallsBackWhenCozyConfigIsEmpty(t *testing.T) {
	t.Setenv("COZY_CONFIG", "")
	var stderr bytes.Buffer
	opts, err := parseOptions("check", []string{"--state-dir", t.TempDir()}, &stderr)
	if err != nil {
		t.Fatalf("parse fallback configuration: %v", err)
	}
	if opts.configPath != defaultConfig {
		t.Fatalf("configuration path = %q, want fallback %q", opts.configPath, defaultConfig)
	}
}

func TestParseOptionsExplicitConfigOverridesEnvironment(t *testing.T) {
	directory := t.TempDir()
	t.Setenv("COZY_CONFIG", filepath.Join(directory, "environment.yaml"))
	explicitConfig := filepath.Join(directory, "explicit.yaml")
	var stderr bytes.Buffer
	opts, err := parseOptions("check", []string{"--config", explicitConfig, "--state-dir", directory}, &stderr)
	if err != nil {
		t.Fatalf("parse explicit configuration: %v", err)
	}
	if opts.configPath != explicitConfig {
		t.Fatalf("configuration path = %q, want explicit --config %q", opts.configPath, explicitConfig)
	}
}

func TestParseOptionsRestartAcceptsAllSites(t *testing.T) {
	var stderr bytes.Buffer
	opts, err := parseOptions("restart", []string{"--state-dir", t.TempDir()}, &stderr)
	if err != nil {
		t.Fatalf("parse restart for all sites: %v", err)
	}
	if opts.site != "" {
		t.Fatalf("all-sites restart selected %q", opts.site)
	}
}

func TestParseOptionsRestartAcceptsOneSite(t *testing.T) {
	var stderr bytes.Buffer
	opts, err := parseOptions("restart", []string{"--state-dir", t.TempDir(), "fishy.localhost"}, &stderr)
	if err != nil {
		t.Fatalf("parse single-site restart: %v", err)
	}
	if opts.site != "fishy.localhost" {
		t.Fatalf("restart site = %q, want fishy.localhost", opts.site)
	}
}

func TestParseOptionsRestartRejectsMultipleSites(t *testing.T) {
	var stderr bytes.Buffer
	_, err := parseOptions("restart", []string{"--state-dir", t.TempDir(), "fishy.localhost", "other.localhost"}, &stderr)
	if err == nil || !strings.Contains(err.Error(), "at most one site") {
		t.Fatalf("multiple-site restart error = %v; want an actionable argument error", err)
	}
}

func TestParseOptionsRefreshRejectsSite(t *testing.T) {
	var stderr bytes.Buffer
	_, err := parseOptions("refresh", []string{"--state-dir", t.TempDir(), "fishy.localhost"}, &stderr)
	if err == nil || !strings.Contains(err.Error(), "unexpected argument") {
		t.Fatalf("refresh site argument error = %v; want an actionable argument error", err)
	}
}

func TestRunControlReportsMissingRuntimeState(t *testing.T) {
	for _, action := range []string{"refresh", "restart"} {
		t.Run(action, func(t *testing.T) {
			var stdout, stderr bytes.Buffer
			code := run([]string{action, "--state-dir", filepath.Join(t.TempDir(), "runtime")}, &stdout, &stderr)
			if code != 1 {
				t.Fatalf("%s exit code = %d, want 1; stderr = %q", action, code, stderr.String())
			}
			if !strings.Contains(stderr.String(), "not running") || !strings.Contains(stderr.String(), "cozy up") {
				t.Fatalf("%s does not explain how to start Cozy: %q", action, stderr.String())
			}
		})
	}
}

func TestRunControlRejectsForgedRuntimeState(t *testing.T) {
	for _, action := range []string{"refresh", "restart"} {
		t.Run(action, func(t *testing.T) {
			directory := filepath.Join(t.TempDir(), "runtime")
			writeForgedState(t, directory, service.State{PID: os.Getpid(), Addr: "127.0.0.1:0"})
			var stdout, stderr bytes.Buffer
			code := run([]string{action, "--state-dir", directory}, &stdout, &stderr)
			if code != 1 {
				t.Fatalf("%s exit code = %d, want 1; stderr = %q", action, code, stderr.String())
			}
			if !strings.Contains(stderr.String(), "not running") || !strings.Contains(stderr.String(), "could not be verified") {
				t.Fatalf("%s trusted unverified supervisor state: %q", action, stderr.String())
			}
		})
	}
}

func TestRunAgtaskDashboardRejectsMissingPort(t *testing.T) {
	t.Setenv("PORT", "")
	var stdout, stderr bytes.Buffer
	if code := run([]string{"__agtask_dashboard"}, &stdout, &stderr); code != 2 {
		t.Fatalf("dashboard exit code = %d, want 2; stderr = %q", code, stderr.String())
	}
	if !strings.Contains(stderr.String(), "PORT is not set") || !strings.Contains(stderr.String(), "Cozy must assign a backend port") {
		t.Fatalf("missing port has no actionable error: %q", stderr.String())
	}
	if stdout.Len() != 0 {
		t.Fatalf("invalid dashboard launcher wrote to stdout: %q", stdout.String())
	}
}

func TestRunAgtaskDashboardRejectsInvalidPort(t *testing.T) {
	for _, value := range []string{"0", "65536", "-1", "+1", " 8080", "8080 ", "1.5", "not-a-port"} {
		t.Run(value, func(t *testing.T) {
			t.Setenv("PORT", value)
			var stdout, stderr bytes.Buffer
			if code := run([]string{"__agtask_dashboard"}, &stdout, &stderr); code != 2 {
				t.Fatalf("dashboard exit code = %d, want 2; stderr = %q", code, stderr.String())
			}
			if !strings.Contains(stderr.String(), "PORT must be a decimal port from 1 through 65535") {
				t.Fatalf("invalid port has no actionable error: %q", stderr.String())
			}
			if stdout.Len() != 0 {
				t.Fatalf("invalid dashboard launcher wrote to stdout: %q", stdout.String())
			}
		})
	}
}

func TestRunAgtaskDashboardRejectsUnexpectedArguments(t *testing.T) {
	t.Setenv("PORT", "8080")
	var stdout, stderr bytes.Buffer
	if code := run([]string{"__agtask_dashboard", "unexpected"}, &stdout, &stderr); code != 2 {
		t.Fatalf("dashboard exit code = %d, want 2; stderr = %q", code, stderr.String())
	}
	if !strings.Contains(stderr.String(), `unexpected argument "unexpected"`) {
		t.Fatalf("unexpected argument has no actionable error: %q", stderr.String())
	}
	if stdout.Len() != 0 {
		t.Fatalf("invalid dashboard launcher wrote to stdout: %q", stdout.String())
	}
}

func TestRunCheckReportsMissingConfiguration(t *testing.T) {
	var stdout, stderr bytes.Buffer
	directory := t.TempDir()
	code := run([]string{"check", "--config", filepath.Join(directory, "missing.yaml"), "--listen", "127.0.0.1:0", "--state-dir", directory}, &stdout, &stderr)
	if code != 1 {
		t.Fatalf("check exit code = %d, want 1; stderr = %q", code, stderr.String())
	}
	if !strings.Contains(stderr.String(), "load configuration") {
		t.Fatalf("missing configuration has no actionable error: %q", stderr.String())
	}
}

func TestRunStatusWhenNotRunning(t *testing.T) {
	var stdout, stderr bytes.Buffer
	code := run([]string{"status", "--state-dir", filepath.Join(t.TempDir(), "runtime")}, &stdout, &stderr)
	if code != 0 {
		t.Fatalf("status exit code = %d; stderr = %q", code, stderr.String())
	}
	if !strings.Contains(stdout.String(), "not running") {
		t.Fatalf("status does not report the stopped state: %q", stdout.String())
	}
}

func writeForgedState(t *testing.T, directory string, state service.State) {
	t.Helper()
	if err := os.MkdirAll(directory, 0o700); err != nil {
		t.Fatalf("create forged state directory: %v", err)
	}
	contents, err := json.Marshal(state)
	if err != nil {
		t.Fatalf("encode forged runtime state: %v", err)
	}
	if err := os.WriteFile(filepath.Join(directory, "state.json"), contents, 0o600); err != nil {
		t.Fatalf("write forged runtime state: %v", err)
	}
}

func TestRunDownDoesNotSignalUnverifiedCurrentProcess(t *testing.T) {
	directory := filepath.Join(t.TempDir(), "runtime")
	writeForgedState(t, directory, service.State{PID: os.Getpid(), Addr: "127.0.0.1:0"})
	var stdout, stderr bytes.Buffer
	code := run([]string{"down", "--state-dir", directory}, &stdout, &stderr)
	if code != 0 {
		t.Fatalf("down exit code = %d; stderr = %q", code, stderr.String())
	}
	if !strings.Contains(stdout.String(), "not running") || !strings.Contains(stdout.String(), "could not be verified") {
		t.Fatalf("down did not report unverified supervisor state: %q", stdout.String())
	}
}

func TestRunStatusRejectsUnverifiedCurrentProcess(t *testing.T) {
	directory := filepath.Join(t.TempDir(), "runtime")
	writeForgedState(t, directory, service.State{PID: os.Getpid(), Addr: "127.0.0.1:0"})
	var stdout, stderr bytes.Buffer
	code := run([]string{"status", "--state-dir", directory}, &stdout, &stderr)
	if code != 0 {
		t.Fatalf("status exit code = %d; stderr = %q", code, stderr.String())
	}
	if !strings.Contains(stdout.String(), "not running") || !strings.Contains(stdout.String(), "could not be verified") {
		t.Fatalf("status trusted unverified supervisor state: %q", stdout.String())
	}
}

func TestRunLogsRequiresOneExactSite(t *testing.T) {
	var stdout, stderr bytes.Buffer
	code := run([]string{"logs", "--state-dir", t.TempDir()}, &stdout, &stderr)
	if code != 2 {
		t.Fatalf("logs exit code = %d, want 2; stderr = %q", code, stderr.String())
	}
	if !strings.Contains(stderr.String(), "exactly one site") {
		t.Fatalf("logs does not explain the required site: %q", stderr.String())
	}
}

func TestRunLogsReportsMissingRuntimeState(t *testing.T) {
	var stdout, stderr bytes.Buffer
	code := run([]string{"logs", "--state-dir", filepath.Join(t.TempDir(), "runtime"), "fishy.localhost"}, &stdout, &stderr)
	if code != 1 {
		t.Fatalf("logs exit code = %d, want 1; stderr = %q", code, stderr.String())
	}
	if !strings.Contains(stderr.String(), "cozy up") {
		t.Fatalf("logs does not explain how to start Cozy: %q", stderr.String())
	}
}

func TestFindSiteRequiresExactConfiguredName(t *testing.T) {
	state := service.State{Sites: []service.SiteState{{Name: "fishy.localhost", URL: "http://fishy.localhost"}}}
	site, err := findSite(state, "fishy.localhost")
	if err != nil {
		t.Fatalf("find configured site: %v", err)
	}
	if site.URL != "http://fishy.localhost" {
		t.Fatalf("site URL = %q", site.URL)
	}
	if _, err := findSite(state, "fishy"); err == nil {
		t.Fatal("an abbreviated name unexpectedly matched the configured site")
	}
}

func TestCheckListenerReportsConflict(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("create occupied listener: %v", err)
	}
	t.Cleanup(func() { _ = listener.Close() })
	if err := checkListener(listener.Addr().String()); err == nil || !strings.Contains(err.Error(), "already in use") {
		t.Fatalf("listener conflict = %v; want an actionable in-use error", err)
	}
}

func TestCheckListenerRejectsWildcardAddress(t *testing.T) {
	err := checkListener("0.0.0.0:0")
	if err == nil || !strings.Contains(err.Error(), "must use a loopback address") {
		t.Fatalf("wildcard listener error = %v; want an actionable loopback-only error", err)
	}
}

func TestCheckListenerReleasesAvailableAddress(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("allocate loopback address: %v", err)
	}
	address := listener.Addr().String()
	if err := listener.Close(); err != nil {
		t.Fatalf("release allocated address: %v", err)
	}
	if err := checkListener(address); err != nil {
		t.Fatalf("check available listener: %v", err)
	}
	confirmation, err := net.Listen("tcp", address)
	if err != nil {
		t.Fatalf("checked listener was not released: %v", err)
	}
	if err := confirmation.Close(); err != nil {
		t.Fatalf("close confirmation listener: %v", err)
	}
}

func TestRunCheckValidConfiguration(t *testing.T) {
	directory := t.TempDir()
	path := filepath.Join(directory, "cozy.yaml")
	contents := "version: 1\nsites:\n  - name: fishy.localhost\n    url: http://fishy.localhost\n    run: fishy\n"
	if err := os.WriteFile(path, []byte(contents), 0o600); err != nil {
		t.Fatalf("write configuration: %v", err)
	}
	var stdout, stderr bytes.Buffer
	code := run([]string{"check", "--config", path, "--listen", "127.0.0.1:0", "--state-dir", filepath.Join(directory, "runtime")}, &stdout, &stderr)
	if code != 0 {
		t.Fatalf("check exit code = %d; stderr = %q", code, stderr.String())
	}
	if !strings.Contains(stdout.String(), "Configuration is valid") {
		t.Fatalf("check did not confirm the valid configuration: %q", stdout.String())
	}
}

func TestRunCheckDoesNotTrustForgedListenerOwnership(t *testing.T) {
	directory := t.TempDir()
	configPath := filepath.Join(directory, "cozy.yaml")
	contents := "version: 1\nsites:\n  - name: fishy.localhost\n    url: http://fishy.localhost\n    run: fishy\n"
	if err := os.WriteFile(configPath, []byte(contents), 0o600); err != nil {
		t.Fatalf("write configuration: %v", err)
	}
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("create occupied listener: %v", err)
	}
	t.Cleanup(func() { _ = listener.Close() })
	stateDir := filepath.Join(directory, "runtime")
	writeForgedState(t, stateDir, service.State{PID: os.Getpid(), Addr: listener.Addr().String()})
	var stdout, stderr bytes.Buffer
	code := run([]string{"check", "--config", configPath, "--listen", listener.Addr().String(), "--state-dir", stateDir}, &stdout, &stderr)
	if code != 1 {
		t.Fatalf("check exit code = %d, want 1; stdout = %q; stderr = %q", code, stdout.String(), stderr.String())
	}
	if !strings.Contains(stderr.String(), "already in use") {
		t.Fatalf("check trusted forged listener ownership: %q", stderr.String())
	}
}
