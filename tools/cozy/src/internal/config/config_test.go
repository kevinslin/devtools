package config

import (
	"bytes"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

func TestParse(t *testing.T) {
	t.Parallel()
	input := `# Cozy services
version: 1 # configuration version
sites:
  - name: fishy.localhost
    url: "http://fishy.localhost" # clean public address
    run: 'fishy --message ''hello # world'''
  - name: garden.localhost
    url: http://garden.localhost
    run: "garden --port=8080"
  - name: tasks.localhost
    url: http://tasks.localhost
    redirect_command: agtask dashboard --no-open
`
	got, err := Parse([]byte(input))
	if err != nil {
		t.Fatalf("Parse() error = %v", err)
	}
	want := Config{Version: 1, Sites: []Site{
		{Name: "fishy.localhost", URL: "http://fishy.localhost", Run: "fishy --message 'hello # world'"},
		{Name: "garden.localhost", URL: "http://garden.localhost", Run: "garden --port=8080"},
		{Name: "tasks.localhost", URL: "http://tasks.localhost", RedirectCommand: "agtask dashboard --no-open"},
	}}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("Parse() = %#v, want %#v", got, want)
	}
}

func TestParseFailures(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name  string
		input string
		want  string
	}{
		{name: "missing version", input: "sites:\n  - name: fishy.localhost\n    url: http://fishy.localhost\n    run: fishy\n", want: "requires version"},
		{name: "missing sites", input: "version: 1\n", want: "requires a sites list"},
		{name: "empty sites", input: "version: 1\nsites:\n", want: "at least one site"},
		{name: "unsupported version", input: "version: 2\nsites:\n  - name: fishy.localhost\n    url: http://fishy.localhost\n    run: fishy\n", want: "version must be 1"},
		{name: "noninteger version", input: "version: one\nsites:\n", want: "version must be the integer 1"},
		{name: "duplicate version", input: "version: 1\nversion: 1\nsites:\n", want: "duplicate configuration key"},
		{name: "unknown root key", input: "version: 1\nextra: true\nsites:\n", want: "unknown configuration key"},
		{name: "sites scalar", input: "version: 1\nsites: fishy\n", want: "indented list"},
		{name: "duplicate site field", input: "version: 1\nsites:\n  - name: fishy.localhost\n    name: fishy.localhost\n    url: http://fishy.localhost\n    run: fishy\n", want: "duplicate site key"},
		{name: "unknown site field", input: "version: 1\nsites:\n  - name: fishy.localhost\n    url: http://fishy.localhost\n    run: fishy\n    extra: true\n", want: "unknown site key"},
		{name: "duplicate site name", input: "version: 1\nsites:\n  - name: fishy.localhost\n    url: http://fishy.localhost\n    run: fishy\n  - name: fishy.localhost\n    url: http://fishy.localhost\n    run: fishy\n", want: "duplicate site name"},
		{name: "reserved admin name", input: "version: 1\nsites:\n  - name: cozy.localhost\n    url: http://cozy.localhost\n    run: cozy\n", want: "reserved for the Cozy admin"},
		{name: "empty hostname prefix", input: "version: 1\nsites:\n  - name: .localhost\n    url: http://.localhost\n    run: fishy\n", want: "valid *.localhost hostname"},
		{name: "invalid hostname label", input: "version: 1\nsites:\n  - name: -fishy.localhost\n    url: http://-fishy.localhost\n    run: fishy\n", want: "valid *.localhost hostname"},
		{name: "url has path", input: "version: 1\nsites:\n  - name: fishy.localhost\n    url: http://fishy.localhost/path\n    run: fishy\n", want: "url must be exactly"},
		{name: "empty command", input: "version: 1\nsites:\n  - name: fishy.localhost\n    url: http://fishy.localhost\n    run: '  '\n", want: "nonempty command"},
		{name: "empty redirect command", input: "version: 1\nsites:\n  - name: fishy.localhost\n    url: http://fishy.localhost\n    redirect_command: '  '\n", want: "nonempty command"},
		{name: "conflicting site commands", input: "version: 1\nsites:\n  - name: fishy.localhost\n    url: http://fishy.localhost\n    run: fishy\n    redirect_command: agtask dashboard --no-open\n", want: "exactly one of run or redirect_command"},
		{name: "bad indentation", input: "version: 1\nsites:\n - name: fishy.localhost\n", want: "two-space list"},
		{name: "tab indentation", input: "version: 1\nsites:\n\t- name: fishy.localhost\n", want: "spaces for indentation"},
		{name: "unterminated quote", input: "version: 1\nsites:\n  - name: 'fishy.localhost\n", want: "unterminated quoted scalar"},
		{name: "oversized line", input: "version: 1\nsites:\n  - name: " + strings.Repeat("x", 8*1024*1024+1) + "\n", want: "scan configuration"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			_, err := Parse([]byte(tt.input))
			if err == nil || !strings.Contains(err.Error(), tt.want) {
				t.Fatalf("Parse() error = %v, want error containing %q", err, tt.want)
			}
		})
	}
}

func TestLoad(t *testing.T) {
	t.Parallel()
	directory := t.TempDir()
	path := filepath.Join(directory, "cozy.yaml")
	input := "version: 1\nsites:\n  - name: fishy.localhost\n    url: http://fishy.localhost\n    run: fishy\n"
	if err := os.WriteFile(path, []byte(input), 0o600); err != nil {
		t.Fatal(err)
	}
	got, err := Load(path)
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}
	if len(got.Sites) != 1 || got.Sites[0].Name != "fishy.localhost" {
		t.Fatalf("Load() = %#v, want the fishy site", got)
	}
	_, err = Load(filepath.Join(directory, "missing.yaml"))
	if err == nil || !strings.Contains(err.Error(), "read configuration") {
		t.Fatalf("Load(missing) error = %v, want read configuration error", err)
	}
	invalidPath := filepath.Join(directory, "invalid.yaml")
	if err := os.WriteFile(invalidPath, []byte("version: nope\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	_, err = Load(invalidPath)
	if err == nil || !strings.Contains(err.Error(), "parse configuration") {
		t.Fatalf("Load(invalid) error = %v, want parse configuration error", err)
	}
}

func TestValidate(t *testing.T) {
	t.Parallel()
	valid := Config{Version: 1, Sites: []Site{{
		Name: "fishy.localhost", URL: "http://fishy.localhost", Run: "fishy",
	}}}
	if err := valid.Validate(); err != nil {
		t.Fatalf("Validate() error = %v", err)
	}
	tests := []struct {
		name string
		edit func(*Config)
		want string
	}{
		{name: "version", edit: func(c *Config) { c.Version = 0 }, want: "version must be 1"},
		{name: "missing sites", edit: func(c *Config) { c.Sites = nil }, want: "at least one site"},
		{name: "empty name", edit: func(c *Config) { c.Sites[0].Name = "" }, want: "valid *.localhost hostname"},
		{name: "reserved admin name", edit: func(c *Config) {
			c.Sites[0].Name = "cozy.localhost"
			c.Sites[0].URL = "http://cozy.localhost"
		}, want: "reserved for the Cozy admin"},
		{name: "url", edit: func(c *Config) { c.Sites[0].URL += "/" }, want: "url must be exactly"},
		{name: "run", edit: func(c *Config) { c.Sites[0].Run = " \t " }, want: "nonempty command"},
		{name: "conflicting commands", edit: func(c *Config) { c.Sites[0].RedirectCommand = "agtask dashboard --no-open" }, want: "exactly one of run or redirect_command"},
		{name: "duplicate", edit: func(c *Config) { c.Sites = append(c.Sites, c.Sites[0]) }, want: "duplicate site name"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			config := Config{Version: valid.Version, Sites: append([]Site(nil), valid.Sites...)}
			tt.edit(&config)
			if err := config.Validate(); err == nil || !strings.Contains(err.Error(), tt.want) {
				t.Fatalf("Validate() error = %v, want error containing %q", err, tt.want)
			}
		})
	}
}

func TestAppendSitePreservesConfiguration(t *testing.T) {
	t.Parallel()
	for _, tt := range []struct {
		name     string
		trailing string
	}{
		{name: "existing trailing newline", trailing: "\n"},
		{name: "missing trailing newline", trailing: ""},
	} {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			directory := t.TempDir()
			path := filepath.Join(directory, "cozy.yaml")
			original := []byte("# Keep this user comment verbatim\nversion: 1 # keep the version comment\nsites:\n  - name: fishy.localhost\n    url: http://fishy.localhost\n    run: fishy\n# Keep this trailing comment" + tt.trailing)
			if err := os.WriteFile(path, original, 0o640); err != nil {
				t.Fatal(err)
			}
			if err := os.Chmod(path, 0o640); err != nil {
				t.Fatal(err)
			}
			added := Site{
				Name: "garden.localhost",
				URL:  "http://garden.localhost",
				Run:  `printf '%s\n' "hello # cozy" && echo "$PORT" | sed 's/hello/hi/'`,
			}

			if err := AppendSite(path, added); err != nil {
				t.Fatalf("AppendSite() error = %v", err)
			}
			updated, err := os.ReadFile(path)
			if err != nil {
				t.Fatal(err)
			}
			if !bytes.HasPrefix(updated, original) {
				t.Fatalf("AppendSite() changed existing configuration:\ngot  %q\nwant prefix %q", updated, original)
			}
			if !bytes.Contains(updated, []byte("    run: \"")) {
				t.Fatalf("AppendSite() did not double-quote the shell command: %s", updated)
			}
			got, err := Load(path)
			if err != nil {
				t.Fatalf("appended configuration is invalid: %v", err)
			}
			if len(got.Sites) != 2 || !reflect.DeepEqual(got.Sites[1], added) {
				t.Fatalf("appended site = %#v, want %#v", got.Sites, added)
			}
			info, err := os.Stat(path)
			if err != nil {
				t.Fatal(err)
			}
			if got := info.Mode().Perm(); got != 0o640 {
				t.Fatalf("configuration permissions = %#o, want %#o", got, 0o640)
			}
			assertNoTemporaryConfigurations(t, directory)
		})
	}
}

func TestAppendSiteRejectsInvalidChangesAtomically(t *testing.T) {
	t.Parallel()
	original := []byte("# preserve this\nversion: 1\nsites:\n  - name: fishy.localhost\n    url: http://fishy.localhost\n    run: fishy\n")
	tests := []struct {
		name string
		site Site
		want string
	}{
		{
			name: "duplicate name",
			site: Site{Name: "fishy.localhost", URL: "http://fishy.localhost", Run: "another fishy"},
			want: "duplicate site name",
		},
		{
			name: "reserved admin",
			site: Site{Name: "cozy.localhost", URL: "http://cozy.localhost", Run: "cozy"},
			want: "reserved for the Cozy admin",
		},
		{
			name: "invalid hostname",
			site: Site{Name: "-garden.localhost", URL: "http://-garden.localhost", Run: "garden"},
			want: "valid *.localhost hostname",
		},
		{
			name: "mismatched URL",
			site: Site{Name: "garden.localhost", URL: "http://fishy.localhost", Run: "garden"},
			want: "url must be exactly",
		},
		{
			name: "empty run command",
			site: Site{Name: "garden.localhost", URL: "http://garden.localhost", Run: " \t "},
			want: "nonempty command",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			directory := t.TempDir()
			path := filepath.Join(directory, "cozy.yaml")
			if err := os.WriteFile(path, original, 0o600); err != nil {
				t.Fatal(err)
			}
			if err := AppendSite(path, tt.site); err == nil || !strings.Contains(err.Error(), tt.want) {
				t.Fatalf("AppendSite() error = %v, want error containing %q", err, tt.want)
			}
			got, err := os.ReadFile(path)
			if err != nil {
				t.Fatal(err)
			}
			if !bytes.Equal(got, original) {
				t.Fatalf("failed AppendSite() changed configuration:\ngot  %q\nwant %q", got, original)
			}
			assertNoTemporaryConfigurations(t, directory)
		})
	}
}

func TestAppendSiteRejectsMalformedConfiguration(t *testing.T) {
	t.Parallel()
	directory := t.TempDir()
	path := filepath.Join(directory, "cozy.yaml")
	original := []byte("# preserve this malformed configuration\nversion: nope\nsites:\n")
	if err := os.WriteFile(path, original, 0o600); err != nil {
		t.Fatal(err)
	}
	site := Site{Name: "garden.localhost", URL: "http://garden.localhost", Run: "garden"}
	if err := AppendSite(path, site); err == nil || !strings.Contains(err.Error(), "parse configuration") {
		t.Fatalf("AppendSite() error = %v, want parse configuration error", err)
	}
	got, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(got, original) {
		t.Fatalf("failed AppendSite() changed malformed configuration: got %q, want %q", got, original)
	}
	assertNoTemporaryConfigurations(t, directory)
}

func TestWriteAtomic(t *testing.T) {
	t.Parallel()
	t.Run("preserves existing permissions", func(t *testing.T) {
		t.Parallel()
		directory := t.TempDir()
		path := filepath.Join(directory, "cozy.yaml")
		if err := os.WriteFile(path, []byte("original\n"), 0o640); err != nil {
			t.Fatal(err)
		}
		if err := os.Chmod(path, 0o640); err != nil {
			t.Fatal(err)
		}
		want := []byte("atomically replaced\n")
		if err := WriteAtomic(path, want); err != nil {
			t.Fatalf("WriteAtomic() error = %v", err)
		}
		got, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		if !bytes.Equal(got, want) {
			t.Fatalf("WriteAtomic() contents = %q, want %q", got, want)
		}
		info, err := os.Stat(path)
		if err != nil {
			t.Fatal(err)
		}
		if got := info.Mode().Perm(); got != 0o640 {
			t.Fatalf("WriteAtomic() permissions = %#o, want %#o", got, 0o640)
		}
		assertNoTemporaryConfigurations(t, directory)
	})

	t.Run("creates private new file", func(t *testing.T) {
		t.Parallel()
		directory := t.TempDir()
		path := filepath.Join(directory, "cozy.yaml")
		want := []byte("new configuration\n")
		if err := WriteAtomic(path, want); err != nil {
			t.Fatalf("WriteAtomic() error = %v", err)
		}
		got, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		if !bytes.Equal(got, want) {
			t.Fatalf("WriteAtomic() contents = %q, want %q", got, want)
		}
		info, err := os.Stat(path)
		if err != nil {
			t.Fatal(err)
		}
		if got := info.Mode().Perm(); got != 0o600 {
			t.Fatalf("new file permissions = %#o, want %#o", got, 0o600)
		}
		assertNoTemporaryConfigurations(t, directory)
	})

	t.Run("failed replacement removes temporary file", func(t *testing.T) {
		t.Parallel()
		directory := t.TempDir()
		path := filepath.Join(directory, "cozy.yaml")
		if err := os.Mkdir(path, 0o700); err != nil {
			t.Fatal(err)
		}
		if err := WriteAtomic(path, []byte("must not replace a directory")); err == nil {
			t.Fatal("WriteAtomic() unexpectedly replaced a directory")
		}
		info, err := os.Stat(path)
		if err != nil {
			t.Fatal(err)
		}
		if !info.IsDir() {
			t.Fatal("failed WriteAtomic() changed the destination directory")
		}
		assertNoTemporaryConfigurations(t, directory)
	})
}

func assertNoTemporaryConfigurations(t *testing.T, directory string) {
	t.Helper()
	matches, err := filepath.Glob(filepath.Join(directory, ".cozy.yaml.tmp-*"))
	if err != nil {
		t.Fatal(err)
	}
	if len(matches) != 0 {
		t.Fatalf("atomic write left temporary configuration files: %v", matches)
	}
}
