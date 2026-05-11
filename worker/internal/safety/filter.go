package safety

import "regexp"

// Sensitive patterns that must be filtered from tool output.
var sensitivePatterns = []*regexp.Regexp{
	regexp.MustCompile(`(?i)(password|passwd|secret|token|api[_-]?key)\s*[:=]\s*\S+`),
	regexp.MustCompile(`(?i)-----BEGIN\s+(RSA|EC|OPENSSH)\s+PRIVATE\s+KEY-----`),
}

// FilterSensitive replaces credentials and secret material in text with
// a fixed placeholder. Applied by exec.run and log.tail before returning.
func FilterSensitive(data string) string {
	for _, pat := range sensitivePatterns {
		data = pat.ReplaceAllString(data, "${1}: ***FILTERED***")
	}
	return data
}
