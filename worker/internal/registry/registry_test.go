package registry_test

import (
	"context"
	"fmt"
	"sync"
	"testing"
	"time"

	"github.com/gaiops/worker/internal/registry"
)

func TestRegisterAndLookup(t *testing.T) {
	r := registry.New()
	r.Register(registry.Tool{
		Action:       "ping.icmp",
		Timeout:      10 * time.Second,
		IsIdempotent: true,
		RiskLevel:    "readonly",
		Execute:      func(_ context.Context, _ map[string]interface{}) (map[string]interface{}, error) { return nil, nil },
	})

	tool, ok := r.Lookup("ping.icmp")
	if !ok {
		t.Fatal("expected to find ping.icmp")
	}
	if tool.Action != "ping.icmp" {
		t.Errorf("Action = %q, want ping.icmp", tool.Action)
	}
	if tool.Timeout != 10*time.Second {
		t.Errorf("Timeout = %v, want 10s", tool.Timeout)
	}
	if !tool.IsIdempotent {
		t.Error("IsIdempotent should be true")
	}
	if tool.RiskLevel != "readonly" {
		t.Errorf("RiskLevel = %q, want readonly", tool.RiskLevel)
	}
}

func TestRegisterPanicOnDuplicate(t *testing.T) {
	defer func() {
		if r := recover(); r == nil {
			t.Fatal("expected panic on duplicate registration")
		}
	}()
	r := registry.New()
	r.Register(registry.Tool{Action: "dup.tool", Execute: nopExec})
	r.Register(registry.Tool{Action: "dup.tool", Execute: nopExec})
}

func TestRegisterDefaultsZeroValues(t *testing.T) {
	r := registry.New()
	r.Register(registry.Tool{Action: "no.timeout", Execute: nopExec})

	tool, ok := r.Lookup("no.timeout")
	if !ok {
		t.Fatal("expected to find no.timeout")
	}
	if tool.Timeout != 30*time.Second {
		t.Errorf("default Timeout = %v, want 30s", tool.Timeout)
	}
	if tool.RiskLevel != "readonly" {
		t.Errorf("default RiskLevel = %q, want readonly", tool.RiskLevel)
	}
}

func TestRegisterDynamicReplacesExisting(t *testing.T) {
	r := registry.New()
	r.Register(registry.Tool{Action: "dynamic.test", Execute: nopExec})
	r.RegisterDynamic(registry.Tool{Action: "dynamic.test", Execute: nopExec, RiskLevel: "write"})

	tool, ok := r.Lookup("dynamic.test")
	if !ok {
		t.Fatal("expected to find dynamic.test after replacement")
	}
	if tool.RiskLevel != "write" {
		t.Errorf("RiskLevel after RegisterDynamic = %q, want write", tool.RiskLevel)
	}
}

func TestRegisterDynamicDefaults(t *testing.T) {
	r := registry.New()
	r.RegisterDynamic(registry.Tool{Action: "dynamic.defaults", Execute: nopExec})

	tool, ok := r.Lookup("dynamic.defaults")
	if !ok {
		t.Fatal("expected to find dynamic.defaults")
	}
	if tool.Timeout != 30*time.Second {
		t.Errorf("default Timeout = %v, want 30s", tool.Timeout)
	}
	if tool.RiskLevel != "readonly" {
		t.Errorf("default RiskLevel = %q, want readonly", tool.RiskLevel)
	}
}

func TestUnregisterRemovesTool(t *testing.T) {
	r := registry.New()
	r.Register(registry.Tool{Action: "temp.tool", Execute: nopExec})
	if _, ok := r.Lookup("temp.tool"); !ok {
		t.Fatal("expected to find before unregister")
	}

	r.Unregister("temp.tool")
	if _, ok := r.Lookup("temp.tool"); ok {
		t.Error("expected not to find after unregister")
	}
}

func TestUnregisterNonExistentNoOp(t *testing.T) {
	r := registry.New()
	r.Unregister("nonexistent") // should not panic
}

func TestListReturnsRegisteredTools(t *testing.T) {
	r := registry.New()
	r.Register(registry.Tool{Action: "tool.a", Execute: nopExec})
	r.Register(registry.Tool{Action: "tool.b", Execute: nopExec})

	list := r.List()
	if len(list) != 2 {
		t.Fatalf("List() returned %d tools, want 2", len(list))
	}
	actions := make(map[string]bool)
	for _, tl := range list {
		actions[tl.Action] = true
	}
	if !actions["tool.a"] || !actions["tool.b"] {
		t.Error("List() missing expected tools")
	}
}

func TestActionsReturnsNames(t *testing.T) {
	r := registry.New()
	r.Register(registry.Tool{Action: "alpha", Execute: nopExec})
	r.Register(registry.Tool{Action: "beta", Execute: nopExec})

	actions := r.Actions()
	if len(actions) != 2 {
		t.Fatalf("Actions() = %v, want 2 entries", actions)
	}
	seen := make(map[string]bool)
	for _, a := range actions {
		seen[a] = true
	}
	if !seen["alpha"] || !seen["beta"] {
		t.Error("Actions() missing expected actions")
	}
}

func TestRiskLevels(t *testing.T) {
	r := registry.New()
	r.Register(registry.Tool{Action: "read.only", RiskLevel: "readonly", Execute: nopExec})
	r.Register(registry.Tool{Action: "danger.zone", RiskLevel: "dangerous", Execute: nopExec})

	levels := r.RiskLevels()
	if levels["read.only"] != "readonly" {
		t.Errorf("RiskLevels['read.only'] = %q, want readonly", levels["read.only"])
	}
	if levels["danger.zone"] != "dangerous" {
		t.Errorf("RiskLevels['danger.zone'] = %q, want dangerous", levels["danger.zone"])
	}
}

func TestGlobalRegistryNotNil(t *testing.T) {
	if registry.Global == nil {
		t.Fatal("Global registry is nil")
	}
}

func TestConcurrentRegistryAccess(t *testing.T) {
	r := registry.New()
	var wg sync.WaitGroup
	n := 50

	for i := 0; i < n; i++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			action := fmt.Sprintf("conc.tool.%d", idx)
			r.Register(registry.Tool{Action: action, Execute: nopExec})
		}(i)
	}
	wg.Wait()

	actions := r.Actions()
	if len(actions) != n {
		t.Errorf("expected %d actions after concurrent register, got %d", n, len(actions))
	}
}

func TestConcurrentRegisterAndLookup(t *testing.T) {
	r := registry.New()
	r.Register(registry.Tool{Action: "shared.tool", Execute: nopExec})

	var wg sync.WaitGroup
	for i := 0; i < 20; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < 100; j++ {
				r.Lookup("shared.tool")
				r.Actions()
				r.List()
				r.RiskLevels()
			}
		}()
	}
	wg.Wait()
}

func TestSourceFieldDefault(t *testing.T) {
	r := registry.New()
	r.Register(registry.Tool{Action: "no.source", Execute: nopExec})

	tool, ok := r.Lookup("no.source")
	if !ok {
		t.Fatal("expected to find no.source")
	}
	_ = tool // Source defaults to "" which is fine — builtin tools omit it
}

var nopExec = func(_ context.Context, _ map[string]interface{}) (map[string]interface{}, error) {
	return nil, nil
}
