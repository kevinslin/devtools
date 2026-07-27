package admin

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

type testBackend struct {
	sites      []Site
	restarted  []string
	added      []Site
	restartErr error
	addErr     error
}

func (b *testBackend) Sites() []Site {
	return append([]Site(nil), b.sites...)
}

func (b *testBackend) RestartSite(_ context.Context, name string) error {
	if b.restartErr != nil {
		return b.restartErr
	}
	b.restarted = append(b.restarted, name)
	return nil
}

func (b *testBackend) AddSite(_ context.Context, site Site) error {
	if b.addErr != nil {
		return b.addErr
	}
	b.added = append(b.added, site)
	b.sites = append(b.sites, site)
	return nil
}

func newTestBackend() *testBackend {
	return &testBackend{sites: []Site{{
		Name: "fishy.localhost", URL: "http://fishy.localhost", Run: "fishy",
		PID: 42, Port: 12345, LogPath: "/private/tmp/fishy.log",
	}}}
}

func makeRequest(method, path, body string) *http.Request {
	r := httptest.NewRequest(method, "http://cozy.localhost:8080"+path, strings.NewReader(body))
	r.Header.Set("Origin", "http://cozy.localhost:8080")
	r.Header.Set("Content-Type", "application/json")
	return r
}

func TestDashboardAssets(t *testing.T) {
	tests := []struct {
		path        string
		contentType string
	}{
		{path: "/", contentType: "text/html; charset=utf-8"},
		{path: "/styles.css", contentType: "text/css; charset=utf-8"},
		{path: "/app.js", contentType: "text/javascript; charset=utf-8"},
		{path: "/logo.svg", contentType: "image/svg+xml"},
	}
	for _, tc := range tests {
		t.Run(tc.path, func(t *testing.T) {
			for _, method := range []string{http.MethodGet, http.MethodHead} {
				t.Run(method, func(t *testing.T) {
					recorder := httptest.NewRecorder()
					New(newTestBackend()).ServeHTTP(recorder, makeRequest(method, tc.path, ""))
					if recorder.Code != http.StatusOK {
						t.Fatalf("status = %d, want %d: %s", recorder.Code, http.StatusOK, recorder.Body.String())
					}
					if got := recorder.Header().Get("Content-Type"); got != tc.contentType {
						t.Errorf("content type = %q, want %q", got, tc.contentType)
					}
					if got := recorder.Header().Get("X-Content-Type-Options"); got != "nosniff" {
						t.Errorf("X-Content-Type-Options = %q, want nosniff", got)
					}
					if got := recorder.Header().Get("Content-Security-Policy"); !strings.Contains(got, "default-src 'self'") {
						t.Errorf("Content-Security-Policy = %q, want self-only policy", got)
					}
					if method == http.MethodHead && recorder.Body.Len() != 0 {
						t.Errorf("HEAD unexpectedly returned a %d-byte body", recorder.Body.Len())
					}
					if method == http.MethodGet && recorder.Body.Len() == 0 {
						t.Error("GET returned an empty dashboard asset")
					}
				})
			}
		})
	}
}

func TestSitesListIsCurated(t *testing.T) {
	recorder := httptest.NewRecorder()
	New(newTestBackend()).ServeHTTP(recorder, makeRequest(http.MethodGet, "/api/sites", ""))
	if recorder.Code != http.StatusOK {
		t.Fatalf("status = %d: %s", recorder.Code, recorder.Body.String())
	}
	var response struct {
		Sites []Site `json:"sites"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode sites: %v", err)
	}
	if len(response.Sites) != 1 || response.Sites[0].Name != "fishy.localhost" || response.Sites[0].PID != 42 {
		t.Fatalf("unexpected site listing: %+v", response.Sites)
	}
	var raw map[string]json.RawMessage
	if err := json.Unmarshal(recorder.Body.Bytes(), &raw); err != nil {
		t.Fatalf("decode response keys: %v", err)
	}
	if len(raw) != 1 {
		t.Fatalf("listing exposed unexpected response fields: %v", raw)
	}
	for _, forbidden := range []string{"token", "control_path", "control.sock"} {
		if strings.Contains(strings.ToLower(recorder.Body.String()), forbidden) {
			t.Errorf("listing exposed forbidden supervisor detail %q", forbidden)
		}
	}
}

func TestSitesListReturnsEmptyArray(t *testing.T) {
	recorder := httptest.NewRecorder()
	New(&testBackend{}).ServeHTTP(recorder, makeRequest(http.MethodGet, "/api/sites", ""))
	if recorder.Code != http.StatusOK || strings.TrimSpace(recorder.Body.String()) != `{"sites":[]}` {
		t.Fatalf("empty listing = status %d, body %q; want an empty sites array", recorder.Code, recorder.Body.String())
	}
}

func TestAddSite(t *testing.T) {
	backend := newTestBackend()
	recorder := httptest.NewRecorder()
	New(backend).ServeHTTP(recorder, makeRequest(http.MethodPost, "/api/sites", `{"name":"garden.localhost","run":"garden --serve"}`))
	if recorder.Code != http.StatusCreated {
		t.Fatalf("add status = %d: %s", recorder.Code, recorder.Body.String())
	}
	if len(backend.added) != 1 {
		t.Fatalf("added %d sites, want 1", len(backend.added))
	}
	if got, want := backend.added[0].URL, "http://garden.localhost"; got != want {
		t.Errorf("derived URL = %q, want %q", got, want)
	}
	if got, want := backend.added[0].Run, "garden --serve"; got != want {
		t.Errorf("run = %q, want %q", got, want)
	}
	var response struct {
		Site Site `json:"site"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode added site: %v", err)
	}
	if response.Site != backend.added[0] {
		t.Errorf("response site = %+v, want %+v", response.Site, backend.added[0])
	}
}

func TestAddSiteRejectsInvalidRequests(t *testing.T) {
	tests := []struct {
		name string
		body string
		want int
	}{
		{name: "empty name", body: `{"name":"","run":"garden"}`, want: http.StatusBadRequest},
		{name: "uppercase name", body: `{"name":"Garden.localhost","run":"garden"}`, want: http.StatusBadRequest},
		{name: "empty command", body: `{"name":"garden.localhost","run":"  "}`, want: http.StatusBadRequest},
		{name: "noncanonical URL", body: `{"name":"garden.localhost","url":"http://garden.localhost:8080","run":"garden"}`, want: http.StatusBadRequest},
		{name: "duplicate name", body: `{"name":"fishy.localhost","run":"fishy"}`, want: http.StatusConflict},
		{name: "unknown field", body: `{"name":"garden.localhost","run":"garden","unexpected":true}`, want: http.StatusBadRequest},
		{name: "runtime metadata", body: `{"name":"garden.localhost","run":"garden","pid":42}`, want: http.StatusBadRequest},
		{name: "multiple JSON values", body: `{"name":"garden.localhost","run":"garden"} {}`, want: http.StatusBadRequest},
		{name: "empty JSON", body: "", want: http.StatusBadRequest},
		{name: "oversized body", body: fmt.Sprintf(`{"name":"garden.localhost","run":"%s"}`, strings.Repeat("x", maxRequestBytes)), want: http.StatusRequestEntityTooLarge},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			backend := newTestBackend()
			recorder := httptest.NewRecorder()
			New(backend).ServeHTTP(recorder, makeRequest(http.MethodPost, "/api/sites", tc.body))
			if recorder.Code != tc.want {
				t.Fatalf("status = %d, want %d: %s", recorder.Code, tc.want, recorder.Body.String())
			}
			if len(backend.added) != 0 {
				t.Fatalf("invalid request unexpectedly added %+v", backend.added)
			}
		})
	}
}

func TestRestartSite(t *testing.T) {
	backend := newTestBackend()
	recorder := httptest.NewRecorder()
	New(backend).ServeHTTP(recorder, makeRequest(http.MethodPost, "/api/sites/fishy.localhost/restart", `{}`))
	if recorder.Code != http.StatusOK {
		t.Fatalf("restart status = %d: %s", recorder.Code, recorder.Body.String())
	}
	if len(backend.restarted) != 1 || backend.restarted[0] != "fishy.localhost" {
		t.Fatalf("restarted sites = %v, want fishy.localhost", backend.restarted)
	}
	var response struct {
		Message string `json:"message"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode restart response: %v", err)
	}
	if response.Message != "restarted fishy.localhost" {
		t.Errorf("restart message = %q", response.Message)
	}
}

func TestRestartRejectsUnknownSiteAndMalformedBody(t *testing.T) {
	tests := []struct {
		name string
		path string
		body string
		want int
	}{
		{name: "unknown site", path: "/api/sites/garden.localhost/restart", body: `{}`, want: http.StatusNotFound},
		{name: "missing name", path: "/api/sites//restart", body: `{}`, want: http.StatusNotFound},
		{name: "nested name", path: "/api/sites/fishy.localhost/extra/restart", body: `{}`, want: http.StatusNotFound},
		{name: "unknown field", path: "/api/sites/fishy.localhost/restart", body: `{"force":true}`, want: http.StatusBadRequest},
		{name: "trailing value", path: "/api/sites/fishy.localhost/restart", body: `{} {}`, want: http.StatusBadRequest},
		{name: "empty body", path: "/api/sites/fishy.localhost/restart", body: "", want: http.StatusBadRequest},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			backend := newTestBackend()
			recorder := httptest.NewRecorder()
			New(backend).ServeHTTP(recorder, makeRequest(http.MethodPost, tc.path, tc.body))
			if recorder.Code != tc.want {
				t.Fatalf("status = %d, want %d: %s", recorder.Code, tc.want, recorder.Body.String())
			}
			if len(backend.restarted) != 0 {
				t.Fatalf("invalid request unexpectedly restarted %v", backend.restarted)
			}
		})
	}
}

func TestMutationsRequireSameOriginAndJSON(t *testing.T) {
	tests := []struct {
		name   string
		change func(*http.Request)
		want   int
	}{
		{name: "missing origin", change: func(r *http.Request) { r.Header.Del("Origin") }, want: http.StatusForbidden},
		{name: "cross origin", change: func(r *http.Request) { r.Header.Set("Origin", "http://outside.localhost:8080") }, want: http.StatusForbidden},
		{name: "duplicate origins", change: func(r *http.Request) { r.Header.Add("Origin", "http://cozy.localhost:8080") }, want: http.StatusForbidden},
		{name: "null origin", change: func(r *http.Request) { r.Header.Set("Origin", "null") }, want: http.StatusForbidden},
		{name: "invalid host", change: func(r *http.Request) { r.Host = "cozy.localhost:8080,other" }, want: http.StatusForbidden},
		{name: "missing content type", change: func(r *http.Request) { r.Header.Del("Content-Type") }, want: http.StatusUnsupportedMediaType},
		{name: "form content type", change: func(r *http.Request) { r.Header.Set("Content-Type", "application/x-www-form-urlencoded") }, want: http.StatusUnsupportedMediaType},
		{name: "malformed content type", change: func(r *http.Request) { r.Header.Set("Content-Type", "application/json; charset") }, want: http.StatusUnsupportedMediaType},
	}
	for _, endpoint := range []struct {
		name string
		path string
		body string
	}{
		{name: "add", path: "/api/sites", body: `{"name":"garden.localhost","run":"garden"}`},
		{name: "restart", path: "/api/sites/fishy.localhost/restart", body: `{}`},
	} {
		for _, tc := range tests {
			t.Run(endpoint.name+"/"+tc.name, func(t *testing.T) {
				backend := newTestBackend()
				r := makeRequest(http.MethodPost, endpoint.path, endpoint.body)
				tc.change(r)
				recorder := httptest.NewRecorder()
				New(backend).ServeHTTP(recorder, r)
				if recorder.Code != tc.want {
					t.Fatalf("status = %d, want %d: %s", recorder.Code, tc.want, recorder.Body.String())
				}
				if len(backend.added) != 0 || len(backend.restarted) != 0 {
					t.Fatalf("unauthorized request changed services: added=%v restarted=%v", backend.added, backend.restarted)
				}
			})
		}
	}
}

func TestRejectUnexpectedMethodsAndPaths(t *testing.T) {
	tests := []struct {
		name   string
		method string
		path   string
		want   int
	}{
		{name: "dashboard mutation", method: http.MethodPost, path: "/", want: http.StatusMethodNotAllowed},
		{name: "asset deletion", method: http.MethodDelete, path: "/app.js", want: http.StatusMethodNotAllowed},
		{name: "sites deletion", method: http.MethodDelete, path: "/api/sites", want: http.StatusMethodNotAllowed},
		{name: "restart by GET", method: http.MethodGet, path: "/api/sites/fishy.localhost/restart", want: http.StatusMethodNotAllowed},
		{name: "unknown API", method: http.MethodGet, path: "/api/state", want: http.StatusNotFound},
		{name: "unknown asset", method: http.MethodGet, path: "/static/index.html", want: http.StatusNotFound},
		{name: "trailing sites slash", method: http.MethodGet, path: "/api/sites/", want: http.StatusNotFound},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			backend := newTestBackend()
			recorder := httptest.NewRecorder()
			New(backend).ServeHTTP(recorder, makeRequest(tc.method, tc.path, `{}`))
			if recorder.Code != tc.want {
				t.Fatalf("status = %d, want %d: %s", recorder.Code, tc.want, recorder.Body.String())
			}
			if len(backend.added) != 0 || len(backend.restarted) != 0 {
				t.Fatalf("unexpected method changed services: added=%v restarted=%v", backend.added, backend.restarted)
			}
		})
	}
}

func TestBackendFailures(t *testing.T) {
	tests := []struct {
		name    string
		backend *testBackend
		path    string
		body    string
	}{
		{
			name: "add failure",
			backend: &testBackend{
				addErr: errors.New("configuration cannot be saved"),
			},
			path: "/api/sites", body: `{"name":"garden.localhost","run":"garden"}`,
		},
		{
			name: "restart failure",
			backend: &testBackend{
				sites: []Site{{Name: "fishy.localhost"}}, restartErr: errors.New("process did not become healthy"),
			},
			path: "/api/sites/fishy.localhost/restart", body: `{}`,
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			recorder := httptest.NewRecorder()
			New(tc.backend).ServeHTTP(recorder, makeRequest(http.MethodPost, tc.path, tc.body))
			if recorder.Code != http.StatusInternalServerError {
				t.Fatalf("status = %d, want %d: %s", recorder.Code, http.StatusInternalServerError, recorder.Body.String())
			}
			var response struct {
				Error string `json:"error"`
			}
			if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil || response.Error == "" {
				t.Fatalf("backend failure was not returned as an actionable JSON error: %+v; decode error: %v", response, err)
			}
		})
	}
}
