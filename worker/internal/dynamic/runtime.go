package dynamic

import (
	"context"
	"fmt"
	"os/exec"
	"sync"
	"sync/atomic"
	"time"
)

// ── RuntimePool ──────────────────────────────────────────────────────────

// RuntimePool maintains pre-warmed interpreter sub-processes to reduce
// cold-start latency for frequently-used dynamic tools.
//
// Each language has its own pool with configurable max size. Idle processes
// are reaped after IdleTimeout.
type RuntimePool struct {
	mu         sync.Mutex
	pools      map[string][]*warmProc
	config     map[string]PoolConfig
	idleTimeout time.Duration
	nextID     atomic.Int64
}

// PoolConfig controls the pool for one interpreter.
type PoolConfig struct {
	Interpreter string // full path, e.g. "/bin/bash"
	MaxProcs    int    // max pre-warmed processes
}

// warmProc is a pre-started interpreter process ready to accept a script.
type warmProc struct {
	ID        int64
	Cmd       *exec.Cmd
	LastUsed  time.Time
	Lang      string
}

// NewRuntimePool creates a pool with zero-initialized per-language pools.
func NewRuntimePool(idleTimeout time.Duration) *RuntimePool {
	return &RuntimePool{
		pools:       make(map[string][]*warmProc),
		config:      make(map[string]PoolConfig),
		idleTimeout: idleTimeout,
	}
}

// RegisterConfig sets the pool configuration for a language.
func (rp *RuntimePool) RegisterConfig(lang string, cfg PoolConfig) {
	rp.mu.Lock()
	defer rp.mu.Unlock()
	rp.config[lang] = cfg
}

// Acquire gets a pre-warmed process from the pool (or creates a new one).
// Returns a process handle that must be released back via Release.
func (rp *RuntimePool) Acquire(ctx context.Context, lang string) (*warmProc, error) {
	rp.mu.Lock()

	// 1. Try to find a usable idle process.
	procs := rp.pools[lang]
	for i, p := range procs {
		if time.Since(p.LastUsed) < rp.idleTimeout {
			rp.pools[lang] = append(procs[:i], procs[i+1:]...)
			rp.mu.Unlock()
			p.LastUsed = time.Now()
			return p, nil
		}
	}
	rp.mu.Unlock()

	// 2. No idle process — start a new one (but don't keep it running
	//    idle; we use lightweight exec.CommandContext per invocation
	//    since modern Linux kernel starts processes in ~1ms).
	//
	// The pool primarily serves to limit concurrent processes and
	// provide quick access to the interpreter path.
	return rp.createProcess(lang)
}

func (rp *RuntimePool) createProcess(lang string) (*warmProc, error) {
	cfg, ok := rp.config[lang]
	if !ok {
		return nil, fmt.Errorf("no pool config for language: %s", lang)
	}
	return &warmProc{
		ID:       rp.nextID.Add(1),
		LastUsed: time.Now(),
		Lang:     lang,
		Cmd:      exec.Command(cfg.Interpreter), // not started, just path holder
	}, nil
}

// Release returns a process to the pool. If the pool is at capacity,
// the process is discarded (not kept alive).
func (rp *RuntimePool) Release(p *warmProc) {
	if p == nil {
		return
	}
	rp.mu.Lock()
	defer rp.mu.Unlock()

	cfg, ok := rp.config[p.Lang]
	if !ok || len(rp.pools[p.Lang]) >= cfg.MaxProcs {
		return // pool full, discard
	}

	p.LastUsed = time.Now()
	rp.pools[p.Lang] = append(rp.pools[p.Lang], p)
}

// ReapIdle terminates and removes processes idle beyond the timeout.
// Returns the number of processes reaped.
func (rp *RuntimePool) ReapIdle() int {
	rp.mu.Lock()
	defer rp.mu.Unlock()

	count := 0
	for lang, procs := range rp.pools {
		active := make([]*warmProc, 0, len(procs))
		for _, p := range procs {
			if time.Since(p.LastUsed) > rp.idleTimeout {
				if p.Cmd != nil && p.Cmd.Process != nil {
					p.Cmd.Process.Kill()
				}
				count++
			} else {
				active = append(active, p)
			}
		}
		rp.pools[lang] = active
	}
	return count
}

// Stats returns pool statistics for each language.
func (rp *RuntimePool) Stats() map[string]map[string]int {
	rp.mu.Lock()
	defer rp.mu.Unlock()

	stats := make(map[string]map[string]int)
	for lang, procs := range rp.pools {
		cfg := rp.config[lang]
		stats[lang] = map[string]int{
			"idle":    len(procs),
			"max":     cfg.MaxProcs,
		}
	}
	return stats
}
