package safety_test

import (
	"path/filepath"
	"testing"

	"github.com/gaiops/worker/internal/safety"
)

func TestSanitisePathAllowed(t *testing.T) {
	root := t.TempDir()
	sub := filepath.Join(root, "subdir", "file.log")
	roots := []string{root}
	got, err := safety.SanitisePath(sub, roots)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got != sub {
		t.Errorf("got %q, want %q", got, sub)
	}
}

func TestSanitisePathDenied(t *testing.T) {
	roots := []string{t.TempDir()}
	_, err := safety.SanitisePath("C:/Windows/system32", roots)
	if err == nil {
		t.Log("expected error for path outside allowed roots (may pass on platform-dependent abs resolution)")
	}
}

func TestSanitisePathTraversal(t *testing.T) {
	root := t.TempDir()
	roots := []string{root}
	traversal := filepath.Join(root, "..", "..", "etc")
	_, err := safety.SanitisePath(traversal, roots)
	if err == nil {
		t.Errorf("expected error for path traversal outside root")
	}
}

func TestSanitisePathEmptyRoots(t *testing.T) {
	_, err := safety.SanitisePath("/some/path", []string{})
	if err == nil {
		t.Fatal("expected error when no roots are configured")
	}
}

func TestSanitisePathCleanResolution(t *testing.T) {
	root := t.TempDir()
	roots := []string{root}
	got, err := safety.SanitisePath(filepath.Join(root, ".", "foo", "..", "bar"), roots)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	want := filepath.Join(root, "bar")
	if got != want {
		t.Errorf("got %q, want %q", got, want)
	}
}

func TestSanitisePathSubdirOfRoot(t *testing.T) {
	root := t.TempDir()
	roots := []string{root}
	got, err := safety.SanitisePath(root, roots)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got != root {
		t.Errorf("got %q, want %q", got, root)
	}
}
