package safety_test

import (
	"testing"

	"github.com/gaiops/worker/internal/safety"
)

func TestTruncateOutputUnderLimit(t *testing.T) {
	data := []byte("hello world")
	truncated, size, was := safety.TruncateOutput(data)
	if was {
		t.Error("unexpected truncation")
	}
	if size != int64(len(data)) {
		t.Errorf("size = %d, want %d", size, len(data))
	}
	if string(truncated) != "hello world" {
		t.Errorf("truncated = %q", string(truncated))
	}
}

func TestTruncateOutputOverLimit(t *testing.T) {
	data := make([]byte, safety.MaxOutputSize+100)
	for i := range data {
		data[i] = 'x'
	}
	truncated, size, was := safety.TruncateOutput(data)
	if !was {
		t.Error("expected truncation")
	}
	if size != int64(len(data)) {
		t.Errorf("size = %d, want %d", size, len(data))
	}
	if len(truncated) != safety.MaxOutputSize {
		t.Errorf("truncated len = %d, want %d", len(truncated), safety.MaxOutputSize)
	}
}

func TestTruncateOutputAtExactLimit(t *testing.T) {
	data := make([]byte, safety.MaxOutputSize)
	_, _, was := safety.TruncateOutput(data)
	if was {
		t.Error("expected no truncation at exact limit")
	}
}

func TestTruncateOutputEmpty(t *testing.T) {
	truncated, size, was := safety.TruncateOutput([]byte{})
	if was {
		t.Error("unexpected truncation for empty")
	}
	if size != 0 {
		t.Errorf("size = %d, want 0", size)
	}
	if len(truncated) != 0 {
		t.Error("expected empty output")
	}
}

func TestTruncateErrorRawUnderLimit(t *testing.T) {
	raw, size, was := safety.TruncateErrorRaw("short error")
	if was {
		t.Error("unexpected truncation")
	}
	if size != int64(len("short error")) {
		t.Errorf("size = %d", size)
	}
	if raw != "short error" {
		t.Errorf("raw = %q", raw)
	}
}

func TestTruncateErrorRawOverLimit(t *testing.T) {
	raw := make([]byte, safety.MaxErrorRawSize+50)
	for i := range raw {
		raw[i] = 'e'
	}
	r, size, was := safety.TruncateErrorRaw(string(raw))
	if !was {
		t.Error("expected truncation")
	}
	if size != int64(len(raw)) {
		t.Errorf("size = %d, want %d", size, len(raw))
	}
	if len(r) != safety.MaxErrorRawSize {
		t.Errorf("truncated len = %d, want %d", len(r), safety.MaxErrorRawSize)
	}
}
