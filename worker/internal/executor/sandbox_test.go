package executor_test

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"testing"
	"time"

	"github.com/gaiops/worker/internal/executor"
	"github.com/gaiops/worker/internal/registry"
)

func TestExecutorUnknownAction(t *testing.T) {
	reg := registry.New()
	exec := executor.New(reg, 5)

	result := exec.Run(context.Background(), "nonexistent", nil)
	if result.Success {
		t.Error("expected failure for unknown action")
	}
	if result.Error == nil || result.Error.Code != "UNKNOWN_ACTION" {
		t.Errorf("Error.Code = %v, want UNKNOWN_ACTION", result.Error)
	}
}

func TestExecutorSuccessfulRun(t *testing.T) {
	reg := registry.New()
	reg.Register(registry.Tool{
		Action:       "test.echo",
		Timeout:      5 * time.Second,
		IsIdempotent: true,
		RiskLevel:    "readonly",
		Execute: func(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
			return map[string]interface{}{"echo": params["msg"]}, nil
		},
	})
	exec := executor.New(reg, 5)

	result := exec.Run(context.Background(), "test.echo", map[string]interface{}{"msg": "hello"})
	if !result.Success {
		t.Fatalf("expected success, got error: %v", result.Error)
	}
	if result.Data["echo"] != "hello" {
		t.Errorf("echo = %v, want hello", result.Data["echo"])
	}
}

func TestExecutorToolError(t *testing.T) {
	reg := registry.New()
	reg.Register(registry.Tool{
		Action:       "test.fail",
		Timeout:      5 * time.Second,
		IsIdempotent: false,
		RiskLevel:    "write",
		Execute: func(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
			return nil, executor.NewErr("CUSTOM_ERROR", "something went wrong")
		},
	})
	exec := executor.New(reg, 5)

	result := exec.Run(context.Background(), "test.fail", nil)
	if result.Success {
		t.Fatal("expected failure")
	}
	if result.Error.Code != "CUSTOM_ERROR" {
		t.Errorf("Error.Code = %q, want CUSTOM_ERROR", result.Error)
	}
	if result.Error.Message != "something went wrong" {
		t.Errorf("Error.Message = %q", result.Error.Message)
	}
}

func TestExecutorTimeout(t *testing.T) {
	reg := registry.New()
	reg.Register(registry.Tool{
		Action:       "test.sleep",
		Timeout:      100 * time.Millisecond,
		IsIdempotent: false,
		RiskLevel:    "write",
		Execute: func(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
			select {
			case <-time.After(5 * time.Second):
				return map[string]interface{}{"done": true}, nil
			case <-ctx.Done():
				return nil, errors.New("cancelled")
			}
		},
	})
	exec := executor.New(reg, 5)

	result := exec.Run(context.Background(), "test.sleep", nil)
	if result.Success {
		t.Fatal("expected timeout failure")
	}
	if result.Error.Code != "EXECUTION_TIMEOUT" {
		t.Errorf("Error.Code = %q, want EXECUTION_TIMEOUT", result.Error)
	}
}

func TestExecutorPanicRecovery(t *testing.T) {
	reg := registry.New()
	reg.Register(registry.Tool{
		Action:       "test.panic",
		Timeout:      5 * time.Second,
		IsIdempotent: false,
		RiskLevel:    "dangerous",
		Execute: func(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
			panic("oops")
		},
	})
	exec := executor.New(reg, 5)

	result := exec.Run(context.Background(), "test.panic", nil)
	if result.Success {
		t.Fatal("expected failure after panic")
	}
	if result.Error.Code != "TOOL_PANIC" {
		t.Errorf("Error.Code = %q, want TOOL_PANIC", result.Error)
	}
}

func TestExecutorConcurrencyLimit(t *testing.T) {
	reg := registry.New()
	reg.Register(registry.Tool{
		Action:       "test.slow",
		Timeout:      10 * time.Second,
		IsIdempotent: true,
		RiskLevel:    "readonly",
		Execute: func(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
			select {
			case <-time.After(500 * time.Millisecond):
				return map[string]interface{}{"done": true}, nil
			case <-ctx.Done():
				return nil, ctx.Err()
			}
		},
	})

	exec := executor.New(reg, 2)
	if max := exec.MaxConcurrent(); max != 2 {
		t.Errorf("MaxConcurrent = %d, want 2", max)
	}

	var wg sync.WaitGroup
	results := make(chan bool, 5)

	// Launch 5 concurrent runs; only 2 should run simultaneously.
	for i := 0; i < 5; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			res := exec.Run(context.Background(), "test.slow", nil)
			results <- res.Success
		}()
	}

	wg.Wait()
	close(results)

	successCount := 0
	for s := range results {
		if s {
			successCount++
		}
	}
	if successCount != 5 {
		t.Errorf("expected 5 successes, got %d", successCount)
	}
}

func TestExecutorConcurrencySlotCancelled(t *testing.T) {
	reg := registry.New()
	reg.Register(registry.Tool{
		Action:       "test.hold",
		Timeout:      10 * time.Second,
		IsIdempotent: false,
		RiskLevel:    "write",
		Execute: func(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
			<-ctx.Done()
			return nil, ctx.Err()
		},
	})

	exec := executor.New(reg, 1)
	// Fill the single slot.
	ctx1, cancel1 := context.WithCancel(context.Background())
	defer cancel1()

	ch := make(chan struct{})
	go func() {
		exec.Run(ctx1, "test.hold", nil)
		close(ch)
	}()

	time.Sleep(50 * time.Millisecond) // let goroutine acquire slot

	// This one should block until ctx2 is cancelled.
	ctx2, cancel2 := context.WithCancel(context.Background())
	go func() {
		time.Sleep(100 * time.Millisecond)
		cancel2()
	}()

	result := exec.Run(ctx2, "test.hold", nil)
	if result.Success {
		t.Fatal("expected failure after context cancellation")
	}
	if result.Error.Code != "EXECUTION_TIMEOUT" {
		t.Errorf("Error.Code = %q, want EXECUTION_TIMEOUT", result.Error)
	}
	fmt.Println(result.Error.Message)
}

func TestExecutorMaxConcurrentDefault(t *testing.T) {
	reg := registry.New()
	exec := executor.New(reg, 0)
	if max := exec.MaxConcurrent(); max != 5 {
		t.Errorf("MaxConcurrent = %d, want 5", max)
	}
}
