package cozy_test

import (
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
	"time"
)

func buildBinary(t *testing.T, output, target string) {
	t.Helper()
	command := exec.Command("go", "build", "-o", output, target)
	if output, err := command.CombinedOutput(); err != nil {
		t.Fatalf("build %s: %v\n%s", target, err, output)
	}
}

func runBinary(t *testing.T, binary string, args ...string) (string, error) {
	t.Helper()
	output, err := exec.Command(binary, args...).CombinedOutput()
	return string(output), err
}

func availableAddress(t *testing.T) string {
	t.Helper()
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("allocate loopback address: %v", err)
	}
	address := listener.Addr().String()
	if err := listener.Close(); err != nil {
		t.Fatalf("release loopback address: %v", err)
	}
	return address
}

func integrationDirectory(t *testing.T) string {
	t.Helper()
	directory, err := os.MkdirTemp("", "cozy-integration-")
	if err != nil {
		t.Fatalf("create short integration directory: %v", err)
	}
	t.Cleanup(func() {
		if err := os.RemoveAll(directory); err != nil {
			t.Errorf("remove integration directory: %v", err)
		}
	})
	return directory
}

func writeConfiguration(t *testing.T, directory, backend string) string {
	t.Helper()
	path := filepath.Join(directory, "cozy.yaml")
	writeConfigurationSites(t, path, backend, "fishy.localhost", "agtask.localhost")
	return path
}

func writeConfigurationSites(t *testing.T, path, backend string, names ...string) {
	t.Helper()
	var configuration strings.Builder
	configuration.WriteString("version: 1\nsites:\n")
	for _, name := range names {
		fmt.Fprintf(&configuration, "  - name: %s\n    url: http://%s\n    run: %s --host 127.0.0.1 --port \"$PORT\" --no-open\n", name, name, backend)
	}
	if err := os.WriteFile(path, []byte(configuration.String()), 0o600); err != nil {
		t.Fatalf("write configuration: %v", err)
	}
}

type runtimeSnapshot struct {
	PID   int               `json:"pid"`
	Sites []runtimeSiteInfo `json:"sites"`
}

type runtimeSiteInfo struct {
	Name string `json:"name"`
	PID  int    `json:"pid"`
	Port int    `json:"port"`
}

func readRuntimeSnapshot(t *testing.T, stateDirectory string) runtimeSnapshot {
	t.Helper()
	data, err := os.ReadFile(filepath.Join(stateDirectory, "state.json"))
	if err != nil {
		t.Fatalf("read runtime state: %v", err)
	}
	var state runtimeSnapshot
	if err := json.Unmarshal(data, &state); err != nil {
		t.Fatalf("decode runtime state: %v", err)
	}
	return state
}

func (state runtimeSnapshot) site(name string) (runtimeSiteInfo, bool) {
	for _, site := range state.Sites {
		if site.Name == name {
			return site, true
		}
	}
	return runtimeSiteInfo{}, false
}

func requireReachableSite(t *testing.T, address, siteName string) {
	t.Helper()
	deadline := time.Now().Add(5 * time.Second)
	for {
		request, err := http.NewRequest(http.MethodGet, "http://"+address, nil)
		if err != nil {
			t.Fatalf("create %s proxy request: %v", siteName, err)
		}
		request.Host = siteName
		response, err := (&http.Client{Timeout: time.Second}).Do(request)
		if err == nil {
			body, readErr := io.ReadAll(response.Body)
			closeErr := response.Body.Close()
			if readErr == nil && closeErr == nil && response.StatusCode == http.StatusOK && strings.Contains(string(body), "cozy backend: "+siteName) {
				return
			}
		}
		if time.Now().After(deadline) {
			t.Fatalf("managed %s backend did not become reachable through %s: %v", siteName, address, err)
		}
		time.Sleep(25 * time.Millisecond)
	}
}

func TestCLILifecycle(t *testing.T) {
	directory := integrationDirectory(t)
	cozy := filepath.Join(directory, "cozy")
	backend := filepath.Join(directory, "backend")
	buildBinary(t, cozy, "./cmd/cozy")
	buildBinary(t, backend, "./testdata/backend")

	stateDirectory := filepath.Join(directory, "runtime")
	configuration := writeConfiguration(t, directory, backend)
	address := availableAddress(t)
	common := []string{"--config", configuration, "--listen", address, "--state-dir", stateDirectory}

	if output, err := runBinary(t, cozy, append([]string{"check"}, common...)...); err != nil {
		t.Fatalf("cozy check: %v\n%s", err, output)
	}
	if output, err := runBinary(t, cozy, append([]string{"up"}, common...)...); err != nil {
		t.Fatalf("cozy up: %v\n%s", err, output)
	}
	t.Cleanup(func() {
		if output, err := runBinary(t, cozy, "down", "--state-dir", stateDirectory); err != nil {
			t.Errorf("cozy down: %v\n%s", err, output)
		}
	})

	status, err := runBinary(t, cozy, "status", "--state-dir", stateDirectory)
	if err != nil {
		t.Fatalf("cozy status: %v\n%s", err, status)
	}
	for _, siteName := range []string{"fishy.localhost", "agtask.localhost"} {
		if !strings.Contains(status, "http://"+siteName) {
			t.Fatalf("status does not contain the clean %s URL: %s", siteName, status)
		}
	}

	for _, siteName := range []string{"fishy.localhost", "agtask.localhost"} {
		requireReachableSite(t, address, siteName)

		logs, err := runBinary(t, cozy, "logs", "--state-dir", stateDirectory, siteName)
		if err != nil {
			t.Fatalf("cozy logs %s: %v\n%s", siteName, err, logs)
		}
		if !strings.Contains(logs, "cozy test backend ready") {
			t.Fatalf("%s output was not captured: %s", siteName, logs)
		}
	}
}

func TestCLIRefreshAndRestart(t *testing.T) {
	directory := integrationDirectory(t)
	cozy := filepath.Join(directory, "cozy")
	backend := filepath.Join(directory, "backend")
	buildBinary(t, cozy, "./cmd/cozy")
	buildBinary(t, backend, "./testdata/backend")

	stateDirectory := filepath.Join(directory, "runtime")
	configuration := writeConfiguration(t, directory, backend)
	address := availableAddress(t)
	if output, err := runBinary(t, cozy, "up", "--config", configuration, "--listen", address, "--state-dir", stateDirectory); err != nil {
		t.Fatalf("start refresh integration supervisor: %v\n%s", err, output)
	}
	t.Cleanup(func() {
		if output, err := runBinary(t, cozy, "down", "--state-dir", stateDirectory); err != nil {
			t.Errorf("stop refresh integration supervisor: %v\n%s", err, output)
		}
	})

	before := readRuntimeSnapshot(t, stateDirectory)
	oldFishy, ok := before.site("fishy.localhost")
	if !ok {
		t.Fatal("initial runtime state is missing fishy.localhost")
	}
	oldAGTask, ok := before.site("agtask.localhost")
	if !ok {
		t.Fatal("initial runtime state is missing agtask.localhost")
	}

	if output, err := runBinary(t, cozy, "restart", "--state-dir", stateDirectory, "agtask.localhost"); err != nil {
		t.Fatalf("restart agtask.localhost: %v\n%s", err, output)
	}
	afterRestart := readRuntimeSnapshot(t, stateDirectory)
	newFishy, ok := afterRestart.site("fishy.localhost")
	if !ok || newFishy.PID != oldFishy.PID {
		t.Fatalf("targeted restart interrupted fishy.localhost: old PID %d, new PID %d", oldFishy.PID, newFishy.PID)
	}
	newAGTask, ok := afterRestart.site("agtask.localhost")
	if !ok || newAGTask.PID == oldAGTask.PID {
		t.Fatalf("targeted restart did not replace agtask.localhost: old PID %d, new PID %d", oldAGTask.PID, newAGTask.PID)
	}
	if afterRestart.PID != before.PID {
		t.Fatalf("targeted restart replaced the supervisor: old PID %d, new PID %d", before.PID, afterRestart.PID)
	}
	requireReachableSite(t, address, "fishy.localhost")
	requireReachableSite(t, address, "agtask.localhost")

	if output, err := runBinary(t, cozy, "refresh", "--state-dir", stateDirectory); err != nil {
		t.Fatalf("refresh unchanged configuration: %v\n%s", err, output)
	}
	unchanged := readRuntimeSnapshot(t, stateDirectory)
	unchangedFishy, ok := unchanged.site("fishy.localhost")
	if !ok || unchangedFishy.PID != newFishy.PID {
		t.Fatalf("refresh restarted unchanged fishy.localhost: old PID %d, new PID %d", newFishy.PID, unchangedFishy.PID)
	}
	unchangedAGTask, ok := unchanged.site("agtask.localhost")
	if !ok || unchangedAGTask.PID != newAGTask.PID {
		t.Fatalf("refresh restarted unchanged agtask.localhost: old PID %d, new PID %d", newAGTask.PID, unchangedAGTask.PID)
	}

	writeConfigurationSites(t, configuration, backend, "fishy.localhost", "agtask.localhost", "garden.localhost")
	if output, err := runBinary(t, cozy, "refresh", "--state-dir", stateDirectory); err != nil {
		t.Fatalf("refresh added garden.localhost: %v\n%s", err, output)
	}
	withGarden := readRuntimeSnapshot(t, stateDirectory)
	if withGarden.PID != before.PID {
		t.Fatal("configuration refresh replaced the running supervisor")
	}
	if site, ok := withGarden.site("fishy.localhost"); !ok || site.PID != oldFishy.PID {
		t.Fatal("configuration refresh interrupted the unchanged Fishy site")
	}
	if _, ok := withGarden.site("garden.localhost"); !ok {
		t.Fatal("configuration refresh did not start the added garden.localhost site")
	}
	requireReachableSite(t, address, "garden.localhost")

	writeConfigurationSites(t, configuration, backend, "fishy.localhost", "agtask.localhost")
	if err := syscall.Kill(before.PID, syscall.SIGHUP); err != nil {
		t.Fatalf("send supervisor configuration refresh signal: %v", err)
	}
	deadline := time.Now().Add(5 * time.Second)
	for {
		state := readRuntimeSnapshot(t, stateDirectory)
		if _, exists := state.site("garden.localhost"); !exists {
			if state.PID != before.PID {
				t.Fatal("SIGHUP replaced the running supervisor")
			}
			if site, ok := state.site("fishy.localhost"); !ok || site.PID != oldFishy.PID {
				t.Fatal("SIGHUP interrupted the unchanged Fishy site")
			}
			break
		}
		if time.Now().After(deadline) {
			t.Fatal("SIGHUP did not refresh the updated configuration")
		}
		time.Sleep(25 * time.Millisecond)
	}
	requireReachableSite(t, address, "fishy.localhost")
	requireReachableSite(t, address, "agtask.localhost")

	if output, err := runBinary(t, cozy, "restart", "--state-dir", stateDirectory, "missing.localhost"); err == nil {
		t.Fatalf("restart unexpectedly accepted an unconfigured site: %s", output)
	}
	requireReachableSite(t, address, "fishy.localhost")
}

func TestCLIReportsListenerConflict(t *testing.T) {
	directory := t.TempDir()
	cozy := filepath.Join(directory, "cozy")
	backend := filepath.Join(directory, "backend")
	buildBinary(t, cozy, "./cmd/cozy")
	buildBinary(t, backend, "./testdata/backend")
	configuration := writeConfiguration(t, directory, backend)

	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("bind conflict listener: %v", err)
	}
	t.Cleanup(func() {
		if err := listener.Close(); err != nil {
			t.Errorf("close conflict listener: %v", err)
		}
	})

	output, err := runBinary(t, cozy, "up", "--config", configuration, "--listen", listener.Addr().String(), "--state-dir", filepath.Join(directory, "runtime"))
	if err == nil {
		t.Fatalf("expected occupied listener to fail; output: %s", output)
	}
	if !strings.Contains(strings.ToLower(output), "address") && !strings.Contains(strings.ToLower(output), "listener") && !strings.Contains(strings.ToLower(output), "use") {
		t.Fatalf("listener conflict did not produce an actionable diagnostic: %s", output)
	}
}
