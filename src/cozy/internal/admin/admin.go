// Package admin serves Cozy's local service-management dashboard.
package admin

import (
	"context"
	"embed"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime"
	"net/http"
	"strconv"
	"strings"

	"cozy/internal/config"
)

//go:embed static/index.html static/styles.css static/app.js static/logo.svg
var assets embed.FS

const maxRequestBytes = 16 << 10

// Site is the public, nonsensitive description of a supervised site.
type Site struct {
	Name    string `json:"name"`
	URL     string `json:"url"`
	Run     string `json:"run"`
	PID     int    `json:"pid"`
	Port    int    `json:"port"`
	LogPath string `json:"log_path"`
}

// Backend supplies dashboard operations without exposing supervisor credentials.
type Backend interface {
	Sites() []Site
	RestartSite(context.Context, string) error
	AddSite(context.Context, Site) error
}

// New returns the local dashboard and its same-origin-protected management API.
func New(backend Backend) http.Handler {
	return &handler{backend: backend}
}

type handler struct {
	backend Backend
}

func (h *handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("X-Content-Type-Options", "nosniff")
	w.Header().Set("Referrer-Policy", "same-origin")
	w.Header().Set("Content-Security-Policy", "default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'self'")
	w.Header().Set("Cache-Control", "no-store")

	switch r.URL.Path {
	case "/":
		h.serveAsset(w, r, "static/index.html", "text/html; charset=utf-8")
	case "/styles.css":
		h.serveAsset(w, r, "static/styles.css", "text/css; charset=utf-8")
	case "/app.js":
		h.serveAsset(w, r, "static/app.js", "text/javascript; charset=utf-8")
	case "/logo.svg":
		h.serveAsset(w, r, "static/logo.svg", "image/svg+xml")
	case "/api/sites":
		h.serveSites(w, r)
	default:
		if strings.HasPrefix(r.URL.Path, "/api/sites/") && strings.HasSuffix(r.URL.Path, "/restart") {
			h.serveRestart(w, r)
			return
		}
		writeError(w, http.StatusNotFound, "page not found")
	}
}

func (h *handler) serveAsset(w http.ResponseWriter, r *http.Request, path, contentType string) {
	if r.Method != http.MethodGet && r.Method != http.MethodHead {
		w.Header().Set("Allow", "GET, HEAD")
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}
	data, err := assets.ReadFile(path)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "dashboard asset is unavailable")
		return
	}
	w.Header().Set("Content-Type", contentType)
	w.Header().Set("Content-Length", strconv.Itoa(len(data)))
	w.WriteHeader(http.StatusOK)
	if r.Method != http.MethodHead {
		_, _ = w.Write(data)
	}
}

func (h *handler) serveSites(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		sites := h.backend.Sites()
		if sites == nil {
			sites = []Site{}
		}
		writeJSON(w, http.StatusOK, struct {
			Sites []Site `json:"sites"`
		}{Sites: sites})
	case http.MethodPost:
		if !authorizeMutation(w, r) {
			return
		}
		var site Site
		if !decodeJSON(w, r, &site) {
			return
		}
		if site.PID != 0 || site.Port != 0 || site.LogPath != "" {
			writeError(w, http.StatusBadRequest, "runtime metadata cannot be specified when adding a site")
			return
		}
		if site.URL == "" {
			site.URL = "http://" + site.Name
		}
		if err := (config.Config{Version: 1, Sites: []config.Site{{
			Name: site.Name, URL: site.URL, Run: site.Run,
		}}}).Validate(); err != nil {
			writeError(w, http.StatusBadRequest, err.Error())
			return
		}
		for _, existing := range h.backend.Sites() {
			if existing.Name == site.Name {
				writeError(w, http.StatusConflict, "site is already configured")
				return
			}
		}
		if err := h.backend.AddSite(r.Context(), site); err != nil {
			writeError(w, http.StatusInternalServerError, "could not add site: "+err.Error())
			return
		}
		writeJSON(w, http.StatusCreated, struct {
			Site Site `json:"site"`
		}{Site: site})
	default:
		w.Header().Set("Allow", "GET, POST")
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
	}
}

func (h *handler) serveRestart(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		w.Header().Set("Allow", "POST")
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}
	if !authorizeMutation(w, r) {
		return
	}
	name := strings.TrimSuffix(strings.TrimPrefix(r.URL.Path, "/api/sites/"), "/restart")
	if name == "" || strings.Contains(name, "/") {
		writeError(w, http.StatusNotFound, "site not found")
		return
	}
	var request struct{}
	if !decodeJSON(w, r, &request) {
		return
	}
	known := false
	for _, site := range h.backend.Sites() {
		if site.Name == name {
			known = true
			break
		}
	}
	if !known {
		writeError(w, http.StatusNotFound, "site not found")
		return
	}
	if err := h.backend.RestartSite(r.Context(), name); err != nil {
		writeError(w, http.StatusInternalServerError, "could not restart site: "+err.Error())
		return
	}
	writeJSON(w, http.StatusOK, struct {
		Message string `json:"message"`
	}{Message: "restarted " + name})
}

func authorizeMutation(w http.ResponseWriter, r *http.Request) bool {
	origins := r.Header.Values("Origin")
	if len(origins) != 1 || r.Host == "" || strings.ContainsAny(r.Host, ",/\\ \t\r\n") ||
		origins[0] != "http://"+r.Host {
		writeError(w, http.StatusForbidden, "a matching same-origin request is required")
		return false
	}
	contentType, _, err := mime.ParseMediaType(r.Header.Get("Content-Type"))
	if err != nil || contentType != "application/json" {
		writeError(w, http.StatusUnsupportedMediaType, "content type must be application/json")
		return false
	}
	return true
}

func decodeJSON(w http.ResponseWriter, r *http.Request, value any) bool {
	r.Body = http.MaxBytesReader(w, r.Body, maxRequestBytes)
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(value); err != nil {
		var maxBytes *http.MaxBytesError
		if errors.As(err, &maxBytes) {
			writeError(w, http.StatusRequestEntityTooLarge, "JSON body must not exceed 16 KiB")
		} else {
			writeError(w, http.StatusBadRequest, fmt.Sprintf("invalid JSON request: %v", err))
		}
		return false
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		var maxBytes *http.MaxBytesError
		if errors.As(err, &maxBytes) {
			writeError(w, http.StatusRequestEntityTooLarge, "JSON body must not exceed 16 KiB")
		} else {
			writeError(w, http.StatusBadRequest, "JSON body must contain exactly one object")
		}
		return false
	}
	return true
}

func writeError(w http.ResponseWriter, status int, message string) {
	writeJSON(w, status, struct {
		Error string `json:"error"`
	}{Error: message})
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}
