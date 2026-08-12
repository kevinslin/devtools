// Package config reads and validates Cozy's dependency-free YAML configuration.
package config

import (
	"bufio"
	"bytes"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

// Config describes version 1 of cozy.yaml.
type Config struct {
	Version int
	Sites   []Site
}

// Site describes one locally managed HTTP service.
type Site struct {
	Name            string
	URL             string
	Run             string
	RedirectCommand string
}

// Load reads, parses, and validates the configuration at path.
func Load(path string) (Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return Config{}, fmt.Errorf("read configuration %q: %w", path, err)
	}
	config, err := Parse(data)
	if err != nil {
		return Config{}, fmt.Errorf("parse configuration %q: %w", path, err)
	}
	return config, nil
}

// AppendSite validates and atomically appends a site without changing existing YAML.
func AppendSite(path string, site Site) error {
	original, err := os.ReadFile(path)
	if err != nil {
		return fmt.Errorf("read configuration %q: %w", path, err)
	}
	current, err := Parse(original)
	if err != nil {
		return fmt.Errorf("parse configuration %q: %w", path, err)
	}
	candidate := Config{
		Version: current.Version,
		Sites:   append(append([]Site(nil), current.Sites...), site),
	}
	if err := candidate.Validate(); err != nil {
		return fmt.Errorf("cannot add site to configuration %q: %w", path, err)
	}

	updated := append([]byte(nil), original...)
	if len(updated) > 0 && updated[len(updated)-1] != '\n' {
		updated = append(updated, '\n')
	}
	updated = fmt.Appendf(updated, "  - name: %s\n    url: %s\n    run: %s\n",
		site.Name, site.URL, strconv.Quote(site.Run))
	if _, err := Parse(updated); err != nil {
		return fmt.Errorf("validate updated configuration %q: %w", path, err)
	}
	return WriteAtomic(path, updated)
}

// WriteAtomic replaces a file with synced data while preserving existing permissions.
func WriteAtomic(path string, data []byte) error {
	mode := os.FileMode(0o600)
	info, err := os.Stat(path)
	if err == nil {
		mode = info.Mode().Perm()
	} else if !os.IsNotExist(err) {
		return fmt.Errorf("inspect configuration %q: %w", path, err)
	}

	temporary, err := os.CreateTemp(filepath.Dir(path), "."+filepath.Base(path)+".tmp-*")
	if err != nil {
		return fmt.Errorf("create temporary configuration for %q: %w", path, err)
	}
	temporaryPath := temporary.Name()
	defer os.Remove(temporaryPath)
	defer temporary.Close()

	if err := temporary.Chmod(mode); err != nil {
		return fmt.Errorf("set configuration permissions for %q: %w", path, err)
	}
	written, err := temporary.Write(data)
	if err != nil {
		return fmt.Errorf("write temporary configuration for %q: %w", path, err)
	}
	if written != len(data) {
		return fmt.Errorf("write temporary configuration for %q: %w", path, io.ErrShortWrite)
	}
	if err := temporary.Sync(); err != nil {
		return fmt.Errorf("sync temporary configuration for %q: %w", path, err)
	}
	if err := temporary.Close(); err != nil {
		return fmt.Errorf("close temporary configuration for %q: %w", path, err)
	}
	if err := os.Rename(temporaryPath, path); err != nil {
		return fmt.Errorf("replace configuration %q: %w", path, err)
	}
	return nil
}

// Parse reads and validates the supported version 1 YAML format.
func Parse(data []byte) (Config, error) {
	var config Config
	rootKeys := make(map[string]bool)
	var siteKeys map[string]bool
	scanner := bufio.NewScanner(bytes.NewReader(data))
	scanner.Buffer(make([]byte, 4096), 8*1024*1024)
	lineNumber := 0
	inSites := false

	for scanner.Scan() {
		lineNumber++
		line, err := uncomment(scanner.Text())
		if err != nil {
			return Config{}, fmt.Errorf("line %d: %w", lineNumber, err)
		}
		if strings.TrimSpace(line) == "" {
			continue
		}
		if strings.ContainsRune(line[:len(line)-len(strings.TrimLeft(line, " \t"))], '\t') {
			return Config{}, fmt.Errorf("line %d: use spaces for indentation", lineNumber)
		}
		indent := len(line) - len(strings.TrimLeft(line, " "))
		content := strings.TrimSpace(line)

		if indent == 0 {
			key, value, err := mapping(content)
			if err != nil {
				return Config{}, fmt.Errorf("line %d: %w", lineNumber, err)
			}
			if rootKeys[key] {
				return Config{}, fmt.Errorf("line %d: duplicate configuration key %q", lineNumber, key)
			}
			rootKeys[key] = true
			switch key {
			case "version":
				inSites = false
				config.Version, err = strconv.Atoi(value)
				if err != nil {
					return Config{}, fmt.Errorf("line %d: version must be the integer 1", lineNumber)
				}
			case "sites":
				if value != "" {
					return Config{}, fmt.Errorf("line %d: sites must be an indented list", lineNumber)
				}
				inSites = true
			default:
				return Config{}, fmt.Errorf("line %d: unknown configuration key %q", lineNumber, key)
			}
			continue
		}

		if !inSites {
			return Config{}, fmt.Errorf("line %d: unexpected indentation outside sites", lineNumber)
		}
		if indent == 2 && strings.HasPrefix(content, "- ") {
			config.Sites = append(config.Sites, Site{})
			siteKeys = make(map[string]bool)
			content = strings.TrimSpace(strings.TrimPrefix(content, "- "))
			if content == "" {
				continue
			}
		} else if indent != 4 || len(config.Sites) == 0 {
			return Config{}, fmt.Errorf("line %d: site entries must use a two-space list and four-space fields", lineNumber)
		}

		key, value, err := mapping(content)
		if err != nil {
			return Config{}, fmt.Errorf("line %d: %w", lineNumber, err)
		}
		if siteKeys[key] {
			return Config{}, fmt.Errorf("line %d: duplicate site key %q", lineNumber, key)
		}
		siteKeys[key] = true
		site := &config.Sites[len(config.Sites)-1]
		switch key {
		case "name":
			site.Name = value
		case "url":
			site.URL = value
		case "run":
			site.Run = value
		case "redirect_command":
			site.RedirectCommand = value
		default:
			return Config{}, fmt.Errorf("line %d: unknown site key %q", lineNumber, key)
		}
	}
	if err := scanner.Err(); err != nil {
		return Config{}, fmt.Errorf("scan configuration: %w", err)
	}
	if !rootKeys["version"] {
		return Config{}, fmt.Errorf("configuration requires version: 1")
	}
	if !rootKeys["sites"] {
		return Config{}, fmt.Errorf("configuration requires a sites list")
	}
	if err := config.Validate(); err != nil {
		return Config{}, err
	}
	return config, nil
}

// Validate checks the supported version, clean localhost URLs, and unique names.
func (c Config) Validate() error {
	if c.Version != 1 {
		return fmt.Errorf("configuration version must be 1; got %d", c.Version)
	}
	if len(c.Sites) == 0 {
		return fmt.Errorf("configuration must contain at least one site")
	}
	seen := make(map[string]struct{}, len(c.Sites))
	for i, site := range c.Sites {
		if !validName(site.Name) {
			return fmt.Errorf("site %d: name must be a valid *.localhost hostname", i+1)
		}
		if site.Name == "cozy.localhost" {
			return fmt.Errorf("site %d: cozy.localhost is reserved for the Cozy admin; choose another *.localhost site name", i+1)
		}
		if _, exists := seen[site.Name]; exists {
			return fmt.Errorf("site %d: duplicate site name %q", i+1, site.Name)
		}
		seen[site.Name] = struct{}{}
		if expected := "http://" + site.Name; site.URL != expected {
			return fmt.Errorf("site %q: url must be exactly %q", site.Name, expected)
		}
		hasRun := strings.TrimSpace(site.Run) != ""
		hasRedirectCommand := strings.TrimSpace(site.RedirectCommand) != ""
		if !hasRun && !hasRedirectCommand {
			return fmt.Errorf("site %q: run or redirect_command must be a nonempty command", site.Name)
		}
		if hasRun && hasRedirectCommand {
			return fmt.Errorf("site %q: configure exactly one of run or redirect_command", site.Name)
		}
	}
	return nil
}

func validName(name string) bool {
	if len(name) > 253 || !strings.HasSuffix(name, ".localhost") {
		return false
	}
	prefix := strings.TrimSuffix(name, ".localhost")
	if prefix == "" {
		return false
	}
	for _, label := range strings.Split(prefix, ".") {
		if len(label) == 0 || len(label) > 63 || label[0] == '-' || label[len(label)-1] == '-' {
			return false
		}
		for _, character := range label {
			if !(character >= 'a' && character <= 'z') && !(character >= '0' && character <= '9') && character != '-' {
				return false
			}
		}
	}
	return true
}

func mapping(line string) (string, string, error) {
	key, raw, ok := strings.Cut(line, ":")
	key = strings.TrimSpace(key)
	if !ok || key == "" {
		return "", "", fmt.Errorf("expected a key: value mapping")
	}
	value, err := scalar(strings.TrimSpace(raw))
	if err != nil {
		return "", "", fmt.Errorf("invalid value for %q: %w", key, err)
	}
	return key, value, nil
}

func scalar(value string) (string, error) {
	if value == "" {
		return "", nil
	}
	if value[0] == '"' {
		decoded, err := strconv.Unquote(value)
		if err != nil {
			return "", fmt.Errorf("invalid double-quoted scalar: %w", err)
		}
		return decoded, nil
	}
	if value[0] == '\'' {
		if len(value) < 2 || value[len(value)-1] != '\'' {
			return "", fmt.Errorf("unterminated single-quoted scalar")
		}
		return strings.ReplaceAll(value[1:len(value)-1], "''", "'"), nil
	}
	return value, nil
}

func uncomment(line string) (string, error) {
	var single, double, escaped bool
	for i := 0; i < len(line); i++ {
		character := line[i]
		if double && escaped {
			escaped = false
			continue
		}
		switch character {
		case '\\':
			if double {
				escaped = true
			}
		case '\'':
			if !double {
				if single && i+1 < len(line) && line[i+1] == '\'' {
					i++
					continue
				}
				single = !single
			}
		case '"':
			if !single {
				double = !double
			}
		case '#':
			if !single && !double && (i == 0 || line[i-1] == ' ' || line[i-1] == '\t') {
				return strings.TrimRight(line[:i], " \t\r"), nil
			}
		}
	}
	if single || double {
		return "", fmt.Errorf("unterminated quoted scalar")
	}
	return strings.TrimRight(line, " \t\r"), nil
}
