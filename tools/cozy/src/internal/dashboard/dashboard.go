// Package dashboard adapts the configured agtask dashboard to a Cozy-managed port.
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

// Run starts agtask and proxies its private local dashboard or redirects to its
// authenticated hosted Site without exposing dashboard credentials.
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
	hosted := target.Scheme == "https"
	if hosted {
		if err := cmd.Wait(); err != nil {
			return fmt.Errorf("hosted dashboard exited after printing its startup URL: %w", err)
		}
	}

	listener, err := net.Listen("tcp", net.JoinHostPort("127.0.0.1", strconv.Itoa(port)))
	if err != nil {
		cancel()
		if !hosted {
			_ = cmd.Wait()
		}
		return fmt.Errorf("bind assigned dashboard loopback port %d: %w", port, err)
	}

	var handler http.Handler = newProxy(target)
	if hosted {
		handler = http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
			location := *target
			location.Path = request.URL.Path
			location.RawPath = request.URL.RawPath
			location.RawQuery = request.URL.RawQuery
			http.Redirect(response, request, location.String(), http.StatusTemporaryRedirect)
		})
	}
	server := &http.Server{Handler: handler, ReadHeaderTimeout: 5 * time.Second}
	serveDone := make(chan error, 1)
	var childDone <-chan error
	if !hosted {
		done := make(chan error, 1)
		childDone = done
		go func() {
			for scanner.Scan() {
				fmt.Fprintln(stdout, scanner.Text())
			}
			done <- cmd.Wait()
		}()
	}
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
		if childDone != nil {
			<-childDone
		}
		return ctx.Err()
	case err := <-childDone:
		shutdown()
		if err != nil {
			return fmt.Errorf("agtask dashboard exited: %w", err)
		}
		return fmt.Errorf("agtask dashboard exited unexpectedly")
	case err := <-serveDone:
		shutdown()
		if childDone != nil {
			<-childDone
		}
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
		return nil, fmt.Errorf("dashboard printed an invalid startup URL")
	}
	if target.User != nil || target.Fragment != "" {
		return nil, fmt.Errorf("dashboard printed an invalid startup URL")
	}
	if target.Scheme == "https" {
		if !strings.HasSuffix(target.Hostname(), ".openai.chatgpt.site") ||
			target.Port() != "" || target.RawQuery != "" || target.ForceQuery ||
			(target.EscapedPath() != "" && target.EscapedPath() != "/") {
			return nil, fmt.Errorf("dashboard startup URL must be a trusted hosted Site root")
		}
		target.Path = "/"
		return target, nil
	}
	if target.Scheme != "http" {
		return nil, fmt.Errorf("dashboard printed an invalid startup URL")
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
