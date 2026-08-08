package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"net"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"syscall"
	"time"

	"cozy/internal/config"
	"cozy/internal/dashboard"
	"cozy/internal/service"
)

const (
	defaultConfig    = "cozy.yaml"
	defaultListen    = "127.0.0.1:8080"
	startTimeout     = 10 * time.Second
	stopTimeout      = 10 * time.Second
	agtaskExecutable = "/Users/kevinlin/code/skills-public/active/agtask/skills/agtask/scripts/agtask"
)

type commandOptions struct {
	configPath string
	listen     string
	stateDir   string
	site       string
}

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr))
}

func run(args []string, stdout, stderr io.Writer) int {
	if len(args) == 0 {
		usage(stderr)
		return 2
	}
	if args[0] == "__agtask_dashboard" {
		return runAgtaskDashboard(args[1:], stdout, stderr)
	}
	if args[0] == "help" || args[0] == "-h" || args[0] == "--help" {
		usage(stdout)
		return 0
	}

	command := args[0]
	switch command {
	case "up", "down", "status", "logs", "open", "check", "refresh", "restart", "__serve":
	default:
		fmt.Fprintf(stderr, "cozy: unknown command %q\n", command)
		usage(stderr)
		return 2
	}

	opts, err := parseOptions(command, args[1:], stderr)
	if errors.Is(err, flag.ErrHelp) {
		return 0
	}
	if err != nil {
		fmt.Fprintf(stderr, "cozy %s: %v\n", command, err)
		return 2
	}

	switch command {
	case "up":
		err = up(opts, stdout)
	case "down":
		err = down(opts, stdout)
	case "status":
		err = status(opts, stdout)
	case "logs":
		err = logs(opts, stdout)
	case "open":
		err = openSite(opts)
	case "check":
		err = check(opts, stdout)
	case "refresh", "restart":
		err = requestControl(opts, command, stdout)
	case "__serve":
		err = serve(opts)
	}
	if err != nil {
		fmt.Fprintf(stderr, "cozy %s: %v\n", command, err)
		return 1
	}
	return 0
}

func runAgtaskDashboard(args []string, stdout, stderr io.Writer) int {
	if len(args) != 0 {
		fmt.Fprintf(stderr, "cozy __agtask_dashboard: unexpected argument %q\n", args[0])
		return 2
	}

	value, exists := os.LookupEnv("PORT")
	if !exists || value == "" {
		fmt.Fprintln(stderr, "cozy __agtask_dashboard: PORT is not set; Cozy must assign a backend port")
		return 2
	}
	for _, character := range value {
		if character < '0' || character > '9' {
			fmt.Fprintln(stderr, "cozy __agtask_dashboard: PORT must be a decimal port from 1 through 65535")
			return 2
		}
	}
	port, err := strconv.ParseUint(value, 10, 16)
	if err != nil || port == 0 {
		fmt.Fprintln(stderr, "cozy __agtask_dashboard: PORT must be a decimal port from 1 through 65535")
		return 2
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	if err := dashboard.Run(ctx, int(port), agtaskExecutable, stdout, stderr); err != nil {
		if errors.Is(err, context.Canceled) || ctx.Err() != nil {
			return 0
		}
		fmt.Fprintf(stderr, "cozy __agtask_dashboard: run dashboard: %v\n", err)
		return 1
	}
	return 0
}

func usage(output io.Writer) {
	fmt.Fprintln(output, "Usage: cozy <up|down|status|logs|open|check|refresh|restart> [flags] [site]")
	fmt.Fprintln(output, "Live operations: cozy refresh; cozy restart [site]")
	fmt.Fprintln(output, "Flags: --config cozy.yaml --listen 127.0.0.1:8080 --state-dir <directory>")
}

func parseOptions(command string, args []string, stderr io.Writer) (commandOptions, error) {
	flags := flag.NewFlagSet("cozy "+command, flag.ContinueOnError)
	flags.SetOutput(stderr)
	opts := commandOptions{}
	configPath := os.Getenv("COZY_CONFIG")
	if configPath == "" {
		configPath = defaultConfig
	}
	flags.StringVar(&opts.configPath, "config", configPath, "path to cozy.yaml")
	flags.StringVar(&opts.listen, "listen", defaultListen, "loopback proxy listener")
	flags.StringVar(&opts.stateDir, "state-dir", "", "runtime state directory")
	if err := flags.Parse(args); err != nil {
		return commandOptions{}, err
	}
	remaining := flags.Args()
	switch command {
	case "logs", "open":
		if len(remaining) != 1 {
			return commandOptions{}, fmt.Errorf("provide exactly one site name")
		}
		opts.site = remaining[0]
	case "restart":
		if len(remaining) > 1 {
			return commandOptions{}, fmt.Errorf("restart accepts at most one site name")
		}
		if len(remaining) == 1 {
			opts.site = remaining[0]
		}
	default:
		if len(remaining) != 0 {
			return commandOptions{}, fmt.Errorf("unexpected argument %q", remaining[0])
		}
	}
	if opts.stateDir == "" {
		stateDir, err := service.DefaultStateDir()
		if err != nil {
			return commandOptions{}, fmt.Errorf("locate application support directory: %w", err)
		}
		opts.stateDir = stateDir
	}
	return opts, nil
}

func loadConfig(path string) (config.Config, error) {
	cfg, err := config.Load(path)
	if err != nil {
		return config.Config{}, fmt.Errorf("load configuration %q: %w", path, err)
	}
	if err := cfg.Validate(); err != nil {
		return config.Config{}, fmt.Errorf("validate configuration %q: %w", path, err)
	}
	return cfg, nil
}

func up(opts commandOptions, output io.Writer) error {
	if _, err := loadConfig(opts.configPath); err != nil {
		return err
	}
	state, err := service.LoadState(opts.stateDir)
	if err == nil && service.OwnsState(state) {
		return fmt.Errorf("Cozy is already running on %s (PID %d); run cozy down first", state.Addr, state.PID)
	}
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		return fmt.Errorf("read runtime state: %w", err)
	}
	if err := checkListener(opts.listen); err != nil {
		return err
	}
	if err := os.MkdirAll(opts.stateDir, 0o700); err != nil {
		return fmt.Errorf("create runtime state directory: %w", err)
	}
	executable, err := os.Executable()
	if err != nil {
		return fmt.Errorf("locate cozy executable: %w", err)
	}
	configPath, err := filepath.Abs(opts.configPath)
	if err != nil {
		return fmt.Errorf("resolve configuration path: %w", err)
	}
	stateDir, err := filepath.Abs(opts.stateDir)
	if err != nil {
		return fmt.Errorf("resolve runtime state directory: %w", err)
	}
	logPath := filepath.Join(stateDir, "cozy.log")
	logFile, err := os.OpenFile(logPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o600)
	if err != nil {
		return fmt.Errorf("open supervisor log %q: %w", logPath, err)
	}
	defer logFile.Close()

	child := exec.Command(executable, "__serve", "--config", configPath, "--listen", opts.listen, "--state-dir", stateDir)
	child.Stdout = logFile
	child.Stderr = logFile
	child.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	if err := child.Start(); err != nil {
		return fmt.Errorf("start background supervisor: %w", err)
	}
	exited := make(chan error, 1)
	go func() { exited <- child.Wait() }()
	timer := time.NewTimer(startTimeout)
	defer timer.Stop()
	ticker := time.NewTicker(25 * time.Millisecond)
	defer ticker.Stop()
	for {
		state, stateErr := service.LoadState(stateDir)
		if stateErr == nil && state.PID == child.Process.Pid && service.OwnsState(state) {
			admin, err := adminURL(state.Addr)
			if err != nil {
				_ = child.Process.Signal(syscall.SIGTERM)
				return fmt.Errorf("format admin URL from proxy listener: %w", err)
			}
			fmt.Fprintf(output, "Cozy is running on %s\n", state.Addr)
			fmt.Fprintf(output, "Admin: %s\n", admin)
			for _, site := range state.Sites {
				fmt.Fprintln(output, site.URL)
			}
			return nil
		}
		if stateErr != nil && !errors.Is(stateErr, os.ErrNotExist) {
			_ = child.Process.Signal(syscall.SIGTERM)
			return fmt.Errorf("read supervisor runtime state: %w; see %s", stateErr, logPath)
		}
		select {
		case exitErr := <-exited:
			if exitErr == nil {
				return fmt.Errorf("background supervisor exited before becoming ready; see %s", logPath)
			}
			return fmt.Errorf("background supervisor failed: %w; see %s", exitErr, logPath)
		case <-timer.C:
			_ = child.Process.Signal(syscall.SIGTERM)
			return fmt.Errorf("background supervisor did not become ready within %s; see %s", startTimeout, logPath)
		case <-ticker.C:
		}
	}
}

func checkListener(address string) error {
	resolved, err := net.ResolveTCPAddr("tcp", address)
	if err != nil {
		return fmt.Errorf("resolve proxy listener %s: %w", address, err)
	}
	if resolved.IP == nil || !resolved.IP.IsLoopback() {
		return fmt.Errorf("proxy listener must use a loopback address; choose --listen 127.0.0.1:<port>")
	}
	listener, err := net.Listen("tcp", address)
	if err != nil {
		switch {
		case errors.Is(err, syscall.EACCES), errors.Is(err, syscall.EPERM):
			return fmt.Errorf("cannot bind proxy listener %s: permission denied; grant permission explicitly or choose --listen 127.0.0.1:<port>: %w", address, err)
		case errors.Is(err, syscall.EADDRINUSE):
			return fmt.Errorf("proxy listener %s is already in use; stop the conflicting service or choose --listen 127.0.0.1:<port>: %w", address, err)
		default:
			return fmt.Errorf("cannot bind proxy listener %s: %w", address, err)
		}
	}
	if err := listener.Close(); err != nil {
		return fmt.Errorf("release checked proxy listener %s: %w", address, err)
	}
	return nil
}

func check(opts commandOptions, output io.Writer) error {
	if _, err := loadConfig(opts.configPath); err != nil {
		return err
	}
	state, err := service.LoadState(opts.stateDir)
	if err == nil && state.Addr == opts.listen && service.OwnsState(state) {
		fmt.Fprintf(output, "Configuration is valid; Cozy is running on %s.\n", opts.listen)
		return nil
	}
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		return fmt.Errorf("read runtime state: %w", err)
	}
	if err := checkListener(opts.listen); err != nil {
		return err
	}
	fmt.Fprintf(output, "Configuration is valid; proxy listener %s is available.\n", opts.listen)
	return nil
}

func requestControl(opts commandOptions, action string, output io.Writer) error {
	state, err := service.LoadState(opts.stateDir)
	if errors.Is(err, os.ErrNotExist) {
		return fmt.Errorf("Cozy is not running; start it with cozy up")
	}
	if err != nil {
		return fmt.Errorf("read runtime state: %w", err)
	}
	if !service.OwnsState(state) {
		return fmt.Errorf("Cozy is not running; the recorded supervisor state could not be verified")
	}
	if opts.site != "" {
		if _, err := findSite(state, opts.site); err != nil {
			return err
		}
	}
	ctx, cancel := context.WithTimeout(context.Background(), stopTimeout)
	defer cancel()
	result, err := service.Request(ctx, state, action, opts.site)
	if err != nil {
		return fmt.Errorf("%s local services: %w", action, err)
	}
	if result.Message != "" {
		fmt.Fprintln(output, result.Message)
	} else if action == "restart" && opts.site != "" {
		fmt.Fprintf(output, "Restarted %s.\n", opts.site)
	} else if action == "restart" {
		fmt.Fprintln(output, "Restarted all sites.")
	} else {
		fmt.Fprintln(output, "Refreshed Cozy configuration.")
	}
	return nil
}

func serve(opts commandOptions) error {
	cfg, err := loadConfig(opts.configPath)
	if err != nil {
		return err
	}
	manager, err := service.Start(cfg, service.Options{Addr: opts.listen, StateDir: opts.stateDir, ConfigPath: opts.configPath})
	if err != nil {
		return fmt.Errorf("start local services and proxy listener %s: %w", opts.listen, err)
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	hup := make(chan os.Signal, 1)
	signal.Notify(hup, syscall.SIGHUP)
	defer signal.Stop(hup)
	hupDone := make(chan struct{})
	go func() {
		defer close(hupDone)
		for {
			select {
			case <-ctx.Done():
				return
			case <-hup:
				state, err := service.LoadState(opts.stateDir)
				if err != nil {
					fmt.Fprintf(os.Stderr, "cozy refresh: read supervisor state after SIGHUP: %v\n", err)
					continue
				}
				if !service.OwnsState(state) {
					fmt.Fprintln(os.Stderr, "cozy refresh: supervisor state after SIGHUP could not be verified")
					continue
				}
				requestCtx, cancel := context.WithTimeout(ctx, stopTimeout)
				_, err = service.Request(requestCtx, state, "refresh", "")
				cancel()
				if err != nil {
					fmt.Fprintf(os.Stderr, "cozy refresh: reload configuration after SIGHUP: %v\n", err)
				}
			}
		}
	}()
	defer func() {
		stop()
		<-hupDone
	}()
	if err := manager.Wait(ctx); err != nil && !errors.Is(err, context.Canceled) {
		shutdownCtx, cancel := context.WithTimeout(context.Background(), stopTimeout)
		defer cancel()
		if shutdownErr := manager.Shutdown(shutdownCtx); shutdownErr != nil {
			return errors.Join(err, shutdownErr)
		}
		return err
	}
	shutdownCtx, cancel := context.WithTimeout(context.Background(), stopTimeout)
	defer cancel()
	if err := manager.Shutdown(shutdownCtx); err != nil {
		return fmt.Errorf("shut down local services: %w", err)
	}
	return nil
}

func down(opts commandOptions, output io.Writer) error {
	state, err := service.LoadState(opts.stateDir)
	if errors.Is(err, os.ErrNotExist) {
		fmt.Fprintln(output, "Cozy is not running.")
		return nil
	}
	if err != nil {
		return fmt.Errorf("read runtime state: %w", err)
	}
	if !service.OwnsState(state) {
		fmt.Fprintln(output, "Cozy is not running; the recorded supervisor state could not be verified.")
		return nil
	}
	process, err := os.FindProcess(state.PID)
	if err != nil {
		return fmt.Errorf("find supervisor PID %d: %w", state.PID, err)
	}
	if err := process.Signal(syscall.SIGTERM); err != nil {
		if errors.Is(err, os.ErrProcessDone) || errors.Is(err, syscall.ESRCH) {
			fmt.Fprintln(output, "Cozy is not running.")
			return nil
		}
		return fmt.Errorf("stop supervisor PID %d: %w", state.PID, err)
	}
	deadline := time.Now().Add(stopTimeout)
	for time.Now().Before(deadline) {
		current, stateErr := service.LoadState(opts.stateDir)
		if errors.Is(stateErr, os.ErrNotExist) || (stateErr == nil && current.PID != state.PID && service.OwnsState(current)) {
			fmt.Fprintln(output, "Cozy has stopped.")
			return nil
		}
		if stateErr != nil {
			return fmt.Errorf("check supervisor shutdown: %w", stateErr)
		}
		time.Sleep(25 * time.Millisecond)
	}
	return fmt.Errorf("supervisor PID %d did not shut down within %s; inspect %s", state.PID, stopTimeout, filepath.Join(opts.stateDir, "cozy.log"))
}

func status(opts commandOptions, output io.Writer) error {
	state, err := service.LoadState(opts.stateDir)
	if errors.Is(err, os.ErrNotExist) {
		fmt.Fprintln(output, "Cozy is not running.")
		return nil
	}
	if err != nil {
		return fmt.Errorf("read runtime state: %w", err)
	}
	if !service.OwnsState(state) {
		fmt.Fprintln(output, "Cozy is not running; the recorded supervisor state could not be verified.")
		return nil
	}
	admin, err := adminURL(state.Addr)
	if err != nil {
		return fmt.Errorf("format admin URL from proxy listener: %w", err)
	}
	fmt.Fprintf(output, "Cozy is running on %s (PID %d)\n", state.Addr, state.PID)
	fmt.Fprintf(output, "Admin: %s\n", admin)
	for _, site := range state.Sites {
		fmt.Fprintf(output, "%s\tPID %d\t%s\n", site.URL, site.PID, site.LogPath)
	}
	return nil
}

func adminURL(address string) (string, error) {
	host, portText, err := net.SplitHostPort(address)
	if err != nil {
		return "", fmt.Errorf("parse loopback proxy listener %q: %w", address, err)
	}
	ip := net.ParseIP(host)
	if ip == nil || !ip.IsLoopback() {
		return "", fmt.Errorf("proxy listener %q must use a loopback IP", address)
	}
	port, err := strconv.ParseUint(portText, 10, 16)
	if err != nil || port == 0 {
		return "", fmt.Errorf("proxy listener %q must use a port from 1 through 65535", address)
	}
	if port == 80 {
		return "http://cozy.localhost/", nil
	}
	return fmt.Sprintf("http://cozy.localhost:%d/", port), nil
}

func logs(opts commandOptions, output io.Writer) error {
	state, err := service.LoadState(opts.stateDir)
	if err != nil {
		return fmt.Errorf("load runtime state; start Cozy with cozy up: %w", err)
	}
	site, err := findSite(state, opts.site)
	if err != nil {
		return err
	}
	logFile, err := os.Open(site.LogPath)
	if err != nil {
		return fmt.Errorf("open logs for %s: %w", site.Name, err)
	}
	defer logFile.Close()
	if _, err := io.Copy(output, logFile); err != nil {
		return fmt.Errorf("read logs for %s: %w", site.Name, err)
	}
	return nil
}

func openSite(opts commandOptions) error {
	state, err := service.LoadState(opts.stateDir)
	if err != nil {
		return fmt.Errorf("load runtime state; start Cozy with cozy up: %w", err)
	}
	site, err := findSite(state, opts.site)
	if err != nil {
		return err
	}
	if runtime.GOOS != "darwin" {
		return fmt.Errorf("automatic browser opening requires macOS; visit %s", site.URL)
	}
	if output, err := exec.Command("open", site.URL).CombinedOutput(); err != nil {
		message := strings.TrimSpace(string(output))
		if message != "" {
			return fmt.Errorf("open %s in your browser: %w: %s", site.URL, err, message)
		}
		return fmt.Errorf("open %s in your browser: %w", site.URL, err)
	}
	return nil
}

func findSite(state service.State, name string) (service.SiteState, error) {
	for _, site := range state.Sites {
		if site.Name == name {
			return site, nil
		}
	}
	return service.SiteState{}, fmt.Errorf("site %q is not present in Cozy runtime state", name)
}
