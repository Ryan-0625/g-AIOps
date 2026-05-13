package server

import (
	"fmt"
	"net/http"
	"sync"

	"github.com/gaiops/worker/internal/reporter"
)

var (
	metricsReporter *reporter.Reporter
	metricsMu       sync.RWMutex
)

// SetMetricsReporter registers the reporter for /metrics exposure.
func SetMetricsReporter(r *reporter.Reporter) {
	metricsMu.Lock()
	defer metricsMu.Unlock()
	metricsReporter = r
}

// MetricsHandler responds with Prometheus-format metrics.
func MetricsHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.WriteHeader(http.StatusMethodNotAllowed)
		return
	}

	metricsMu.RLock()
	rep := metricsReporter
	metricsMu.RUnlock()

	if rep == nil {
		w.WriteHeader(http.StatusServiceUnavailable)
		fmt.Fprint(w, "# reporter not initialized\n")
		return
	}

	s := rep.Snapshot()

	w.Header().Set("Content-Type", "text/plain; charset=utf-8")

	fmt.Fprint(w, "# HELP gaiops_worker_total_executions Total tool executions\n")
	fmt.Fprint(w, "# TYPE gaiops_worker_total_executions counter\n")
	fmt.Fprintf(w, "gaiops_worker_total_executions %d\n", s.TotalExecutions)

	fmt.Fprint(w, "# HELP gaiops_worker_success_count Successful tool executions\n")
	fmt.Fprint(w, "# TYPE gaiops_worker_success_count counter\n")
	fmt.Fprintf(w, "gaiops_worker_success_count %d\n", s.SuccessCount)

	fmt.Fprint(w, "# HELP gaiops_worker_failure_count Failed tool executions\n")
	fmt.Fprint(w, "# TYPE gaiops_worker_failure_count counter\n")
	fmt.Fprintf(w, "gaiops_worker_failure_count %d\n", s.FailureCount)

	fmt.Fprint(w, "# HELP gaiops_worker_panic_count Panicked tool executions\n")
	fmt.Fprint(w, "# TYPE gaiops_worker_panic_count counter\n")
	fmt.Fprintf(w, "gaiops_worker_panic_count %d\n", s.PanicCount)

	fmt.Fprint(w, "# HELP gaiops_worker_timeout_count Timed-out tool executions\n")
	fmt.Fprint(w, "# TYPE gaiops_worker_timeout_count counter\n")
	fmt.Fprintf(w, "gaiops_worker_timeout_count %d\n", s.TimeoutCount)

	fmt.Fprint(w, "# HELP gaiops_worker_uptime_seconds Process uptime\n")
	fmt.Fprint(w, "# TYPE gaiops_worker_uptime_seconds gauge\n")
	fmt.Fprintf(w, "gaiops_worker_uptime_seconds %d\n", s.UptimeSeconds)

	fmt.Fprint(w, "# HELP gaiops_worker_tool_count Registered tools\n")
	fmt.Fprint(w, "# TYPE gaiops_worker_tool_count gauge\n")
	fmt.Fprintf(w, "gaiops_worker_tool_count %d\n", s.ToolCount)
}
