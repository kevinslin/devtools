package service

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"testing"
	"time"

	"cozy/internal/admin"
	"cozy/internal/config"
)

func shortTempDir(t *testing.T) string {
	t.Helper()
	dir, err := os.MkdirTemp("", "cozy-")
	if err != nil {
		t.Fatalf("create short private runtime directory: %v", err)
	}
	t.Cleanup(func() {
		if err := os.RemoveAll(dir); err != nil {
			t.Errorf("remove short private runtime directory: %v", err)
		}
	})
	return dir
}

func startTestManager(t *testing.T, cfg config.Config, dir string) *Manager {
	t.Helper()
	m, err := Start(cfg, Options{Addr: "127.0.0.1:0", StateDir: dir})
	if err != nil {
		t.Fatalf("start manager: %v", err)
	}
	t.Cleanup(func() {
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()
		if err := m.Shutdown(ctx); err != nil {
			t.Errorf("shutdown manager: %v", err)
		}
	})
	return m
}

func startConfiguredTestManager(t *testing.T, cfg config.Config, dir, path string) *Manager {
	t.Helper()
	m, err := Start(cfg, Options{
		Addr: "127.0.0.1:0", StateDir: dir, ConfigPath: path,
	})
	if err != nil {
		t.Fatalf("start configured manager: %v", err)
	}
	t.Cleanup(func() {
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()
		if err := m.Shutdown(ctx); err != nil {
			t.Errorf("shutdown configured manager: %v", err)
		}
	})
	return m
}

func writeSiteConfig(t *testing.T, path string, sites []config.Site) {
	t.Helper()
	var contents strings.Builder
	contents.WriteString("version: 1\nsites:\n")
	for _, site := range sites {
		fmt.Fprintf(&contents, "  - name: %s\n    url: %s\n", site.Name, site.URL)
		if site.RedirectCommand != "" {
			fmt.Fprintf(&contents, "    redirect_command: %s\n", strconv.Quote(site.RedirectCommand))
		} else {
			fmt.Fprintf(&contents, "    run: %s\n", strconv.Quote(site.Run))
		}
	}
	if err := os.WriteFile(path, []byte(contents.String()), 0o600); err != nil {
		t.Fatalf("write hermetic site configuration: %v", err)
	}
}

func stateSite(t *testing.T, state State, name string) SiteState {
	t.Helper()
	for _, site := range state.Sites {
		if site.Name == name {
			return site
		}
	}
	t.Fatalf("runtime state does not contain %s", name)
	return SiteState{}
}

func siteResponse(t *testing.T, m *Manager, host string) (int, string) {
	t.Helper()
	req, err := http.NewRequest(http.MethodGet, "http://"+m.State().Addr+"/", nil)
	if err != nil {
		t.Fatal(err)
	}
	req.Host = host
	client := &http.Client{Timeout: 2 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		t.Fatalf("request routed site %s: %v", host, err)
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("read routed site %s: %v", host, err)
	}
	return resp.StatusCode, string(body)
}

func adminResponse(t *testing.T, m *Manager, method, path, body, host, origin string) (int, []byte) {
	t.Helper()
	req, err := http.NewRequest(method, "http://"+m.State().Addr+path, strings.NewReader(body))
	if err != nil {
		t.Fatalf("construct admin request: %v", err)
	}
	req.Host = host
	if origin != "" {
		req.Header.Set("Origin", origin)
	}
	req.Header.Set("Content-Type", "application/json")
	client := &http.Client{Timeout: 5 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		t.Fatalf("request embedded admin %s: %v", path, err)
	}
	defer resp.Body.Close()
	data, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("read embedded admin response: %v", err)
	}
	return resp.StatusCode, data
}

func sleepingSite(name string) config.Site {
	return config.Site{Name: name, URL: "http://" + name, Run: testHTTPCommand(name)}
}

func TestStartPersistsDistinctPortsAndPrivateState(t *testing.T) {
	dir := filepath.Join(shortTempDir(t), "runtime")
	m := startTestManager(t, config.Config{Version: 1, Sites: []config.Site{
		sleepingSite("fishy.localhost"), sleepingSite("pond.localhost"),
	}}, dir)
	state, err := LoadState(dir)
	if err != nil {
		t.Fatalf("load state: %v", err)
	}
	if state.PID != os.Getpid() || state.Addr != m.State().Addr ||
		state.Token == "" || state.ControlPath != filepath.Join(dir, "control.sock") {
		t.Fatalf("unexpected proxy state: %+v", state)
	}
	if !OwnsState(state) {
		t.Fatal("running manager did not authenticate ownership of its state")
	}
	if len(state.Sites) != 2 || state.Sites[0].Port == state.Sites[1].Port {
		t.Fatalf("expected two distinct site ports: %+v", state.Sites)
	}
	for _, site := range state.Sites {
		if site.PID <= 0 || site.Port <= 0 || filepath.Dir(site.LogPath) != dir {
			t.Errorf("incomplete site state: %+v", site)
		}
	}
	for _, check := range []struct {
		path string
		want os.FileMode
	}{{dir, 0o700}, {filepath.Join(dir, "state.json"), 0o600}, {filepath.Join(dir, "control.sock"), 0o600}} {
		info, err := os.Stat(check.path)
		if err != nil {
			t.Fatalf("stat %s: %v", check.path, err)
		}
		if got := info.Mode().Perm(); got != check.want {
			t.Errorf("%s permissions = %04o, want %04o", check.path, got, check.want)
		}
	}
}

func TestRedirectCommandRunsOnceAndPreservesHostedPaths(t *testing.T) {
	dir := filepath.Join(shortTempDir(t), "runtime")
	m := startTestManager(t, config.Config{Version: 1, Sites: []config.Site{
		sleepingSite("fishy.localhost"),
		{
			Name: "tasks.localhost", URL: "http://tasks.localhost",
			RedirectCommand: "printf 'https://example.com/dashboard\\n'",
		},
	}}, dir)
	state := m.State()
	if len(state.Sites) != 2 || state.Sites[1].RedirectCommand == "" ||
		state.Sites[1].PID != 0 || state.Sites[1].Port != 0 {
		t.Fatalf("redirect site should have no persistent child: %+v", state.Sites)
	}

	client := &http.Client{
		Timeout: time.Second,
		CheckRedirect: func(*http.Request, []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
	for _, path := range []string{"/", "/tasks/~example?search=cozy"} {
		request, err := http.NewRequest(http.MethodGet, "http://"+state.Addr+path, nil)
		if err != nil {
			t.Fatal(err)
		}
		request.Host = "tasks.localhost"
		response, err := client.Do(request)
		if err != nil {
			t.Fatalf("request redirect site: %v", err)
		}
		_ = response.Body.Close()
		if response.StatusCode != http.StatusTemporaryRedirect {
			t.Fatalf("redirect status = %d, want %d", response.StatusCode, http.StatusTemporaryRedirect)
		}
		if got, want := response.Header.Get("Location"), "https://example.com/dashboard"+path; got != want {
			t.Fatalf("redirect location = %q, want %q", got, want)
		}
	}

	if err := m.RestartSite(context.Background(), "tasks.localhost"); err != nil {
		t.Fatalf("restart redirect site: %v", err)
	}
}

func TestRedirectCommandRejectsUnsafeOrInvalidDestinations(t *testing.T) {
	for _, test := range []struct {
		name    string
		command string
	}{
		{name: "credentials", command: "printf 'https://user:secret@example.com/\\n'"},
		{name: "wrong scheme", command: "printf 'javascript:alert(1)\\n'"},
		{name: "multiple destinations", command: "printf 'https://example.com/\\nhttps://other.example/\\n'"},
		{name: "command failure", command: "exit 7"},
	} {
		t.Run(test.name, func(t *testing.T) {
			_, err := Start(config.Config{Version: 1, Sites: []config.Site{{
				Name: "tasks.localhost", URL: "http://tasks.localhost", RedirectCommand: test.command,
			}}}, Options{Addr: "127.0.0.1:0", StateDir: filepath.Join(shortTempDir(t), "runtime")})
			if err == nil {
				t.Fatal("invalid redirect command unexpectedly started")
			}
			if strings.Contains(err.Error(), "secret") {
				t.Fatalf("redirect error exposed credentials: %v", err)
			}
		})
	}
}

func TestRefreshSwitchesBetweenRunAndRedirectCommandWithoutRestartingPeers(t *testing.T) {
	dir := shortTempDir(t)
	path := filepath.Join(dir, "cozy.yaml")
	fishy := sleepingSite("fishy.localhost")
	tasks := sleepingSite("tasks.localhost")
	writeSiteConfig(t, path, []config.Site{fishy, tasks})
	m := startConfiguredTestManager(t, config.Config{Version: 1, Sites: []config.Site{fishy, tasks}},
		filepath.Join(dir, "runtime"), path)
	originalFishyPID := stateSite(t, m.State(), fishy.Name).PID

	tasks.Run = ""
	tasks.RedirectCommand = "printf 'https://example.com/\\n'"
	writeSiteConfig(t, path, []config.Site{fishy, tasks})
	if _, err := m.controlAction("refresh", ""); err != nil {
		t.Fatalf("refresh to redirect command: %v", err)
	}
	if got := stateSite(t, m.State(), fishy.Name).PID; got != originalFishyPID {
		t.Fatalf("refresh restarted unchanged peer: got PID %d, want %d", got, originalFishyPID)
	}
	redirect := stateSite(t, m.State(), tasks.Name)
	if redirect.RedirectCommand == "" || redirect.PID != 0 {
		t.Fatalf("refresh did not activate childless redirect: %+v", redirect)
	}

	tasks.RedirectCommand = ""
	tasks.Run = testHTTPCommand(tasks.Name)
	writeSiteConfig(t, path, []config.Site{fishy, tasks})
	if _, err := m.controlAction("refresh", ""); err != nil {
		t.Fatalf("refresh back to managed service: %v", err)
	}
	if got := stateSite(t, m.State(), fishy.Name).PID; got != originalFishyPID {
		t.Fatalf("second refresh restarted unchanged peer: got PID %d, want %d", got, originalFishyPID)
	}
	managed := stateSite(t, m.State(), tasks.Name)
	if managed.RedirectCommand != "" || managed.PID == 0 {
		t.Fatalf("refresh did not restore managed service: %+v", managed)
	}
}

func TestProxyRoutesByHost(t *testing.T) {
	t.Parallel()
	cfg := config.Config{Version: 1, Sites: []config.Site{
		{Name: "fishy.localhost", URL: "http://fishy.localhost", Run: testHTTPCommand("fishy.localhost")},
		{Name: "pond.localhost", URL: "http://pond.localhost", Run: testHTTPCommand("pond.localhost")},
	}}
	m := startTestManager(t, cfg, shortTempDir(t))
	for _, tc := range []struct {
		host string
		want string
		code int
	}{
		{host: "fishy.localhost", want: "fishy.localhost", code: http.StatusOK},
		{host: "fishy.localhost:80", want: "fishy.localhost", code: http.StatusOK},
		{host: "pond.localhost", want: "pond.localhost", code: http.StatusOK},
		{host: "missing.localhost", code: http.StatusNotFound},
	} {
		t.Run(tc.host, func(t *testing.T) {
			deadline := time.Now().Add(5 * time.Second)
			for {
				req, err := http.NewRequest(http.MethodGet, "http://"+m.State().Addr+"/", nil)
				if err != nil {
					t.Fatal(err)
				}
				req.Host = tc.host
				resp, err := http.DefaultClient.Do(req)
				if err == nil {
					body, readErr := io.ReadAll(resp.Body)
					_ = resp.Body.Close()
					if readErr != nil {
						t.Fatal(readErr)
					}
					if resp.StatusCode == tc.code && (tc.want == "" || strings.Contains(string(body), tc.want)) {
						return
					}
					if time.Now().After(deadline) {
						t.Fatalf("host %s: status %d, body %q; want status %d and %q", tc.host, resp.StatusCode, body, tc.code, tc.want)
					}
				} else if time.Now().After(deadline) {
					t.Fatalf("request host %s: %v", tc.host, err)
				}
				time.Sleep(15 * time.Millisecond)
			}
		})
	}
}

func testHTTPCommand(response string) string {
	return testHTTPCommandWithDelay(response, 0)
}

func testHTTPCommandWithDelay(response string, delay time.Duration) string {
	quote := func(value string) string {
		return "'" + strings.ReplaceAll(value, "'", "'\\''") + "'"
	}
	return fmt.Sprintf("exec env COZY_TEST_HELPER=1 COZY_TEST_RESPONSE=%s COZY_TEST_DELAY_MS=%d %s -test.run=^TestServiceHTTPHelperProcess$",
		quote(response), delay.Milliseconds(), quote(os.Args[0]))
}

func TestServiceHTTPHelperProcess(t *testing.T) {
	if os.Getenv("COZY_TEST_HELPER") != "1" {
		return
	}
	if value := os.Getenv("COZY_TEST_DELAY_MS"); value != "" {
		delay, err := strconv.Atoi(value)
		if err != nil {
			t.Fatalf("parse test backend startup delay %q: %v", value, err)
		}
		time.Sleep(time.Duration(delay) * time.Millisecond)
	}
	addr := net.JoinHostPort("127.0.0.1", os.Getenv("PORT"))
	handler := http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = io.WriteString(w, os.Getenv("COZY_TEST_RESPONSE"))
	})
	if err := http.ListenAndServe(addr, handler); err != nil {
		t.Fatalf("serve test backend on %s: %v", addr, err)
	}
}

func TestShutdownTerminatesChildrenAndRemovesOwnedState(t *testing.T) {
	dir := shortTempDir(t)
	m := startTestManager(t, config.Config{Version: 1, Sites: []config.Site{sleepingSite("fishy.localhost")}}, dir)
	pid := m.State().Sites[0].PID
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	if err := m.Shutdown(ctx); err != nil {
		t.Fatalf("shutdown: %v", err)
	}
	if _, err := LoadState(dir); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("expected removed state, got %v", err)
	}
	if err := syscall.Kill(pid, 0); !errors.Is(err, syscall.ESRCH) {
		t.Fatalf("expected child %d to be reaped, got %v", pid, err)
	}
}

func TestStartReportsPortConflictWithoutStartingChildren(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	dir := shortTempDir(t)
	_, err = Start(config.Config{Version: 1, Sites: []config.Site{sleepingSite("fishy.localhost")}}, Options{
		Addr: listener.Addr().String(), StateDir: dir,
	})
	if err == nil || !strings.Contains(err.Error(), "already in use") {
		t.Fatalf("expected actionable port-conflict error, got %v", err)
	}
	if _, statErr := os.Stat(filepath.Join(dir, "state.json")); !errors.Is(statErr, os.ErrNotExist) {
		t.Fatalf("port conflict created runtime state: %v", statErr)
	}
}

func TestStartRejectsNonLoopbackProxyWithoutStartingChildren(t *testing.T) {
	for _, addr := range []string{":0", "0.0.0.0:0"} {
		t.Run(addr, func(t *testing.T) {
			dir := filepath.Join(shortTempDir(t), "runtime")
			_, err := Start(config.Config{Version: 1, Sites: []config.Site{
				sleepingSite("fishy.localhost"),
			}}, Options{Addr: addr, StateDir: dir})
			if err == nil || !strings.Contains(err.Error(), "loopback") {
				t.Fatalf("expected actionable loopback-only error, got %v", err)
			}
			if _, err := os.Stat(dir); !errors.Is(err, os.ErrNotExist) {
				t.Fatalf("rejected proxy address created runtime directory or children: %v", err)
			}
		})
	}
}

func TestStartCapturesOutputAndExportsBothPortVariables(t *testing.T) {
	dir := shortTempDir(t)
	m := startTestManager(t, config.Config{Version: 1, Sites: []config.Site{{
		Name: "fishy.localhost", URL: "http://fishy.localhost",
		Run: "printf 'port=%s cozy=%s\\n' \"$PORT\" \"$COZY_PORT\"; " + testHTTPCommand("fishy.localhost"),
	}}}, dir)
	state := m.State().Sites[0]
	want := fmt.Sprintf("port=%d cozy=%d", state.Port, state.Port)
	deadline := time.Now().Add(2 * time.Second)
	for {
		data, err := os.ReadFile(state.LogPath)
		if err != nil {
			t.Fatalf("read service log: %v", err)
		}
		if strings.Contains(string(data), want) {
			break
		}
		if time.Now().After(deadline) {
			t.Fatalf("service log = %q, want %q", data, want)
		}
		time.Sleep(10 * time.Millisecond)
	}
}

func TestStartFailureCleansUpPreviouslyStartedChildren(t *testing.T) {
	dir := shortTempDir(t)
	if err := os.Mkdir(filepath.Join(dir, "broken.localhost.log"), 0o700); err != nil {
		t.Fatalf("create deterministic site log conflict: %v", err)
	}
	_, err := Start(config.Config{Version: 1, Sites: []config.Site{
		{
			Name: "fishy.localhost", URL: "http://fishy.localhost",
			Run: "printf 'child=%s\\n' \"$$\"; " + testHTTPCommand("fishy.localhost"),
		},
		sleepingSite("broken.localhost"),
	}}, Options{Addr: "127.0.0.1:0", StateDir: dir})
	if err == nil || !strings.Contains(err.Error(), "broken.localhost") || !strings.Contains(err.Error(), "open log") {
		t.Fatalf("expected actionable site log failure, got %v", err)
	}
	if _, stateErr := LoadState(dir); !errors.Is(stateErr, os.ErrNotExist) {
		t.Fatalf("failed start retained state: %v", stateErr)
	}
	data, readErr := os.ReadFile(filepath.Join(dir, "fishy.localhost.log"))
	if readErr != nil {
		t.Fatalf("read previously started site log: %v", readErr)
	}
	var pid int
	if _, err := fmt.Sscanf(strings.TrimSpace(string(data)), "child=%d", &pid); err != nil || pid <= 0 {
		t.Fatalf("expected recorded child PID in previously started site log, got %q: %v", data, err)
	}
	if err := syscall.Kill(pid, 0); !errors.Is(err, syscall.ESRCH) {
		t.Fatalf("transactional rollback did not reap child %d: %v", pid, err)
	}
}

func TestEarlyChildExitIsReportedAndLogged(t *testing.T) {
	dir := shortTempDir(t)
	m, err := Start(config.Config{Version: 1, Sites: []config.Site{{
		Name: "broken.localhost", URL: "http://broken.localhost",
		Run: "printf 'startup failed\\n' >&2; exit 42",
	}}}, Options{Addr: "127.0.0.1:0", StateDir: dir})
	if err == nil {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		err = m.Wait(ctx)
	}
	if err == nil || !strings.Contains(err.Error(), "broken.localhost") || !strings.Contains(err.Error(), "exit") {
		t.Fatalf("expected actionable early-child exit, got %v", err)
	}
	if _, stateErr := LoadState(dir); !errors.Is(stateErr, os.ErrNotExist) {
		t.Fatalf("early child exit retained state: %v", stateErr)
	}
	data, readErr := os.ReadFile(filepath.Join(dir, "broken.localhost.log"))
	if readErr != nil || !strings.Contains(string(data), "startup failed") {
		t.Fatalf("early-child failure log = %q, error %v", data, readErr)
	}
}

func TestLoadStateReportsMalformedJSON(t *testing.T) {
	dir := shortTempDir(t)
	if err := os.WriteFile(filepath.Join(dir, "state.json"), []byte("{"), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := LoadState(dir); err == nil || !strings.Contains(err.Error(), "decode") {
		t.Fatalf("expected state decoding error, got %v", err)
	}
}

func TestOwnsStateRejectsForgedTokenAndUnrelatedLivePID(t *testing.T) {
	dir := shortTempDir(t)
	m := startTestManager(t, config.Config{Version: 1, Sites: []config.Site{
		sleepingSite("fishy.localhost"),
	}}, dir)
	state := m.State()
	if !OwnsState(state) {
		t.Fatal("expected authenticated manager state")
	}
	for _, tc := range []struct {
		name  string
		state State
	}{
		{name: "zero process", state: withStatePID(state, 0)},
		{name: "forged token", state: withStateToken(state, strings.Repeat("a", 64))},
		{name: "unrelated live process", state: State{
			PID: os.Getpid(), Addr: state.Addr,
			Token: strings.Repeat("b", 64), ControlPath: state.ControlPath,
		}},
		{name: "unrelated control path", state: State{
			PID: os.Getpid(), Addr: state.Addr,
			Token: state.Token, ControlPath: filepath.Join(dir, "unrelated.sock"),
		}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if OwnsState(tc.state) {
				t.Fatalf("accepted forged state: %+v", tc.state)
			}
		})
	}
}

func withStatePID(state State, pid int) State {
	state.PID = pid
	return state
}

func withStateToken(state State, token string) State {
	state.Token = token
	return state
}

func TestStartReplacesStaleSocketAndUnauthenticatedLivePID(t *testing.T) {
	dir := shortTempDir(t)
	path := filepath.Join(dir, "control.sock")
	stale, err := net.Listen("unix", path)
	if err != nil {
		t.Fatalf("create stale control socket: %v", err)
	}
	stale.(*net.UnixListener).SetUnlinkOnClose(false)
	if err := stale.Close(); err != nil {
		t.Fatalf("close stale control socket: %v", err)
	}
	if err := persistState(dir, State{
		PID: os.Getpid(), Addr: "127.0.0.1:1",
		Token: strings.Repeat("a", 64), ControlPath: path,
	}); err != nil {
		t.Fatalf("persist forged live-process state: %v", err)
	}
	m := startTestManager(t, config.Config{Version: 1, Sites: []config.Site{
		sleepingSite("fishy.localhost"),
	}}, dir)
	state, err := LoadState(dir)
	if err != nil {
		t.Fatalf("load replacement state: %v", err)
	}
	if !OwnsState(state) || state.Token != m.State().Token || state.Token == strings.Repeat("a", 64) {
		t.Fatalf("stale socket or forged live process was not replaced: %+v", state)
	}
}

func TestStartFailsWhenBackendNeverListens(t *testing.T) {
	dir := shortTempDir(t)
	started := time.Now()
	_, err := Start(config.Config{Version: 1, Sites: []config.Site{{
		Name: "fishy.localhost", URL: "http://fishy.localhost",
		Run: "printf 'backend never started\\n'; exec sleep 60",
	}}}, Options{Addr: "127.0.0.1:0", StateDir: dir})
	if err == nil || !strings.Contains(err.Error(), "fishy.localhost") ||
		!strings.Contains(err.Error(), "loopback port") ||
		!strings.Contains(err.Error(), "fishy.localhost.log") {
		t.Fatalf("expected actionable backend-readiness timeout, got %v", err)
	}
	if elapsed := time.Since(started); elapsed > 5*time.Second {
		t.Fatalf("backend-readiness timeout was not bounded: %v", elapsed)
	}
	if _, err := LoadState(dir); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("backend-readiness failure retained state: %v", err)
	}
	if _, err := os.Stat(filepath.Join(dir, "control.sock")); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("backend-readiness failure retained control socket: %v", err)
	}
	data, err := os.ReadFile(filepath.Join(dir, "fishy.localhost.log"))
	if err != nil || !strings.Contains(string(data), "backend never started") {
		t.Fatalf("backend-readiness failure log = %q, error %v", data, err)
	}
}

func TestStartWaitsForDelayedBackendListener(t *testing.T) {
	dir := shortTempDir(t)
	started := time.Now()
	m := startTestManager(t, config.Config{Version: 1, Sites: []config.Site{{
		Name: "fishy.localhost", URL: "http://fishy.localhost",
		Run: testHTTPCommandWithDelay("fishy.localhost", 100*time.Millisecond),
	}}}, dir)
	if elapsed := time.Since(started); elapsed < 80*time.Millisecond {
		t.Fatalf("manager returned before its delayed backend could be listening: %v", elapsed)
	}
	addr := net.JoinHostPort("127.0.0.1", strconv.Itoa(m.State().Sites[0].Port))
	conn, err := net.DialTimeout("tcp", addr, time.Second)
	if err != nil {
		t.Fatalf("manager returned without a listening backend at %s: %v", addr, err)
	}
	_ = conn.Close()
}

func TestStartReportsOverlongControlSocketPath(t *testing.T) {
	dir := filepath.Join(shortTempDir(t), strings.Repeat("a", len(syscall.RawSockaddrUnix{}.Path)))
	_, err := Start(config.Config{Version: 1, Sites: []config.Site{
		sleepingSite("fishy.localhost"),
	}}, Options{Addr: "127.0.0.1:0", StateDir: dir})
	if err == nil || !strings.Contains(err.Error(), "too long") ||
		!strings.Contains(err.Error(), "shorter state directory") {
		t.Fatalf("expected actionable control-socket path error, got %v", err)
	}
	if _, err := LoadState(dir); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("overlong control socket path created runtime state: %v", err)
	}
}

func TestRequestRestartsOnlySelectedSiteWithoutSupervisorOutage(t *testing.T) {
	dir := shortTempDir(t)
	m := startTestManager(t, config.Config{Version: 1, Sites: []config.Site{
		sleepingSite("fishy.localhost"), sleepingSite("pond.localhost"),
	}}, dir)
	before := m.State()
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	result, err := Request(ctx, before, "restart", "pond.localhost")
	if err != nil {
		t.Fatalf("restart selected site: %v", err)
	}
	if !strings.Contains(result.Message, "pond.localhost") {
		t.Fatalf("restart response = %q, want selected site", result.Message)
	}
	after, err := LoadState(dir)
	if err != nil {
		t.Fatalf("load restarted runtime state: %v", err)
	}
	if after.PID != before.PID || after.Addr != before.Addr || after.Token != before.Token {
		t.Fatalf("targeted restart replaced the supervisor: before %+v; after %+v", before, after)
	}
	if got, want := stateSite(t, after, "fishy.localhost").PID,
		stateSite(t, before, "fishy.localhost").PID; got != want {
		t.Fatalf("targeted restart interrupted unrelated site: PID %d, want %d", got, want)
	}
	old := stateSite(t, before, "pond.localhost")
	restarted := stateSite(t, after, "pond.localhost")
	if restarted.PID == old.PID || restarted.Port == old.Port {
		t.Fatalf("targeted restart did not allocate a replacement: old %+v; new %+v", old, restarted)
	}
	if err := syscall.Kill(old.PID, 0); !errors.Is(err, syscall.ESRCH) {
		t.Fatalf("replaced site process %d was not reaped: %v", old.PID, err)
	}
	for _, name := range []string{"fishy.localhost", "pond.localhost"} {
		if status, body := siteResponse(t, m, name); status != http.StatusOK || !strings.Contains(body, name) {
			t.Fatalf("site %s became unavailable: status %d, body %q", name, status, body)
		}
	}
}

func TestRequestRestartsAllSitesWithoutReplacingSupervisor(t *testing.T) {
	dir := shortTempDir(t)
	m := startTestManager(t, config.Config{Version: 1, Sites: []config.Site{
		sleepingSite("fishy.localhost"), sleepingSite("pond.localhost"),
	}}, dir)
	before := m.State()
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	result, err := Request(ctx, before, "restart", "")
	if err != nil {
		t.Fatalf("restart all sites: %v", err)
	}
	if !strings.Contains(result.Message, "2 sites") {
		t.Fatalf("all-sites restart response = %q", result.Message)
	}
	after := m.State()
	if after.PID != before.PID || after.Addr != before.Addr {
		t.Fatalf("all-sites restart replaced the supervisor: before %+v; after %+v", before, after)
	}
	for _, name := range []string{"fishy.localhost", "pond.localhost"} {
		if stateSite(t, after, name).PID == stateSite(t, before, name).PID {
			t.Fatalf("all-sites restart did not replace %s", name)
		}
		if status, body := siteResponse(t, m, name); status != http.StatusOK || !strings.Contains(body, name) {
			t.Fatalf("restarted site %s is unhealthy: status %d, body %q", name, status, body)
		}
	}
}

func TestRequestRefreshAddsChangesRemovesAndPreservesSites(t *testing.T) {
	dir := shortTempDir(t)
	path := filepath.Join(dir, "cozy.yaml")
	initial := []config.Site{
		sleepingSite("fishy.localhost"),
		sleepingSite("pond.localhost"),
		sleepingSite("old.localhost"),
	}
	writeSiteConfig(t, path, initial)
	m := startConfiguredTestManager(t, config.Config{Version: 1, Sites: initial}, dir, path)
	before := m.State()
	updated := []config.Site{
		sleepingSite("fishy.localhost"),
		{
			Name: "pond.localhost", URL: "http://pond.localhost",
			Run: testHTTPCommand("updated pond.localhost"),
		},
		sleepingSite("garden.localhost"),
	}
	writeSiteConfig(t, path, updated)
	ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
	defer cancel()
	result, err := Request(ctx, before, "refresh", "")
	if err != nil {
		t.Fatalf("refresh changed configuration: %v", err)
	}
	for _, expected := range []string{"1 added", "1 changed", "1 removed", "1 unchanged"} {
		if !strings.Contains(result.Message, expected) {
			t.Errorf("refresh response %q does not include %q", result.Message, expected)
		}
	}
	after, err := LoadState(dir)
	if err != nil {
		t.Fatalf("load refreshed state: %v", err)
	}
	if after.PID != before.PID || after.Addr != before.Addr {
		t.Fatalf("refresh replaced the supervisor: before %+v; after %+v", before, after)
	}
	if got, want := stateSite(t, after, "fishy.localhost").PID,
		stateSite(t, before, "fishy.localhost").PID; got != want {
		t.Fatalf("refresh restarted unchanged site: PID %d, want %d", got, want)
	}
	if stateSite(t, after, "pond.localhost").PID == stateSite(t, before, "pond.localhost").PID {
		t.Fatal("refresh did not replace changed site")
	}
	stateSite(t, after, "garden.localhost")
	if status, body := siteResponse(t, m, "pond.localhost"); status != http.StatusOK ||
		!strings.Contains(body, "updated pond.localhost") {
		t.Fatalf("changed site route was not atomically updated: status %d, body %q", status, body)
	}
	if status, body := siteResponse(t, m, "garden.localhost"); status != http.StatusOK ||
		!strings.Contains(body, "garden.localhost") {
		t.Fatalf("added site route is unhealthy: status %d, body %q", status, body)
	}
	if status, _ := siteResponse(t, m, "old.localhost"); status != http.StatusNotFound {
		t.Fatalf("removed site still has a route: status %d", status)
	}
	old := stateSite(t, before, "old.localhost")
	if err := syscall.Kill(old.PID, 0); !errors.Is(err, syscall.ESRCH) {
		t.Fatalf("removed site process %d was not reaped: %v", old.PID, err)
	}
}

func TestRequestRefreshFailurePreservesRunningRoute(t *testing.T) {
	dir := shortTempDir(t)
	path := filepath.Join(dir, "cozy.yaml")
	initial := []config.Site{sleepingSite("fishy.localhost")}
	writeSiteConfig(t, path, initial)
	m := startConfiguredTestManager(t, config.Config{Version: 1, Sites: initial}, dir, path)
	before := m.State()
	updated := []config.Site{{
		Name: "fishy.localhost", URL: "http://fishy.localhost",
		Run: "printf 'replacement failed\\n' >&2; exit 42",
	}}
	writeSiteConfig(t, path, updated)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if _, err := Request(ctx, before, "refresh", ""); err == nil ||
		!strings.Contains(err.Error(), "fishy.localhost") {
		t.Fatalf("expected actionable replacement failure, got %v", err)
	}
	after, err := LoadState(dir)
	if err != nil {
		t.Fatalf("load preserved state: %v", err)
	}
	if stateSite(t, after, "fishy.localhost").PID != stateSite(t, before, "fishy.localhost").PID {
		t.Fatal("failed refresh replaced the healthy site")
	}
	if status, body := siteResponse(t, m, "fishy.localhost"); status != http.StatusOK ||
		!strings.Contains(body, "fishy.localhost") {
		t.Fatalf("failed refresh disrupted healthy route: status %d, body %q", status, body)
	}
	if err := os.WriteFile(path, []byte("version: invalid\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := Request(ctx, before, "refresh", ""); err == nil {
		t.Fatal("refresh accepted invalid configuration")
	}
	if stateSite(t, m.State(), "fishy.localhost").PID != stateSite(t, before, "fishy.localhost").PID {
		t.Fatal("invalid configuration disrupted healthy site")
	}
}

func TestRequestRejectsForgedTokenAndUnknownActions(t *testing.T) {
	dir := shortTempDir(t)
	m := startTestManager(t, config.Config{Version: 1, Sites: []config.Site{
		sleepingSite("fishy.localhost"),
	}}, dir)
	state := m.State()
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	forged := state
	forged.Token = strings.Repeat("a", 64)
	if _, err := Request(ctx, forged, "restart", "fishy.localhost"); err == nil {
		t.Fatal("control request accepted a forged ownership token")
	}
	if _, err := Request(ctx, state, "restart", "missing.localhost"); err == nil ||
		!strings.Contains(err.Error(), "missing.localhost") {
		t.Fatalf("expected actionable unknown site error, got %v", err)
	}
	if _, err := Request(ctx, state, "unrecognized", ""); err == nil ||
		!strings.Contains(err.Error(), "control action") {
		t.Fatalf("expected actionable unknown action error, got %v", err)
	}
	if _, err := Request(ctx, state, "refresh", ""); err == nil ||
		!strings.Contains(err.Error(), "configuration") {
		t.Fatalf("expected missing configuration-path error, got %v", err)
	}
	if stateSite(t, m.State(), "fishy.localhost").PID != stateSite(t, state, "fishy.localhost").PID {
		t.Fatal("rejected control request disrupted the running service")
	}
}

func TestConcurrentControlRequestsPreserveRoutesAndState(t *testing.T) {
	dir := shortTempDir(t)
	m := startTestManager(t, config.Config{Version: 1, Sites: []config.Site{
		sleepingSite("fishy.localhost"), sleepingSite("pond.localhost"),
	}}, dir)
	stop := make(chan struct{})
	failures := make(chan error, 16)
	var readers sync.WaitGroup
	for range 3 {
		readers.Add(1)
		go func() {
			defer readers.Done()
			client := &http.Client{Timeout: 2 * time.Second}
			for {
				select {
				case <-stop:
					return
				default:
				}
				state := m.State()
				if len(state.Sites) != 2 {
					select {
					case failures <- fmt.Errorf("concurrent state contains %d sites", len(state.Sites)):
					default:
					}
					return
				}
				req, err := http.NewRequest(http.MethodGet, "http://"+state.Addr+"/", nil)
				if err != nil {
					select {
					case failures <- err:
					default:
					}
					return
				}
				req.Host = "fishy.localhost"
				resp, err := client.Do(req)
				if err != nil {
					select {
					case failures <- err:
					default:
					}
					return
				}
				_, _ = io.Copy(io.Discard, resp.Body)
				_ = resp.Body.Close()
				if resp.StatusCode != http.StatusOK {
					select {
					case failures <- fmt.Errorf("concurrent route status %d", resp.StatusCode):
					default:
					}
					return
				}
			}
		}()
	}
	for i := 0; i < 3; i++ {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		_, err := Request(ctx, m.State(), "restart", "pond.localhost")
		cancel()
		if err != nil {
			close(stop)
			readers.Wait()
			t.Fatalf("concurrent restart %d: %v", i, err)
		}
	}
	close(stop)
	readers.Wait()
	select {
	case err := <-failures:
		t.Fatalf("concurrent route or state failure: %v", err)
	default:
	}
}

func TestAdminHostServesDashboardAndCuratedSites(t *testing.T) {
	dir := shortTempDir(t)
	m := startTestManager(t, config.Config{Version: 1, Sites: []config.Site{
		sleepingSite("fishy.localhost"),
	}}, dir)
	status, body := adminResponse(t, m, http.MethodGet, "/", "",
		"cozy.localhost:8080", "")
	if status != http.StatusOK || !strings.Contains(strings.ToLower(string(body)), "<!doctype html") {
		t.Fatalf("embedded admin dashboard = status %d, body %q", status, body)
	}
	status, body = adminResponse(t, m, http.MethodGet, "/api/sites", "",
		"cozy.localhost:8080", "")
	if status != http.StatusOK {
		t.Fatalf("embedded site API = status %d, body %q", status, body)
	}
	var response struct {
		Sites []admin.Site `json:"sites"`
	}
	if err := json.Unmarshal(body, &response); err != nil {
		t.Fatalf("decode embedded site API: %v", err)
	}
	if len(response.Sites) != 1 || response.Sites[0].Name != "fishy.localhost" ||
		response.Sites[0].PID != stateSite(t, m.State(), "fishy.localhost").PID {
		t.Fatalf("embedded site API returned unexpected sites: %+v", response.Sites)
	}
	for _, secret := range []string{m.State().Token, "control_path", "control.sock"} {
		if strings.Contains(string(body), secret) {
			t.Fatalf("embedded admin site API exposed private supervisor data %q", secret)
		}
	}
	if status, body := siteResponse(t, m, "fishy.localhost"); status != http.StatusOK ||
		!strings.Contains(body, "fishy.localhost") {
		t.Fatalf("admin host interrupted existing site: status %d, body %q", status, body)
	}
}

func TestAdminAPIRestartsOnlyRequestedSite(t *testing.T) {
	dir := shortTempDir(t)
	m := startTestManager(t, config.Config{Version: 1, Sites: []config.Site{
		sleepingSite("fishy.localhost"), sleepingSite("pond.localhost"),
	}}, dir)
	before := m.State()
	status, body := adminResponse(t, m, http.MethodPost,
		"/api/sites/pond.localhost/restart", "{}",
		"cozy.localhost", "http://cozy.localhost")
	if status != http.StatusOK || !strings.Contains(string(body), "pond.localhost") {
		t.Fatalf("admin targeted restart = status %d, body %q", status, body)
	}
	after := m.State()
	if after.PID != before.PID || after.Addr != before.Addr {
		t.Fatalf("admin restart interrupted the proxy supervisor: before %+v; after %+v", before, after)
	}
	if got, want := stateSite(t, after, "fishy.localhost").PID,
		stateSite(t, before, "fishy.localhost").PID; got != want {
		t.Fatalf("admin restart interrupted Fishy: PID %d, want %d", got, want)
	}
	if stateSite(t, after, "pond.localhost").PID == stateSite(t, before, "pond.localhost").PID {
		t.Fatal("admin restart did not replace the requested site")
	}
	for _, name := range []string{"fishy.localhost", "pond.localhost"} {
		if status, body := siteResponse(t, m, name); status != http.StatusOK ||
			!strings.Contains(body, name) {
			t.Fatalf("admin restart disrupted %s: status %d, body %q", name, status, body)
		}
	}
}

func TestAdminAPIAddSitePersistsConfigurationAndStartsBackend(t *testing.T) {
	dir := shortTempDir(t)
	path := filepath.Join(dir, "cozy.yaml")
	initial := []config.Site{sleepingSite("fishy.localhost")}
	writeSiteConfig(t, path, initial)
	original, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	original = append([]byte("# Preserve this user comment.\n"), original...)
	if err := os.WriteFile(path, original, 0o600); err != nil {
		t.Fatal(err)
	}
	m := startConfiguredTestManager(t, config.Config{Version: 1, Sites: initial}, dir, path)
	before := m.State()
	payload, err := json.Marshal(admin.Site{
		Name: "garden.localhost", Run: testHTTPCommand("garden.localhost"),
	})
	if err != nil {
		t.Fatal(err)
	}
	status, body := adminResponse(t, m, http.MethodPost, "/api/sites",
		string(payload), "cozy.localhost", "http://cozy.localhost")
	if status != http.StatusCreated {
		t.Fatalf("admin add site = status %d, body %q", status, body)
	}
	after := m.State()
	if stateSite(t, after, "fishy.localhost").PID != stateSite(t, before, "fishy.localhost").PID {
		t.Fatal("adding a site interrupted Fishy")
	}
	garden := stateSite(t, after, "garden.localhost")
	if garden.URL != "http://garden.localhost" || garden.PID <= 0 {
		t.Fatalf("new site did not receive runtime metadata: %+v", garden)
	}
	updated, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read persisted site configuration: %v", err)
	}
	if !bytes.HasPrefix(updated, original) {
		t.Fatalf("adding a site did not preserve original configuration and comments: %q", updated)
	}
	loaded, err := config.Load(path)
	if err != nil || len(loaded.Sites) != 2 || loaded.Sites[1].Name != "garden.localhost" {
		t.Fatalf("new site was not persisted as valid YAML: %+v, error %v", loaded, err)
	}
	if status, body := siteResponse(t, m, "garden.localhost"); status != http.StatusOK ||
		!strings.Contains(body, "garden.localhost") {
		t.Fatalf("new site did not boot: status %d, body %q", status, body)
	}
}

func TestAdminAPIAddFailureRollsBackConfigurationAndSites(t *testing.T) {
	dir := shortTempDir(t)
	path := filepath.Join(dir, "cozy.yaml")
	initial := []config.Site{sleepingSite("fishy.localhost")}
	writeSiteConfig(t, path, initial)
	original, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	m := startConfiguredTestManager(t, config.Config{Version: 1, Sites: initial}, dir, path)
	before := m.State()
	payload, err := json.Marshal(admin.Site{
		Name: "broken.localhost", Run: "printf 'backend failed\\n' >&2; exit 42",
	})
	if err != nil {
		t.Fatal(err)
	}
	status, body := adminResponse(t, m, http.MethodPost, "/api/sites",
		string(payload), "cozy.localhost", "http://cozy.localhost")
	if status != http.StatusInternalServerError || !strings.Contains(string(body), "broken.localhost") {
		t.Fatalf("expected actionable site startup failure: status %d, body %q", status, body)
	}
	restored, err := os.ReadFile(path)
	if err != nil || !bytes.Equal(restored, original) {
		t.Fatalf("failed site add did not restore original configuration: %q, error %v", restored, err)
	}
	after := m.State()
	if len(after.Sites) != 1 ||
		stateSite(t, after, "fishy.localhost").PID != stateSite(t, before, "fishy.localhost").PID {
		t.Fatalf("failed site add disrupted original site state: before %+v; after %+v", before, after)
	}
	if status, _ := siteResponse(t, m, "broken.localhost"); status != http.StatusNotFound {
		t.Fatalf("failed site add published a broken route: status %d", status)
	}
	if status, body := siteResponse(t, m, "fishy.localhost"); status != http.StatusOK ||
		!strings.Contains(body, "fishy.localhost") {
		t.Fatalf("failed site add disrupted Fishy: status %d, body %q", status, body)
	}
}

func TestAdminAPIRejectsCrossOriginAndReservedSites(t *testing.T) {
	dir := shortTempDir(t)
	path := filepath.Join(dir, "cozy.yaml")
	initial := []config.Site{sleepingSite("fishy.localhost")}
	writeSiteConfig(t, path, initial)
	m := startConfiguredTestManager(t, config.Config{Version: 1, Sites: initial}, dir, path)
	before := m.State()
	payload, err := json.Marshal(admin.Site{
		Name: "garden.localhost", Run: testHTTPCommand("garden.localhost"),
	})
	if err != nil {
		t.Fatal(err)
	}
	status, body := adminResponse(t, m, http.MethodPost, "/api/sites",
		string(payload), "cozy.localhost", "http://untrusted.localhost")
	if status != http.StatusForbidden {
		t.Fatalf("admin accepted cross-origin mutation: status %d, body %q", status, body)
	}
	reserved, err := json.Marshal(admin.Site{
		Name: "cozy.localhost", Run: testHTTPCommand("cozy.localhost"),
	})
	if err != nil {
		t.Fatal(err)
	}
	status, body = adminResponse(t, m, http.MethodPost, "/api/sites",
		string(reserved), "cozy.localhost", "http://cozy.localhost")
	if status != http.StatusBadRequest || !strings.Contains(string(body), "reserved") {
		t.Fatalf("admin accepted its reserved hostname: status %d, body %q", status, body)
	}
	if got := stateSite(t, m.State(), "fishy.localhost").PID; got != stateSite(t, before, "fishy.localhost").PID {
		t.Fatalf("rejected admin mutation interrupted Fishy: PID %d", got)
	}
	if len(m.State().Sites) != 1 {
		t.Fatalf("rejected admin mutation changed configured sites: %+v", m.State().Sites)
	}
}

func TestManagerAddSiteRespectsCancellationAndReservedHostname(t *testing.T) {
	dir := shortTempDir(t)
	m := startTestManager(t, config.Config{Version: 1, Sites: []config.Site{
		sleepingSite("fishy.localhost"),
	}}, dir)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if err := m.AddSite(ctx, admin.Site{
		Name: "garden.localhost", Run: testHTTPCommand("garden.localhost"),
	}); !errors.Is(err, context.Canceled) {
		t.Fatalf("site add did not respect cancellation: %v", err)
	}
	if err := m.AddSite(context.Background(), admin.Site{
		Name: "cozy.localhost", Run: testHTTPCommand("cozy.localhost"),
	}); err == nil || !strings.Contains(err.Error(), "reserved") {
		t.Fatalf("site add accepted reserved admin host: %v", err)
	}
	if err := m.RestartSite(ctx, "fishy.localhost"); !errors.Is(err, context.Canceled) {
		t.Fatalf("site restart did not respect cancellation: %v", err)
	}
}

func TestStartRejectsReservedAdminHostname(t *testing.T) {
	dir := shortTempDir(t)
	_, err := Start(config.Config{Version: 1, Sites: []config.Site{{
		Name: "cozy.localhost", URL: "http://cozy.localhost",
		Run: testHTTPCommand("cozy.localhost"),
	}}}, Options{Addr: "127.0.0.1:0", StateDir: dir})
	if err == nil || !strings.Contains(err.Error(), "reserved") {
		t.Fatalf("manager accepted reserved admin hostname: %v", err)
	}
	if _, err := LoadState(dir); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("reserved admin hostname created runtime state: %v", err)
	}
}

func TestDefaultProxyAddressUsesUnprivilegedPort8080(t *testing.T) {
	if defaultProxyAddress != "127.0.0.1:8080" {
		t.Fatalf("default proxy address = %q, want 127.0.0.1:8080", defaultProxyAddress)
	}
	probe, err := net.Listen("tcp", defaultProxyAddress)
	if err != nil {
		t.Skipf("the default listener is already in use: %v", err)
	}
	if err := probe.Close(); err != nil {
		t.Fatal(err)
	}
	dir := shortTempDir(t)
	m, err := Start(config.Config{Version: 1, Sites: []config.Site{
		sleepingSite("fishy.localhost"),
	}}, Options{StateDir: dir})
	if err != nil {
		if errors.Is(err, syscall.EADDRINUSE) {
			t.Skipf("another service acquired the default listener: %v", err)
		}
		t.Fatalf("start default unprivileged proxy: %v", err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	defer func() {
		if err := m.Shutdown(ctx); err != nil {
			t.Errorf("shutdown default unprivileged proxy: %v", err)
		}
	}()
	if got := m.State().Addr; got != defaultProxyAddress {
		t.Fatalf("default proxy listener = %q, want %q", got, defaultProxyAddress)
	}
}
