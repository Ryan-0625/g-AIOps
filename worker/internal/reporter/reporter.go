// Package reporter collects execution metrics and periodically reports health
// status to Master. Each Worker has one Reporter instance that gathers tool
// execution results and sends summary envelopes at a configurable interval.
package reporter

import (
	"context"
	"log"
	"sync"
	"sync/atomic"
	"time"

	"github.com/gaiops/worker/pkg/envelope"
)

// Stats accumulates tool execution counters.
type Stats struct {
	TotalExecutions int64
	SuccessCount    int64
	FailureCount    int64
	PanicCount      int64
	TimeoutCount    int64
}

// Snapshot is an immutable copy of Stats at a point in time.
type Snapshot struct {
	TotalExecutions int64
	SuccessCount    int64
	FailureCount    int64
	PanicCount      int64
	TimeoutCount    int64
	UptimeSeconds   int64
	ToolCount       int
}

// Reporter periodically pushes health/status snapshots to Master.
type Reporter struct {
	interval time.Duration

	mu         sync.Mutex
	toolCount  int
	startedAt  time.Time

	// atomic counters
	totalExecs atomic.Int64
	successes  atomic.Int64
	failures   atomic.Int64
	panics     atomic.Int64
	timeouts   atomic.Int64

	// sendFn is called to deliver an envelope to Master.
	sendFn func(*envelope.Envelope)
}

// New creates a Reporter. sendFn is called in a background goroutine each
// interval to deliver the status envelope. If intervalSec is <= 0, 30s is used.
func New(intervalSec int, toolCount int, sendFn func(*envelope.Envelope)) *Reporter {
	if intervalSec <= 0 {
		intervalSec = 30
	}
	return &Reporter{
		interval:  time.Duration(intervalSec) * time.Second,
		toolCount: toolCount,
		startedAt: time.Now(),
		sendFn:    sendFn,
	}
}

// RecordExecution records a tool execution outcome. Thread-safe.
func (r *Reporter) RecordExecution(success, panicked, timedOut bool) {
	r.totalExecs.Add(1)
	if panicked {
		r.panics.Add(1)
	} else if timedOut {
		r.timeouts.Add(1)
	} else if success {
		r.successes.Add(1)
	} else {
		r.failures.Add(1)
	}
}

// Snapshot returns a point-in-time copy of all counters.
func (r *Reporter) Snapshot() Snapshot {
	return Snapshot{
		TotalExecutions: r.totalExecs.Load(),
		SuccessCount:    r.successes.Load(),
		FailureCount:    r.failures.Load(),
		PanicCount:      r.panics.Load(),
		TimeoutCount:    r.timeouts.Load(),
		UptimeSeconds:   int64(time.Since(r.startedAt).Seconds()),
		ToolCount:       r.toolCount,
	}
}

// healthReport builds a status envelope from current counters.
func (r *Reporter) healthReport() *envelope.Envelope {
	s := r.Snapshot()
	return &envelope.Envelope{
		ProtoVersion: "1.0",
		MsgID:        healthMsgID(),
		MsgType:      envelope.MsgHeartbeat,
		Timestamp:    time.Now().Unix(),
		Source:       envelope.RoleWorker,
		Target:       envelope.RoleMaster,
		Payload: envelope.Payload{
			Action: "worker.heartbeat",
			Status: envelope.StatusSuccess,
			Params: map[string]interface{}{
				"total_executions": s.TotalExecutions,
				"success_count":    s.SuccessCount,
				"failure_count":    s.FailureCount,
				"panic_count":      s.PanicCount,
				"timeout_count":    s.TimeoutCount,
				"uptime_seconds":   s.UptimeSeconds,
				"tool_count":       s.ToolCount,
			},
		},
	}
}

// Start begins the periodic reporting loop. Blocks until ctx is cancelled.
func (r *Reporter) Start(ctx context.Context) {
	ticker := time.NewTicker(r.interval)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			env := r.healthReport()
			r.sendFn(env)
		case <-ctx.Done():
			log.Println("reporter: stopping")
			return
		}
	}
}

var healthMsgCounter int64

func healthMsgID() string {
	c := atomic.AddInt64(&healthMsgCounter, 1)
	return "hb-" + time.Now().Format("150405") + "-" + itoa(c)
}

func itoa(n int64) string {
	if n == 0 {
		return "0"
	}
	var buf [20]byte
	i := len(buf)
	for n > 0 {
		i--
		buf[i] = byte('0' + n%10)
		n /= 10
	}
	return string(buf[i:])
}
