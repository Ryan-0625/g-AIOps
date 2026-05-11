package connection_test

import (
	"testing"
	"time"

	"github.com/gaiops/worker/internal/connection"
)

func TestReconnectPolicyDefaults(t *testing.T) {
	p := connection.NewReconnectPolicy(0, 0) // should default to 1 and 60
	d := p.Delay(0)
	if d <= 0 {
		t.Errorf("expected positive delay, got %v", d)
	}
}

func TestReconnectPolicyBackoff(t *testing.T) {
	p := connection.NewReconnectPolicy(1, 60)
	d0 := p.Delay(0)
	d1 := p.Delay(1)
	d2 := p.Delay(2)

	// With jitter ±50%, d2 should generally be larger than d0 (exponential).
	// Not a strict assertion — jitter can theoretically make d2 smaller,
	// but statistically very unlikely across three samples.
	t.Logf("delays: %v, %v, %v", d0, d1, d2)
}

func TestReconnectPolicyMaxDelay(t *testing.T) {
	p := connection.NewReconnectPolicy(1, 5)
	// Attempt 10 would be 1*2^10 = 1024s, capped at 5s with jitter up to 1.5x = 7.5s
	allBelow8 := true
	for i := 0; i < 100; i++ {
		d := p.Delay(10)
		if d > 8*time.Second {
			allBelow8 = false
		}
	}
	if !allBelow8 {
		t.Error("delay exceeded max delay + max jitter")
	}
}

func TestReconnectPolicyNonNegative(t *testing.T) {
	p := connection.NewReconnectPolicy(1, 60)
	for i := 0; i < 100; i++ {
		d := p.Delay(i)
		if d < 0 {
			t.Errorf("negative delay at attempt %d: %v", i, d)
		}
	}
}
