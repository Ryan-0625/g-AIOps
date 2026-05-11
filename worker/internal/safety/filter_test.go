package safety_test

import (
	"testing"

	"github.com/gaiops/worker/internal/safety"
)

func TestFilterSensitivePassword(t *testing.T) {
	input := "password=supersecret"
	got := safety.FilterSensitive(input)
	if got != "password: ***FILTERED***" {
		t.Errorf("got %q", got)
	}
}

func TestFilterSensitiveSecret(t *testing.T) {
	input := "secret: my-token-here"
	got := safety.FilterSensitive(input)
	if got != "secret: ***FILTERED***" {
		t.Errorf("got %q", got)
	}
}

func TestFilterSensitiveAPIKey(t *testing.T) {
	input := "api_key=abc123def456"
	got := safety.FilterSensitive(input)
	if got != "api_key: ***FILTERED***" {
		t.Errorf("got %q", got)
	}
}

func TestFilterSensitiveCaseInsensitive(t *testing.T) {
	input := "PASSWORD=topsecret"
	got := safety.FilterSensitive(input)
	if got != "PASSWORD: ***FILTERED***" {
		t.Errorf("got %q", got)
	}
}

func TestFilterSensitivePrivateKey(t *testing.T) {
	input := "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA..."
	got := safety.FilterSensitive(input)
	if got != "RSA: ***FILTERED***\nMIIEpAIBAAKCAQEA..." {
		t.Errorf("got %q", got)
	}
}

func TestFilterSensitiveNoMatch(t *testing.T) {
	input := "this is a normal log line without secrets"
	got := safety.FilterSensitive(input)
	if got != input {
		t.Errorf("got %q, want unchanged", got)
	}
}

func TestFilterSensitiveEmpty(t *testing.T) {
	got := safety.FilterSensitive("")
	if got != "" {
		t.Errorf("expected empty, got %q", got)
	}
}

func TestFilterSensitiveMixedContent(t *testing.T) {
	input := "user=jdoe password=hunter2 role=admin"
	got := safety.FilterSensitive(input)
	if got != "user=jdoe password: ***FILTERED*** role=admin" {
		t.Errorf("got %q", got)
	}
}
