package connection

import (
	"math"
	"math/rand"
	"time"
)

// ReconnectPolicy implements jittered exponential backoff.
//
// BaseDelay → ×2 each attempt → capped at MaxDelay → jitter ±50%.
type ReconnectPolicy struct {
	baseDelay time.Duration
	maxDelay  time.Duration
}

func NewReconnectPolicy(baseSec, maxSec int) *ReconnectPolicy {
	if baseSec <= 0 {
		baseSec = 1
	}
	if maxSec <= 0 {
		maxSec = 60
	}
	return &ReconnectPolicy{
		baseDelay: time.Duration(baseSec) * time.Second,
		maxDelay:  time.Duration(maxSec) * time.Second,
	}
}

// Delay returns the sleep duration for the n-th reconnection attempt (0-indexed).
func (p *ReconnectPolicy) Delay(attempt int) time.Duration {
	// exponential: base * 2^attempt
	exp := float64(p.baseDelay) * math.Pow(2, float64(attempt))
	if exp > float64(p.maxDelay) {
		exp = float64(p.maxDelay)
	}
	// jitter: random [0.5, 1.5) * exp
	jitter := exp * (0.5 + rand.Float64())
	return time.Duration(jitter)
}
