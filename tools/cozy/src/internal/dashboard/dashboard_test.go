package dashboard

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"
)

const helperToken = "cozy-private-test-token"

func TestParseTarget(t *testing.T) {
	tests := []struct {
		name  string
		line  string
		valid bool
	}{
		{name: "loopback token", line: "http://127.0.0.1:34567/private-token/", valid: true},
		{name: "IPv6 loopback token", line: "http://[::1]:34567/private-token/", valid: true},
		{name: "hosted private site", line: "https://agtask-example.openai.chatgpt.site", valid: true},
		{name: "hosted private site root", line: "https://agtask-example.openai.chatgpt.site/", valid: true},
		{name: "untrusted hosted domain", line: "https://example.com/"},
		{name: "hosted site query", line: "https://agtask-example.openai.chatgpt.site/?token=secret"},
		{name: "hosted site nested path", line: "https://agtask-example.openai.chatgpt.site/private"},
		{name: "hosted site port", line: "https://agtask-example.openai.chatgpt.site:8443/"},
		{name: "missing token", line: "http://127.0.0.1:34567/"},
		{name: "nonloopback host", line: "http://example.com:34567/private-token/"},
		{name: "missing port", line: "http://127.0.0.1/private-token/"},
		{name: "invalid port", line: "http://127.0.0.1:99999/private-token/"},
		{name: "nested path", line: "http://127.0.0.1:34567/a/b/"},
		{name: "encoded slash", line: "http://127.0.0.1:34567/a%2Fb/"},
		{name: "wrong scheme", line: "https://127.0.0.1:34567/private-token/"},
		{name: "credentials", line: "http://user@127.0.0.1:34567/private-token/"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			got, err := parseTarget(test.line)
			if (err == nil) != test.valid {
				t.Fatalf("parseTarget(%q) = %v, %v; valid = %t", test.line, got, err, test.valid)
			}
		})
	}
}

func helperExecutable(t *testing.T, mode string) string {
	t.Helper()
	t.Setenv("COZY_DASHBOARD_TEST_HELPER", mode)
	path := filepath.Join(t.TempDir(), "agtask")
	contents := "#!/bin/sh\nexec " + strconv.Quote(os.Args[0]) + " -test.run=^TestDashboardHelperProcess$ -- \"$@\"\n"
	if err := os.WriteFile(path, []byte(contents), 0o700); err != nil {
		t.Fatalf("write hermetic dashboard helper: %v", err)
	}
	return path
}

func availablePort(t *testing.T) int {
	t.Helper()
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("reserve loopback port: %v", err)
	}
	port := listener.Addr().(*net.TCPAddr).Port
	if err := listener.Close(); err != nil {
		t.Fatalf("release loopback port: %v", err)
	}
	return port
}

func TestRunRoutesDashboardAndPreservesSecurity(t *testing.T) {
	executable := helperExecutable(t, "serve")
	port := availablePort(t)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	var stdout, stderr bytes.Buffer
	done := make(chan error, 1)
	go func() { done <- Run(ctx, port, executable, &stdout, &stderr) }()

	client := &http.Client{Timeout: time.Second}
	address := "http://127.0.0.1:" + strconv.Itoa(port)
	deadline := time.Now().Add(5 * time.Second)
	for {
		response, err := client.Get(address + "/")
		if err == nil {
			_ = response.Body.Close()
			if response.StatusCode == http.StatusOK {
				break
			}
		}
		select {
		case runErr := <-done:
			t.Fatalf("dashboard adapter exited before readiness: %v; stderr: %s", runErr, stderr.String())
		default:
		}
		if time.Now().After(deadline) {
			t.Fatalf("dashboard adapter did not become ready: %v; stderr: %s", err, stderr.String())
		}
		time.Sleep(15 * time.Millisecond)
	}

	for _, path := range []string{"/", "/app.css", "/app.js", "/task.js", "/api/dashboard?search=cozy", "/tasks/abc", "/api/tasks/abc"} {
		t.Run(path, func(t *testing.T) {
			response, err := client.Get(address + path)
			if err != nil {
				t.Fatalf("request public dashboard path: %v", err)
			}
			body, err := io.ReadAll(response.Body)
			_ = response.Body.Close()
			if err != nil {
				t.Fatalf("read dashboard response: %v", err)
			}
			if response.StatusCode != http.StatusOK {
				t.Fatalf("dashboard response = %d: %s", response.StatusCode, body)
			}
			if strings.Contains(string(body), helperToken) {
				t.Fatalf("dashboard response leaked the private token: %s", body)
			}
			if path == "/" && response.Header.Get("Content-Security-Policy") != "default-src 'self'" {
				t.Fatalf("dashboard CSP was not preserved: %q", response.Header.Get("Content-Security-Policy"))
			}
			if strings.Contains(path, "?") && !strings.Contains(string(body), "search=cozy") {
				t.Fatalf("dashboard query was not forwarded: %s", body)
			}
		})
	}

	for _, test := range []struct {
		name   string
		origin string
		status int
	}{
		{name: "same origin", origin: address, status: http.StatusOK},
		{name: "foreign origin", origin: "http://untrusted.invalid", status: http.StatusForbidden},
	} {
		t.Run(test.name, func(t *testing.T) {
			request, err := http.NewRequest(http.MethodPatch, address+"/api/tasks/abc/status", strings.NewReader("{}"))
			if err != nil {
				t.Fatalf("create dashboard update: %v", err)
			}
			request.Header.Set("Origin", test.origin)
			request.Header.Set("Content-Type", "application/json")
			response, err := client.Do(request)
			if err != nil {
				t.Fatalf("send dashboard update: %v", err)
			}
			_ = response.Body.Close()
			if response.StatusCode != test.status {
				t.Fatalf("dashboard update status = %d, want %d", response.StatusCode, test.status)
			}
		})
	}

	cancel()
	select {
	case err := <-done:
		if err != context.Canceled {
			t.Fatalf("dashboard cancellation = %v, want context canceled", err)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("dashboard child did not stop on cancellation")
	}
	if strings.Contains(stdout.String(), helperToken) || strings.Contains(stderr.String(), helperToken) {
		t.Fatal("dashboard diagnostics leaked the private token")
	}
}

func TestRunRedirectsHostedDashboardWithoutBypassingAuthentication(t *testing.T) {
	executable := helperExecutable(t, "hosted")
	port := availablePort(t)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	var stdout, stderr bytes.Buffer
	done := make(chan error, 1)
	go func() { done <- Run(ctx, port, executable, &stdout, &stderr) }()

	client := &http.Client{
		Timeout: time.Second,
		CheckRedirect: func(*http.Request, []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
	address := "http://127.0.0.1:" + strconv.Itoa(port)
	deadline := time.Now().Add(5 * time.Second)
	for {
		response, err := client.Get(address + "/")
		if err == nil {
			_ = response.Body.Close()
			if response.StatusCode == http.StatusTemporaryRedirect {
				break
			}
		}
		select {
		case runErr := <-done:
			t.Fatalf("hosted dashboard adapter exited before readiness: %v; stderr: %s", runErr, stderr.String())
		default:
		}
		if time.Now().After(deadline) {
			t.Fatalf("hosted dashboard adapter did not become ready: %v; stderr: %s", err, stderr.String())
		}
		time.Sleep(15 * time.Millisecond)
	}

	for _, path := range []string{"/", "/tasks/~example", "/?search=cozy"} {
		t.Run(path, func(t *testing.T) {
			response, err := client.Get(address + path)
			if err != nil {
				t.Fatalf("request hosted dashboard redirect: %v", err)
			}
			_ = response.Body.Close()
			if response.StatusCode != http.StatusTemporaryRedirect {
				t.Fatalf("hosted dashboard status = %d, want %d", response.StatusCode, http.StatusTemporaryRedirect)
			}
			if got, want := response.Header.Get("Location"), "https://agtask-example.openai.chatgpt.site"+path; got != want {
				t.Fatalf("hosted dashboard redirect = %q, want %q", got, want)
			}
		})
	}

	cancel()
	select {
	case err := <-done:
		if err != context.Canceled {
			t.Fatalf("hosted dashboard cancellation = %v, want context canceled", err)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("hosted dashboard adapter did not stop on cancellation")
	}
}

func TestRunReportsInvalidStartupURL(t *testing.T) {
	executable := helperExecutable(t, "invalid")
	var stdout, stderr bytes.Buffer
	err := Run(context.Background(), availablePort(t), executable, &stdout, &stderr)
	if err == nil || !strings.Contains(err.Error(), "loopback") {
		t.Fatalf("invalid dashboard startup = %v, want a loopback diagnostic", err)
	}
}

func TestRunReportsMissingExecutable(t *testing.T) {
	err := Run(context.Background(), availablePort(t), filepath.Join(t.TempDir(), "missing"), io.Discard, io.Discard)
	if err == nil || !strings.Contains(err.Error(), "start agtask dashboard") {
		t.Fatalf("missing dashboard executable = %v", err)
	}
}

func TestRunReportsOccupiedManagedPort(t *testing.T) {
	executable := helperExecutable(t, "serve")
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("occupy loopback port: %v", err)
	}
	defer listener.Close()
	err = Run(context.Background(), listener.Addr().(*net.TCPAddr).Port, executable, io.Discard, io.Discard)
	if err == nil || !strings.Contains(err.Error(), "bind assigned dashboard loopback port") {
		t.Fatalf("occupied dashboard port = %v", err)
	}
}

func TestDashboardHelperProcess(t *testing.T) {
	mode := os.Getenv("COZY_DASHBOARD_TEST_HELPER")
	if mode == "" {
		return
	}
	if len(os.Args) < 2 || os.Args[len(os.Args)-2] != "dashboard" || os.Args[len(os.Args)-1] != "--no-open" {
		fmt.Fprintln(os.Stderr, "dashboard helper received unexpected arguments")
		os.Exit(2)
	}
	if mode == "hosted" {
		fmt.Println("https://agtask-example.openai.chatgpt.site")
		return
	}
	if mode == "invalid" {
		fmt.Println("http://example.com:34567/not-local/")
		return
	}
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	host := listener.Addr().String()
	fmt.Printf("http://%s/%s/\n", host, helperToken)
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Host != host || !strings.HasPrefix(r.URL.Path, "/"+helperToken+"/") {
			http.NotFound(w, r)
			return
		}
		if r.Method == http.MethodPatch && r.Header.Get("Origin") != "http://"+host {
			http.Error(w, "invalid origin", http.StatusForbidden)
			return
		}
		if r.URL.Path == "/"+helperToken+"/" {
			w.Header().Set("Content-Security-Policy", "default-src 'self'")
		}
		fmt.Fprintf(w, "dashboard route %s", strings.TrimPrefix(r.URL.RequestURI(), "/"+helperToken))
	})
	if err := http.Serve(listener, handler); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
