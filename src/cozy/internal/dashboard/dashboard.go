// Package dashboard adapts the local agtask dashboard to a Cozy-managed port.
package dashboard

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os/exec"
	"strconv"
	"strings"
	"time"
)

// Run starts agtask and proxies a Cozy-assigned loopback port to its private
// dashboard. The dashboard's capability token never becomes a public path.
func Run(ctx context.Context, port int, executable string, stdout, stderr io.Writer) error {
	if port < 1 || port > 65535 {
		return fmt.Errorf("dashboard port must be between 1 and 65535")
	}
	if executable == "" {
		return fmt.Errorf("dashboard executable must not be empty")
	}
	if stdout == nil || stderr == nil {
		return fmt.Errorf("dashboard output writers must not be nil")
	}

	childCtx, cancel := context.WithCancel(ctx)
	defer cancel()
	cmd := exec.CommandContext(childCtx, executable, "dashboard", "--no-open")
	cmd.Stderr = stderr
	output, err := cmd.StdoutPipe()
	if err != nil {
		return fmt.Errorf("capture dashboard startup: %w", err)
	}
	if err := cmd.Start(); err != nil {
		return fmt.Errorf("start agtask dashboard: %w", err)
	}

	scanner := bufio.NewScanner(output)
	if !scanner.Scan() {
		scanErr := scanner.Err()
		waitErr := cmd.Wait()
		if ctx.Err() != nil {
			return ctx.Err()
		}
		if scanErr != nil {
			return fmt.Errorf("read dashboard startup: %w", scanErr)
		}
		if waitErr != nil {
			return fmt.Errorf("dashboard exited before becoming ready: %w", waitErr)
		}
		return fmt.Errorf("dashboard exited without printing its local startup URL")
	}
	target, err := parseTarget(scanner.Text())
	if err != nil {
		cancel()
		_ = cmd.Wait()
		return err
	}

	listener, err := net.Listen("tcp", net.JoinHostPort("127.0.0.1", strconv.Itoa(port)))
	if err != nil {
		cancel()
		_ = cmd.Wait()
		return fmt.Errorf("bind assigned dashboard loopback port %d: %w", port, err)
	}

	proxy := newProxy(target)
	server := &http.Server{Handler: proxy, ReadHeaderTimeout: 5 * time.Second}
	serveDone := make(chan error, 1)
	childDone := make(chan error, 1)
	go func() {
		for scanner.Scan() {
			fmt.Fprintln(stdout, scanner.Text())
		}
		childDone <- cmd.Wait()
	}()
	go func() { serveDone <- server.Serve(listener) }()
	fmt.Fprintln(stdout, "agtask dashboard ready on managed loopback port")

	shutdown := func() {
		shutdownCtx, stop := context.WithTimeout(context.Background(), 2*time.Second)
		defer stop()
		_ = server.Shutdown(shutdownCtx)
		cancel()
	}

	select {
	case <-ctx.Done():
		shutdown()
		<-childDone
		return ctx.Err()
	case err := <-childDone:
		shutdown()
		if err != nil {
			return fmt.Errorf("agtask dashboard exited: %w", err)
		}
		return fmt.Errorf("agtask dashboard exited unexpectedly")
	case err := <-serveDone:
		shutdown()
		<-childDone
		if err != nil && !errors.Is(err, http.ErrServerClosed) {
			return fmt.Errorf("serve managed dashboard: %w", err)
		}
		if ctx.Err() != nil {
			return ctx.Err()
		}
		return fmt.Errorf("managed dashboard listener stopped unexpectedly")
	}
}

func parseTarget(line string) (*url.URL, error) {
	target, err := url.Parse(strings.TrimSpace(line))
	if err != nil || target == nil {
		return nil, fmt.Errorf("dashboard printed an invalid local startup URL")
	}
	if target.Scheme != "http" || target.User != nil || target.Fragment != "" {
		return nil, fmt.Errorf("dashboard printed an invalid local startup URL")
	}
	ip := net.ParseIP(target.Hostname())
	if ip == nil || !ip.IsLoopback() || target.Port() == "" {
		return nil, fmt.Errorf("dashboard startup URL must use a loopback address and port")
	}
	port, err := strconv.Atoi(target.Port())
	if err != nil || port < 1 || port > 65535 {
		return nil, fmt.Errorf("dashboard startup URL contains an invalid loopback port")
	}
	token := strings.Trim(target.EscapedPath(), "/")
	if token == "" || strings.Contains(token, "/") || token == "." || token == ".." {
		return nil, fmt.Errorf("dashboard startup URL must contain one private token")
	}
	decoded, err := url.PathUnescape(token)
	if err != nil || decoded == "" || strings.ContainsAny(decoded, "/\\") || decoded == "." || decoded == ".." {
		return nil, fmt.Errorf("dashboard startup URL must contain one private token")
	}
	target.RawQuery = ""
	target.Path = "/" + decoded + "/"
	target.RawPath = ""
	return target, nil
}

func newProxy(target *url.URL) *httputil.ReverseProxy {
	proxy := httputil.NewSingleHostReverseProxy(target)
	originalDirector := proxy.Director
	proxy.Director = func(request *http.Request) {
		publicHost := request.Host
		origin := request.Header.Get("Origin")
		originalDirector(request)
		request.Host = target.Host
		if origin == "http://"+publicHost {
			request.Header.Set("Origin", "http://"+target.Host)
		}
	}
	return proxy
}
