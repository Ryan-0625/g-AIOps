package safety

import (
	"fmt"
	"path/filepath"
	"strings"
)

// SanitisePath resolves a requested path against a list of allowed roots.
// Returns an error if the path is outside any allowed root.
func SanitisePath(requested string, allowedRoots []string) (string, error) {
	clean := filepath.Clean(requested)
	abs, err := filepath.Abs(clean)
	if err != nil {
		return "", fmt.Errorf("cannot resolve path %q: %w", requested, err)
	}

	for _, root := range allowedRoots {
		rootAbs, err := filepath.Abs(root)
		if err != nil {
			continue
		}
		if strings.HasPrefix(abs, rootAbs) {
			return abs, nil
		}
	}
	return "", fmt.Errorf("path %q is not allowed (outside permitted roots)", requested)
}
