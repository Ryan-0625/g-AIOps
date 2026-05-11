package connection

import (
	"sync"

	"github.com/gaiops/worker/pkg/envelope"
)

// DedupCache holds recent msg_id → response mappings for at-most-once delivery.
//
// When Master re-sends a request after a reconnection, the Worker looks up the
// msg_id here. If found, it returns the cached response without re-executing.
//
// Entries are evicted FIFO when the cache reaches capacity.
type DedupCache struct {
	mu       sync.RWMutex
	capacity int
	entries  map[string]*envelope.Envelope
	order    []string
}

func NewDedupCache(capacity int) *DedupCache {
	if capacity <= 0 {
		capacity = 1024
	}
	return &DedupCache{
		capacity: capacity,
		entries:  make(map[string]*envelope.Envelope),
		order:    make([]string, 0, capacity),
	}
}

// Get returns the cached response for a msg_id, or nil.
func (c *DedupCache) Get(msgID string) *envelope.Envelope {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.entries[msgID]
}

// Set stores a response keyed by msg_id. Evicts oldest entry if at capacity.
func (c *DedupCache) Set(msgID string, resp *envelope.Envelope) {
	c.mu.Lock()
	defer c.mu.Unlock()

	if _, exists := c.entries[msgID]; exists {
		return
	}

	if len(c.order) >= c.capacity {
		oldest := c.order[0]
		delete(c.entries, oldest)
		c.order = c.order[1:]
	}

	c.entries[msgID] = resp
	c.order = append(c.order, msgID)
}
