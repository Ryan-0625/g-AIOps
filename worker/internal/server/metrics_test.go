package server

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gaiops/worker/internal/reporter"
)

func TestMetricsHandlerNoReporter(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	w := httptest.NewRecorder()
	MetricsHandler(w, req)
	resp := w.Result()
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusServiceUnavailable {
		t.Fatalf("expected 503 without reporter, got %d", resp.StatusCode)
	}
}

func TestMetricsHandlerMethodNotAllowed(t *testing.T) {
	req := httptest.NewRequest(http.MethodPost, "/metrics", nil)
	w := httptest.NewRecorder()
	MetricsHandler(w, req)
	resp := w.Result()
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusMethodNotAllowed {
		t.Fatalf("expected 405 for POST, got %d", resp.StatusCode)
	}
}

func TestMetricsHandlerWithReporter(t *testing.T) {
	sendFn := func(*envelope.Envelope) {}
	rep := reporter.New(30, 8, sendFn, nil)

	// Simulate some executions.
	rep.RecordExecution(true, false, false)
	rep.RecordExecution(false, false, false)
	rep.RecordExecution(false, true, false)
	rep.RecordExecution(false, false, true)

	SetMetricsReporter(rep)
	defer func() {
		metricsMu.Lock()
		metricsReporter = nil
		metricsMu.Unlock()
	}()

	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	w := httptest.NewRecorder()
	MetricsHandler(w, req)
	resp := w.Result()
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", resp.StatusCode)
	}

	body := w.Body.String()
	if !strings.Contains(body, "gaiops_worker_total_executions") {
		t.Fatal("missing total_executions metric")
	}
	if !strings.Contains(body, "gaiops_worker_uptime_seconds") {
		t.Fatal("missing uptime_seconds metric")
	}
	if !strings.Contains(body, "# TYPE") {
		t.Fatal("missing TYPE annotations")
	}
}
