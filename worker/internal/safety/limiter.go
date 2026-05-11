// Package safety provides output truncation, sensitive-data filtering, and
// path sanitisation shared across tools.
package safety

const (
	MaxOutputSize   = 1 * 1024 * 1024  // 1 MB — payload.data
	MaxErrorRawSize = 100 * 1024       // 100 KB — payload.error.raw
)

// TruncateOutput checks if data exceeds MaxOutputSize and returns a
// truncated copy along with the original size.
func TruncateOutput(data []byte) (truncated []byte, originalSize int64, wasTruncated bool) {
	n := len(data)
	if int64(n) <= MaxOutputSize {
		return data, int64(n), false
	}
	return data[:MaxOutputSize], int64(n), true
}

// TruncateErrorRaw checks if raw exceeds MaxErrorRawSize.
func TruncateErrorRaw(raw string) (string, int64, bool) {
	n := len(raw)
	if int64(n) <= MaxErrorRawSize {
		return raw, int64(n), false
	}
	return raw[:MaxErrorRawSize], int64(n), true
}
