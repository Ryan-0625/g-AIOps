package connection_test

import (
	"net/http"
	"testing"

	"github.com/gaiops/worker/internal/connection"
)

func TestAuthApplySetsHeader(t *testing.T) {
	a := connection.NewAuth("s3cr3t")
	var h http.Header = make(http.Header)
	a.Apply(&h)
	if h.Get("Authorization") != "Bearer s3cr3t" {
		t.Errorf("Authorization = %q, want Bearer s3cr3t", h.Get("Authorization"))
	}
}

func TestAuthValidateEmpty(t *testing.T) {
	a := connection.NewAuth("")
	if err := a.Validate(); err == nil {
		t.Error("expected error for empty token")
	}
}

func TestAuthValidateValid(t *testing.T) {
	a := connection.NewAuth("valid-token")
	if err := a.Validate(); err != nil {
		t.Errorf("unexpected error: %v", err)
	}
}
