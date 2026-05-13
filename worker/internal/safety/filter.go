package safety

import "regexp"

// sensitivePatterns matches common credential and secret formats in tool output.
// Each pattern captures the field name (group 1) so the replacement preserves
// the label while redacting the value.
var sensitivePatterns = []*regexp.Regexp{
	// Generic key=value credentials
	regexp.MustCompile(`(?i)(password|passwd|pwd|secret|token|api[_-]?key|api_secret|app[_-]?secret|auth_token|refresh_token|access_token|secret_key|private_key)\s*[:=]\s*\S+`),
	// HTTP Authorization header
	regexp.MustCompile(`(?i)(authorization|Bearer|Authorization)\s*[:=]\s*\S+`),
	// AWS credentials
	regexp.MustCompile(`(?i)(aws_access_key_id|aws_secret_access_key|aws_session_token)\s*[:=]\s*\S+`),
	// Cloud provider keys: sk-... (OpenAI/DeepSeek), ghp_... (GitHub), etc.
	regexp.MustCompile(`(?i)(sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{36,}|gho_[a-zA-Z0-9]{36,}|ghu_[a-zA-Z0-9]{36,}|github_pat_[a-zA-Z0-9_]{50,})`),
	// JWT tokens (base64url-encoded triple)
	regexp.MustCompile(`eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}`),
	// Database connection strings
	regexp.MustCompile(`(?i)(mongodb(?:\+srv)?://|mysql://|postgres(?:ql)?://|redis://|rediss://)([^\s]{3,50}):([^\s]{3,50})@`),
	// Private keys — all known formats
	regexp.MustCompile(`-----BEGIN\s+(RSA|EC|DSA|OPENSSH|PGP|PRIVATE)\s+KEY\s*(BLOCK)?-----`),
	// xox[baprs]-... Slack tokens
	regexp.MustCompile(`xox[baprs]-[a-zA-Z0-9-]{10,}`),
}

// FilterSensitive replaces credentials and secret material in text with
// a fixed placeholder. Applied by exec.run and log.tail before returning
// results to the caller.
func FilterSensitive(data string) string {
	for _, pat := range sensitivePatterns {
		data = pat.ReplaceAllString(data, "${1}: ***FILTERED***")
	}
	return data
}

// IsSecretEnvVar returns true if the environment variable name suggests it
// carries sensitive material. Used to filter env vars passed to sub-processes.
func IsSecretEnvVar(name string) bool {
	secretPatterns := []*regexp.Regexp{
		regexp.MustCompile(`(?i)(token|secret|password|passwd|pwd|key|cert|credential|auth)`),
		regexp.MustCompile(`(?i)(CLUSTER_TOKEN|OPENAI_API_KEY|AWS_SECRET|AWS_ACCESS)`),
	}
	upper := name
	for _, pat := range secretPatterns {
		if pat.MatchString(upper) {
			return true
		}
	}
	return false
}
