package reporter_test

import (
	"context"
	"sync/atomic"
	"testing"
	"time"

	"github.com/gaiops/worker/internal/reporter"
	"github.com/gaiops/worker/pkg/envelope"
)

func TestNewReporter(t *testing.T) {
	r := reporter.New(30, 10, func(env *envelope.Envelope) {})
	if r == nil {
		t.Fatal("expected non-nil reporter")
	}
	s := r.Snapshot()
	if s.ToolCount != 10 {
		t.Errorf("ToolCount = %d, want 10", s.ToolCount)
	}
}

func TestReporterDefaultInterval(t *testing.T) {
	r := reporter.New(0, 5, func(env *envelope.Envelope) {})
	if r == nil {
		t.Fatal("expected non-nil reporter")
	}
}

func TestRecordExecutions(t *testing.T) {
	r := reporter.New(30, 5, func(env *envelope.Envelope) {})

	r.RecordExecution(true, false, false)
	r.RecordExecution(false, false, false)
	r.RecordExecution(false, true, false)
	r.RecordExecution(false, false, true)
	r.RecordExecution(true, false, false)

	s := r.Snapshot()
	if s.TotalExecutions != 5 {
		t.Errorf("TotalExecutions = %d, want 5", s.TotalExecutions)
	}
	if s.SuccessCount != 2 {
		t.Errorf("SuccessCount = %d, want 2", s.SuccessCount)
	}
	if s.FailureCount != 1 {
		t.Errorf("FailureCount = %d, want 1", s.FailureCount)
	}
	if s.PanicCount != 1 {
		t.Errorf("PanicCount = %d, want 1", s.PanicCount)
	}
	if s.TimeoutCount != 1 {
		t.Errorf("TimeoutCount = %d, want 1", s.TimeoutCount)
	}
}

func TestSnapshotIncludesUptime(t *testing.T) {
	r := reporter.New(30, 3, func(env *envelope.Envelope) {})
	time.Sleep(1100 * time.Millisecond)
	s := r.Snapshot()
	if s.UptimeSeconds < 1 {
		t.Errorf("UptimeSeconds should be >= 1, got %d", s.UptimeSeconds)
	}
}

func TestStartSendsHeartbeat(t *testing.T) {
	var sent atomic.Int64
	sendFn := func(env *envelope.Envelope) {
		if env.MsgType == envelope.MsgHeartbeat {
			sent.Add(1)
		}
	}

	r := reporter.New(1, 5, sendFn)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	go r.Start(ctx)

	time.Sleep(1500 * time.Millisecond)
	cancel()

	n := sent.Load()
	if n == 0 {
		t.Error("expected at least one heartbeat to be sent")
	}
}

func TestHealthReportSnapshot(t *testing.T) {
	r := reporter.New(30, 7, func(env *envelope.Envelope) {})
	r.RecordExecution(true, false, false)

	s := r.Snapshot()
	if s.TotalExecutions != 1 {
		t.Errorf("TotalExecutions = %d, want 1", s.TotalExecutions)
	}
}
