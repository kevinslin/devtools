// Package service starts and supervises Cozy's local HTTP services.
package service

import (
	"context"
	"crypto/rand"
	"crypto/subtle"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"time"

	"cozy/internal/admin"
	"cozy/internal/config"
)

const (
	defaultProxyAddress = "127.0.0.1:8080"
	adminHostname       = "cozy.localhost"
)

var _ admin.Backend = (*Manager)(nil)

// Options configures the local proxy and runtime metadata.
type Options struct {
	Addr       string
	StateDir   string
	ConfigPath string
}

// ControlResult is the response from an authenticated live control action.
type ControlResult struct {
	Message string `json:"message"`
}

type controlRequest struct {
	Token  string `json:"token"`
	Action string `json:"action"`
	Site   string `json:"site,omitempty"`
}

type controlResponse struct {
	Message string `json:"message,omitempty"`
	Error   string `json:"error,omitempty"`
}

// SiteState is the persisted runtime information for a site.
type SiteState struct {
	Name    string `json:"name"`
	URL     string `json:"url"`
	Run     string `json:"run"`
	PID     int    `json:"pid"`
	Port    int    `json:"port"`
	LogPath string `json:"log_path"`
}

// State is the persisted runtime information for the proxy and its sites.
type State struct {
	PID         int         `json:"pid"`
	Addr        string      `json:"addr"`
	Token       string      `json:"token"`
	ControlPath string      `json:"control_path"`
	Sites       []SiteState `json:"sites"`
}

type child struct {
	cmd         *exec.Cmd
	log         *os.File
	done        chan struct{}
	exit        chan childExit
	generation  uint64
	intentional atomic.Bool
}

type childExit struct {
	name       string
	generation uint64
	err        error
}

// Manager owns a proxy listener and all child processes started for it.
type Manager struct {
	mu          sync.RWMutex
	mutationMu  sync.Mutex
	state       State
	stateDir    string
	configPath  string
	server      *http.Server
	listener    net.Listener
	control     net.Listener
	controlInfo os.FileInfo
	children    map[string]*child
	routes      map[string]*httputil.ReverseProxy
	generation  atomic.Uint64
	childExit   chan childExit
	serveErr    chan error
	stopCh      chan struct{}
	stopping    bool
	stopOnce    sync.Once
	stopErr     error
}

// DefaultStateDir resolves the platform's user application-support directory.
func DefaultStateDir() (string, error) {
	dir, err := os.UserConfigDir()
	if err != nil {
		return "", fmt.Errorf("resolve user application support directory: %w", err)
	}
	return filepath.Join(dir, "cozy"), nil
}

// LoadState reads persisted proxy and child-process metadata.
func LoadState(dir string) (State, error) {
	var state State
	file, err := os.Open(filepath.Join(dir, "state.json"))
	if err != nil {
		return state, fmt.Errorf("open Cozy runtime state: %w", err)
	}
	defer file.Close()
	if err := json.NewDecoder(file).Decode(&state); err != nil {
		return State{}, fmt.Errorf("decode Cozy runtime state: %w", err)
	}
	return state, nil
}

// OwnsState verifies that a live Cozy manager proves ownership of its state.
func OwnsState(state State) bool {
	if state.PID <= 0 || len(state.Token) != 64 || state.ControlPath == "" ||
		!filepath.IsAbs(state.ControlPath) ||
		filepath.Clean(state.ControlPath) != state.ControlPath ||
		filepath.Base(state.ControlPath) != "control.sock" {
		return false
	}
	if _, err := hex.DecodeString(state.Token); err != nil {
		return false
	}
	if err := syscall.Kill(state.PID, 0); err != nil && !errors.Is(err, syscall.EPERM) {
		return false
	}
	dirInfo, err := os.Stat(filepath.Dir(state.ControlPath))
	if err != nil || !dirInfo.IsDir() || dirInfo.Mode().Perm()&0o077 != 0 {
		return false
	}
	socketInfo, err := os.Lstat(state.ControlPath)
	if err != nil || socketInfo.Mode()&os.ModeSocket == 0 || socketInfo.Mode().Perm()&0o077 != 0 {
		return false
	}
	conn, err := net.DialTimeout("unix", state.ControlPath, 300*time.Millisecond)
	if err != nil {
		return false
	}
	defer conn.Close()
	if err := conn.SetReadDeadline(time.Now().Add(300 * time.Millisecond)); err != nil {
		return false
	}
	reply := make([]byte, len(state.Token))
	if _, err := io.ReadFull(conn, reply); err != nil {
		return false
	}
	return subtle.ConstantTimeCompare(reply, []byte(state.Token)) == 1
}

// Request authenticates and sends a bounded live action to a running manager.
func Request(ctx context.Context, state State, action, site string) (ControlResult, error) {
	var result ControlResult
	if !OwnsState(state) {
		return result, fmt.Errorf("Cozy runtime state is stale or could not be authenticated")
	}
	var dialer net.Dialer
	conn, err := dialer.DialContext(ctx, "unix", state.ControlPath)
	if err != nil {
		return result, fmt.Errorf("connect to authenticated Cozy control socket: %w", err)
	}
	defer conn.Close()
	deadline := time.Now().Add(30 * time.Second)
	if ctxDeadline, ok := ctx.Deadline(); ok && ctxDeadline.Before(deadline) {
		deadline = ctxDeadline
	}
	if err := conn.SetDeadline(deadline); err != nil {
		return result, fmt.Errorf("set Cozy control request deadline: %w", err)
	}
	token := make([]byte, len(state.Token))
	if _, err := io.ReadFull(conn, token); err != nil {
		return result, fmt.Errorf("read Cozy control authentication: %w", err)
	}
	if subtle.ConstantTimeCompare(token, []byte(state.Token)) != 1 {
		return result, fmt.Errorf("Cozy control authentication failed")
	}
	if err := json.NewEncoder(conn).Encode(controlRequest{
		Token: state.Token, Action: action, Site: site,
	}); err != nil {
		return result, fmt.Errorf("send Cozy %s control request: %w", action, err)
	}
	var response controlResponse
	if err := json.NewDecoder(io.LimitReader(conn, 64<<10)).Decode(&response); err != nil {
		return result, fmt.Errorf("read Cozy %s control response: %w", action, err)
	}
	if response.Error != "" {
		return result, errors.New(response.Error)
	}
	result.Message = response.Message
	return result, nil
}

// State returns a copy of this manager's runtime metadata.
func (m *Manager) State() State {
	m.mu.RLock()
	defer m.mu.RUnlock()
	state := m.state
	state.Sites = append([]SiteState(nil), state.Sites...)
	return state
}

// Sites returns only the public, non-sensitive metadata for managed sites.
func (m *Manager) Sites() []admin.Site {
	state := m.State()
	sites := make([]admin.Site, 0, len(state.Sites))
	for _, site := range state.Sites {
		sites = append(sites, admin.Site{
			Name: site.Name, URL: site.URL, Run: site.Run,
			PID: site.PID, Port: site.Port, LogPath: site.LogPath,
		})
	}
	return sites
}

func (m *Manager) lockMutation(ctx context.Context) error {
	if err := ctx.Err(); err != nil {
		return fmt.Errorf("wait for Cozy site operation: %w", err)
	}
	for !m.mutationMu.TryLock() {
		timer := time.NewTimer(10 * time.Millisecond)
		select {
		case <-ctx.Done():
			if !timer.Stop() {
				<-timer.C
			}
			return fmt.Errorf("wait for Cozy site operation: %w", ctx.Err())
		case <-timer.C:
		}
	}
	if err := ctx.Err(); err != nil {
		m.mutationMu.Unlock()
		return fmt.Errorf("start Cozy site operation: %w", err)
	}
	return nil
}

// RestartSite replaces one ready site without interrupting the proxy or peers.
func (m *Manager) RestartSite(ctx context.Context, name string) error {
	if name == "" {
		return fmt.Errorf("restart requires a configured site hostname")
	}
	if err := m.lockMutation(ctx); err != nil {
		return err
	}
	defer m.mutationMu.Unlock()
	if _, err := m.controlActionLocked("restart", name); err != nil {
		return fmt.Errorf("restart site %s: %w", name, err)
	}
	return nil
}

// AddSite persists and starts a validated new site as one rollback-safe change.
func (m *Manager) AddSite(ctx context.Context, input admin.Site) error {
	if input.PID != 0 || input.Port != 0 || input.LogPath != "" {
		return fmt.Errorf("runtime metadata cannot be specified when adding a site")
	}
	site := config.Site{Name: input.Name, URL: input.URL, Run: input.Run}
	if site.URL == "" {
		site.URL = "http://" + site.Name
	}
	if site.Name == adminHostname {
		return fmt.Errorf("site %q is reserved for the Cozy admin", adminHostname)
	}
	if err := (config.Config{Version: 1, Sites: []config.Site{site}}).Validate(); err != nil {
		return fmt.Errorf("validate new site: %w", err)
	}
	if err := m.lockMutation(ctx); err != nil {
		return err
	}
	defer m.mutationMu.Unlock()
	m.mu.RLock()
	path := m.configPath
	stopping := m.stopping
	m.mu.RUnlock()
	if stopping {
		return fmt.Errorf("Cozy is shutting down")
	}
	if path == "" {
		return fmt.Errorf("configuration path is unavailable; start Cozy with a configuration file before adding a site")
	}
	original, err := os.ReadFile(path)
	if err != nil {
		return fmt.Errorf("read configuration before adding %s: %w", site.Name, err)
	}
	if err := config.AppendSite(path, site); err != nil {
		return fmt.Errorf("persist new site %s: %w", site.Name, err)
	}
	rollback := func(reason error) error {
		if err := config.WriteAtomic(path, original); err != nil {
			return fmt.Errorf("add site %s failed: %v; restore original configuration: %w", site.Name, reason, err)
		}
		return fmt.Errorf("add site %s and restore original configuration: %w", site.Name, reason)
	}
	if err := ctx.Err(); err != nil {
		return rollback(err)
	}
	cfg, err := config.Load(path)
	if err != nil {
		return rollback(fmt.Errorf("reload updated configuration: %w", err))
	}
	if _, err := m.reconcile(cfg, nil, true); err != nil {
		return rollback(err)
	}
	return nil
}

// Start binds the proxy and transactionally starts all configured services.
func Start(cfg config.Config, opts Options) (_ *Manager, resultErr error) {
	if err := cfg.Validate(); err != nil {
		return nil, fmt.Errorf("validate Cozy configuration: %w", err)
	}
	if opts.Addr == "" {
		opts.Addr = defaultProxyAddress
	}
	tcpAddr, err := net.ResolveTCPAddr("tcp", opts.Addr)
	if err != nil {
		return nil, fmt.Errorf("resolve Cozy loopback proxy address %q: %w", opts.Addr, err)
	}
	if tcpAddr.IP == nil || !tcpAddr.IP.IsLoopback() {
		return nil, fmt.Errorf("Cozy proxy address %q must bind exclusively to a loopback IP; choose 127.0.0.1 or localhost", opts.Addr)
	}
	if opts.StateDir == "" {
		var err error
		opts.StateDir, err = DefaultStateDir()
		if err != nil {
			return nil, err
		}
	}
	if err := os.MkdirAll(opts.StateDir, 0o700); err != nil {
		return nil, fmt.Errorf("create Cozy runtime directory: %w", err)
	}
	if existing, err := LoadState(opts.StateDir); err == nil {
		if OwnsState(existing) {
			return nil, fmt.Errorf("Cozy is already running as process %d; run cozy down first", existing.PID)
		}
	} else if !errors.Is(err, os.ErrNotExist) {
		return nil, err
	}

	listener, err := net.Listen("tcp", opts.Addr)
	if err != nil {
		if errors.Is(err, syscall.EACCES) || errors.Is(err, syscall.EPERM) {
			return nil, fmt.Errorf("cannot bind Cozy proxy to %s: permission denied; choose a permitted proxy address or explicitly grant access: %w", opts.Addr, err)
		}
		if errors.Is(err, syscall.EADDRINUSE) {
			return nil, fmt.Errorf("cannot bind Cozy proxy to %s: the port is already in use; stop its current listener or choose another proxy address: %w", opts.Addr, err)
		}
		return nil, fmt.Errorf("bind Cozy proxy to %s: %w", opts.Addr, err)
	}

	m := &Manager{
		state:      State{PID: os.Getpid(), Addr: listener.Addr().String(), Sites: make([]SiteState, 0, len(cfg.Sites))},
		stateDir:   opts.StateDir,
		configPath: opts.ConfigPath,
		listener:   listener,
		children:   make(map[string]*child, len(cfg.Sites)),
		routes:     make(map[string]*httputil.ReverseProxy, len(cfg.Sites)),
		childExit:  make(chan childExit, 256),
		serveErr:   make(chan error, 1),
		stopCh:     make(chan struct{}),
	}
	defer func() {
		if resultErr != nil {
			ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
			defer cancel()
			_ = m.Shutdown(ctx)
		}
	}()

	if err := m.startControl(); err != nil {
		return nil, err
	}

	for _, site := range cfg.Sites {
		process, siteState, proxy, err := m.startSite(site)
		if err != nil {
			return nil, err
		}
		m.mu.Lock()
		m.children[site.Name] = process
		m.routes[strings.ToLower(site.Name)] = proxy
		m.state.Sites = append(m.state.Sites, siteState)
		m.mu.Unlock()
	}

	adminHandler := admin.New(m)
	m.server = &http.Server{Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		host := r.Host
		if withoutPort, _, err := net.SplitHostPort(host); err == nil {
			host = withoutPort
		}
		if strings.EqualFold(host, adminHostname) {
			adminHandler.ServeHTTP(w, r)
			return
		}
		m.mu.RLock()
		proxy, ok := m.routes[strings.ToLower(host)]
		m.mu.RUnlock()
		if !ok {
			http.NotFound(w, r)
			return
		}
		proxy.ServeHTTP(w, r)
	})}
	if err := persistState(opts.StateDir, m.State()); err != nil {
		return nil, err
	}
	go func() {
		err := m.server.Serve(listener)
		if err != nil && !errors.Is(err, http.ErrServerClosed) {
			m.serveErr <- err
		}
	}()
	return m, nil
}

func (m *Manager) startSite(site config.Site) (*child, SiteState, *httputil.ReverseProxy, error) {
	var empty SiteState
	reservation, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return nil, empty, nil, fmt.Errorf("allocate loopback port for %s: %w", site.Name, err)
	}
	port := reservation.Addr().(*net.TCPAddr).Port
	if err := reservation.Close(); err != nil {
		return nil, empty, nil, fmt.Errorf("release loopback port for %s: %w", site.Name, err)
	}
	parsed, err := url.Parse(site.URL)
	if err != nil || parsed.Hostname() == "" {
		return nil, empty, nil, fmt.Errorf("parse site URL for %s: %q", site.Name, site.URL)
	}
	backend := &url.URL{Scheme: "http", Host: net.JoinHostPort("127.0.0.1", strconv.Itoa(port))}
	logPath := filepath.Join(m.stateDir, site.Name+".log")
	log, err := os.OpenFile(logPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o600)
	if err != nil {
		return nil, empty, nil, fmt.Errorf("open log for %s: %w", site.Name, err)
	}
	cmd := exec.Command("sh", "-c", site.Run)
	cmd.Env = append(os.Environ(), "PORT="+strconv.Itoa(port), "COZY_PORT="+strconv.Itoa(port))
	cmd.Stdout = log
	cmd.Stderr = log
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	if err := cmd.Start(); err != nil {
		_ = log.Close()
		return nil, empty, nil, fmt.Errorf("start service %s: %w", site.Name, err)
	}
	process := &child{
		cmd: cmd, log: log, done: make(chan struct{}),
		exit:       make(chan childExit, 1),
		generation: m.generation.Add(1),
	}
	siteState := SiteState{
		Name: site.Name, URL: site.URL, Run: site.Run,
		PID: cmd.Process.Pid, Port: port, LogPath: logPath,
	}
	go func() {
		err := cmd.Wait()
		_ = log.Close()
		exit := childExit{name: site.Name, generation: process.generation, err: err}
		process.exit <- exit
		close(process.done)
		if !process.intentional.Load() {
			select {
			case m.childExit <- exit:
			case <-m.stopCh:
			}
		}
	}()
	if err := m.waitForBackend(process, site.Name, backend.Host, logPath); err != nil {
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()
		_ = stopChild(ctx, process)
		return nil, empty, nil, err
	}
	return process, siteState, httputil.NewSingleHostReverseProxy(backend), nil
}

func stopChild(ctx context.Context, process *child) error {
	if process == nil {
		return nil
	}
	process.intentional.Store(true)
	if err := syscall.Kill(-process.cmd.Process.Pid, syscall.SIGTERM); err != nil && !errors.Is(err, syscall.ESRCH) {
		return fmt.Errorf("terminate Cozy service process %d: %w", process.cmd.Process.Pid, err)
	}
	select {
	case <-process.done:
		return nil
	case <-ctx.Done():
		if err := syscall.Kill(-process.cmd.Process.Pid, syscall.SIGKILL); err != nil && !errors.Is(err, syscall.ESRCH) {
			return fmt.Errorf("kill Cozy service process %d: %w", process.cmd.Process.Pid, err)
		}
		select {
		case <-process.done:
		case <-time.After(time.Second):
		}
		return fmt.Errorf("Cozy service shutdown timed out: %w", ctx.Err())
	}
}

func (m *Manager) startControl() error {
	controlPath := filepath.Join(m.stateDir, "control.sock")
	if len(controlPath) >= len(syscall.RawSockaddrUnix{}.Path) {
		return fmt.Errorf("Cozy runtime directory path is too long for the Unix control socket; choose a shorter state directory: %s", m.stateDir)
	}
	if info, err := os.Lstat(controlPath); err == nil {
		if info.Mode()&os.ModeSocket == 0 {
			return fmt.Errorf("Cozy control path %s exists and is not a Unix socket", controlPath)
		}
		conn, dialErr := net.DialTimeout("unix", controlPath, 200*time.Millisecond)
		if dialErr == nil {
			_ = conn.Close()
			return fmt.Errorf("Cozy control socket %s is already active; inspect or stop its owner", controlPath)
		}
		if err := os.Remove(controlPath); err != nil {
			return fmt.Errorf("remove stale Cozy control socket %s: %w", controlPath, err)
		}
	} else if !errors.Is(err, os.ErrNotExist) {
		return fmt.Errorf("inspect Cozy control socket %s: %w", controlPath, err)
	}
	token := make([]byte, 32)
	if _, err := rand.Read(token); err != nil {
		return fmt.Errorf("generate Cozy state ownership token: %w", err)
	}
	control, err := net.Listen("unix", controlPath)
	if err != nil {
		return fmt.Errorf("bind private Cozy control socket: %w", err)
	}
	if unixControl, ok := control.(*net.UnixListener); ok {
		unixControl.SetUnlinkOnClose(false)
	}
	if err := os.Chmod(controlPath, 0o600); err != nil {
		_ = control.Close()
		_ = os.Remove(controlPath)
		return fmt.Errorf("protect private Cozy control socket: %w", err)
	}
	info, err := os.Lstat(controlPath)
	if err != nil {
		_ = control.Close()
		_ = os.Remove(controlPath)
		return fmt.Errorf("inspect private Cozy control socket: %w", err)
	}
	m.control = control
	m.controlInfo = info
	m.state.Token = hex.EncodeToString(token)
	m.state.ControlPath = controlPath
	go func() {
		for {
			conn, err := control.Accept()
			if err != nil {
				return
			}
			go m.handleControl(conn)
		}
	}()
	return nil
}

func (m *Manager) handleControl(conn net.Conn) {
	defer conn.Close()
	if err := conn.SetWriteDeadline(time.Now().Add(time.Second)); err != nil {
		return
	}
	m.mu.RLock()
	token := m.state.Token
	m.mu.RUnlock()
	if _, err := io.WriteString(conn, token); err != nil {
		return
	}
	if err := conn.SetReadDeadline(time.Now().Add(2 * time.Second)); err != nil {
		return
	}
	var request controlRequest
	if err := json.NewDecoder(io.LimitReader(conn, 16<<10)).Decode(&request); err != nil {
		return
	}
	if err := conn.SetReadDeadline(time.Time{}); err != nil {
		return
	}
	if err := conn.SetWriteDeadline(time.Now().Add(30 * time.Second)); err != nil {
		return
	}
	if subtle.ConstantTimeCompare([]byte(request.Token), []byte(token)) != 1 {
		_ = json.NewEncoder(conn).Encode(controlResponse{Error: "Cozy control authentication failed"})
		return
	}
	result, err := m.controlAction(request.Action, request.Site)
	response := controlResponse{Message: result.Message}
	if err != nil {
		response.Message = ""
		response.Error = err.Error()
	}
	_ = json.NewEncoder(conn).Encode(response)
}

func (m *Manager) controlAction(action, site string) (ControlResult, error) {
	m.mutationMu.Lock()
	defer m.mutationMu.Unlock()
	return m.controlActionLocked(action, site)
}

func (m *Manager) controlActionLocked(action, site string) (ControlResult, error) {
	m.mu.RLock()
	stopping := m.stopping
	state := m.state
	state.Sites = append([]SiteState(nil), state.Sites...)
	configPath := m.configPath
	m.mu.RUnlock()
	if stopping {
		return ControlResult{}, fmt.Errorf("Cozy is shutting down")
	}
	switch action {
	case "refresh":
		if site != "" {
			return ControlResult{}, fmt.Errorf("refresh does not accept an individual site")
		}
		if configPath == "" {
			return ControlResult{}, fmt.Errorf("configuration path is unavailable; start Cozy with a configuration file before refreshing")
		}
		cfg, err := config.Load(configPath)
		if err != nil {
			return ControlResult{}, fmt.Errorf("reload Cozy configuration: %w", err)
		}
		return m.reconcile(cfg, nil, true)
	case "restart":
		cfg := config.Config{Version: 1, Sites: make([]config.Site, 0, len(state.Sites))}
		restart := make(map[string]bool, len(state.Sites))
		for _, existing := range state.Sites {
			cfg.Sites = append(cfg.Sites, config.Site{
				Name: existing.Name, URL: existing.URL, Run: existing.Run,
			})
			if site == "" || site == existing.Name {
				restart[existing.Name] = true
			}
		}
		if site != "" && !restart[site] {
			return ControlResult{}, fmt.Errorf("unknown configured site %q", site)
		}
		return m.reconcile(cfg, restart, false)
	default:
		return ControlResult{}, fmt.Errorf("unknown Cozy control action %q", action)
	}
}

type stagedSite struct {
	process *child
	state   SiteState
	proxy   *httputil.ReverseProxy
}

func (m *Manager) reconcile(cfg config.Config, restart map[string]bool, refresh bool) (ControlResult, error) {
	if err := cfg.Validate(); err != nil {
		return ControlResult{}, fmt.Errorf("validate Cozy configuration: %w", err)
	}
	current := m.State()
	m.mu.RLock()
	currentChildren := make(map[string]*child, len(m.children))
	currentRoutes := make(map[string]*httputil.ReverseProxy, len(m.routes))
	for name, process := range m.children {
		currentChildren[name] = process
	}
	for name, proxy := range m.routes {
		currentRoutes[name] = proxy
	}
	m.mu.RUnlock()
	byName := make(map[string]SiteState, len(current.Sites))
	for _, existing := range current.Sites {
		byName[existing.Name] = existing
	}
	staged := make(map[string]stagedSite, len(cfg.Sites))
	cleanupStaged := func() {
		for _, candidate := range staged {
			ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
			_ = stopChild(ctx, candidate.process)
			cancel()
		}
	}
	added, changed, unchanged := 0, 0, 0
	for _, site := range cfg.Sites {
		existing, exists := byName[site.Name]
		if exists && !restart[site.Name] && existing.URL == site.URL && existing.Run == site.Run {
			unchanged++
			continue
		}
		process, state, proxy, err := m.startSite(site)
		if err != nil {
			cleanupStaged()
			return ControlResult{}, fmt.Errorf("prepare service %s without disrupting running sites: %w", site.Name, err)
		}
		staged[site.Name] = stagedSite{process: process, state: state, proxy: proxy}
		if exists {
			changed++
		} else {
			added++
		}
	}
	next := current
	next.Sites = make([]SiteState, 0, len(cfg.Sites))
	nextChildren := make(map[string]*child, len(cfg.Sites))
	nextRoutes := make(map[string]*httputil.ReverseProxy, len(cfg.Sites))
	for _, site := range cfg.Sites {
		if candidate, ok := staged[site.Name]; ok {
			select {
			case <-candidate.process.done:
				cleanupStaged()
				return ControlResult{}, fmt.Errorf("replacement service %s exited before activation; inspect %s", site.Name, candidate.state.LogPath)
			default:
			}
			next.Sites = append(next.Sites, candidate.state)
			nextChildren[site.Name] = candidate.process
			nextRoutes[strings.ToLower(site.Name)] = candidate.proxy
			continue
		}
		next.Sites = append(next.Sites, byName[site.Name])
		nextChildren[site.Name] = currentChildren[site.Name]
		nextRoutes[strings.ToLower(site.Name)] = currentRoutes[strings.ToLower(site.Name)]
	}
	if err := persistState(m.stateDir, next); err != nil {
		cleanupStaged()
		return ControlResult{}, fmt.Errorf("persist updated Cozy runtime without disrupting running sites: %w", err)
	}
	oldProcesses := make([]*child, 0, len(currentChildren))
	m.mu.Lock()
	for name, candidate := range staged {
		select {
		case <-candidate.process.done:
			m.mu.Unlock()
			restoreErr := persistState(m.stateDir, current)
			cleanupStaged()
			if restoreErr != nil {
				return ControlResult{}, fmt.Errorf(
					"replacement service %s exited before activation and restoring running state failed: %w; inspect %s",
					name, restoreErr, candidate.state.LogPath,
				)
			}
			return ControlResult{}, fmt.Errorf(
				"replacement service %s exited before activation; inspect %s",
				name, candidate.state.LogPath,
			)
		default:
		}
	}
	for name, process := range currentChildren {
		if replacement, exists := nextChildren[name]; !exists || replacement != process {
			process.intentional.Store(true)
			oldProcesses = append(oldProcesses, process)
		}
	}
	m.state = next
	m.children = nextChildren
	m.routes = nextRoutes
	m.mu.Unlock()
	for _, process := range oldProcesses {
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		err := stopChild(ctx, process)
		cancel()
		if err != nil {
			return ControlResult{}, fmt.Errorf("activated updated services but could not stop the replaced process: %w", err)
		}
	}
	if refresh {
		removed := len(current.Sites) - unchanged - changed
		return ControlResult{Message: fmt.Sprintf(
			"refreshed configuration: %d added, %d changed, %d removed, %d unchanged",
			added, changed, removed, unchanged,
		)}, nil
	}
	if len(restart) == 1 {
		for name := range restart {
			return ControlResult{Message: "restarted " + name}, nil
		}
	}
	return ControlResult{Message: fmt.Sprintf("restarted %d sites", len(restart))}, nil
}

func (m *Manager) waitForBackend(process *child, name, addr, logPath string) error {
	deadline := time.NewTimer(3 * time.Second)
	defer deadline.Stop()
	ticker := time.NewTicker(20 * time.Millisecond)
	defer ticker.Stop()
	for {
		select {
		case exit := <-process.exit:
			return m.startupExitError(exit, logPath)
		case <-deadline.C:
			return fmt.Errorf("service %s did not bind its assigned loopback port within 3 seconds; inspect %s", name, logPath)
		default:
		}
		conn, err := net.DialTimeout("tcp", addr, 100*time.Millisecond)
		if err == nil {
			_ = conn.Close()
			return nil
		}
		select {
		case exit := <-process.exit:
			return m.startupExitError(exit, logPath)
		case <-deadline.C:
			return fmt.Errorf("service %s did not bind its assigned loopback port within 3 seconds; inspect %s", name, logPath)
		case <-ticker.C:
		}
	}
}

func (m *Manager) startupExitError(exit childExit, fallbackLogPath string) error {
	logPath := fallbackLogPath
	m.mu.RLock()
	for _, site := range m.state.Sites {
		if site.Name == exit.name {
			logPath = site.LogPath
			break
		}
	}
	m.mu.RUnlock()
	if exit.err != nil {
		return fmt.Errorf("service %s exited before its backend was ready: %w; inspect %s", exit.name, exit.err, logPath)
	}
	return fmt.Errorf("service %s exited before its backend was ready; inspect %s", exit.name, logPath)
}

func persistState(dir string, state State) error {
	file, err := os.CreateTemp(dir, ".state-*.json")
	if err != nil {
		return fmt.Errorf("create Cozy runtime state: %w", err)
	}
	path := file.Name()
	defer os.Remove(path)
	if err := file.Chmod(0o600); err != nil {
		_ = file.Close()
		return fmt.Errorf("protect Cozy runtime state: %w", err)
	}
	encoder := json.NewEncoder(file)
	encoder.SetIndent("", "  ")
	if err := encoder.Encode(state); err != nil {
		_ = file.Close()
		return fmt.Errorf("encode Cozy runtime state: %w", err)
	}
	if err := file.Sync(); err != nil {
		_ = file.Close()
		return fmt.Errorf("sync Cozy runtime state: %w", err)
	}
	if err := file.Close(); err != nil {
		return fmt.Errorf("close Cozy runtime state: %w", err)
	}
	if err := os.Rename(path, filepath.Join(dir, "state.json")); err != nil {
		return fmt.Errorf("publish Cozy runtime state: %w", err)
	}
	return nil
}

// Wait supervises the proxy until cancellation or an unexpected child exit.
func (m *Manager) Wait(ctx context.Context) error {
	for {
		select {
		case <-ctx.Done():
			shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			return m.Shutdown(shutdownCtx)
		case exit := <-m.childExit:
			m.mu.RLock()
			active := m.children[exit.name]
			current := active != nil && active.generation == exit.generation &&
				!active.intentional.Load()
			m.mu.RUnlock()
			if !current {
				continue
			}
			shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			_ = m.Shutdown(shutdownCtx)
			if exit.err != nil {
				return fmt.Errorf("service %s exited: %w", exit.name, exit.err)
			}
			return fmt.Errorf("service %s exited unexpectedly", exit.name)
		case err := <-m.serveErr:
			shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			_ = m.Shutdown(shutdownCtx)
			return fmt.Errorf("Cozy proxy stopped: %w", err)
		}
	}
}

// Shutdown gracefully closes the proxy, terminates service process groups,
// and removes only runtime state owned by this manager.
func (m *Manager) Shutdown(ctx context.Context) error {
	m.stopOnce.Do(func() {
		m.mutationMu.Lock()
		defer m.mutationMu.Unlock()
		m.mu.Lock()
		m.stopping = true
		current := m.state
		processes := make([]*child, 0, len(m.children))
		for _, process := range m.children {
			process.intentional.Store(true)
			processes = append(processes, process)
		}
		m.mu.Unlock()
		ownsPersistedState := false
		if state, err := LoadState(m.stateDir); err == nil &&
			state.PID == current.PID &&
			state.Addr == current.Addr &&
			state.ControlPath == current.ControlPath &&
			subtle.ConstantTimeCompare([]byte(state.Token), []byte(current.Token)) == 1 {
			ownsPersistedState = OwnsState(state)
		}
		close(m.stopCh)
		if m.server != nil {
			if err := m.server.Shutdown(ctx); err != nil && !errors.Is(err, http.ErrServerClosed) {
				m.stopErr = fmt.Errorf("shut down Cozy proxy: %w", err)
			}
		} else if m.listener != nil {
			if err := m.listener.Close(); err != nil && !errors.Is(err, net.ErrClosed) {
				m.stopErr = fmt.Errorf("close Cozy proxy listener: %w", err)
			}
		}
		for _, process := range processes {
			if err := stopChild(ctx, process); err != nil && m.stopErr == nil {
				m.stopErr = err
			}
		}
		if m.control != nil {
			if err := m.control.Close(); err != nil && !errors.Is(err, net.ErrClosed) && m.stopErr == nil {
				m.stopErr = fmt.Errorf("close private Cozy control socket: %w", err)
			}
			controlPath := filepath.Join(m.stateDir, "control.sock")
			if current.ControlPath == controlPath && m.controlInfo != nil {
				if info, err := os.Lstat(controlPath); err == nil && os.SameFile(info, m.controlInfo) {
					if err := os.Remove(controlPath); err != nil && !errors.Is(err, os.ErrNotExist) && m.stopErr == nil {
						m.stopErr = fmt.Errorf("remove private Cozy control socket: %w", err)
					}
				}
			}
		}
		if ownsPersistedState {
			if err := os.Remove(filepath.Join(m.stateDir, "state.json")); err != nil && !errors.Is(err, os.ErrNotExist) && m.stopErr == nil {
				m.stopErr = fmt.Errorf("remove Cozy runtime state: %w", err)
			}
		}
	})
	return m.stopErr
}
