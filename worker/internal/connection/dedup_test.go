package connection_test

import (
	"testing"

	"github.com/gaiops/worker/internal/connection"
	"github.com/gaiops/worker/pkg/envelope"
)

func TestDedupCacheGetSet(t *testing.T) {
	c := connection.NewDedupCache(10)
	resp := envelope.NewRequest("t1", "m1", "test.action", nil)

	c.Set("msg-1", resp)
	got := c.Get("msg-1")
	if got == nil {
		t.Fatal("expected cached response, got nil")
	}
	if got.MsgID != "m1" {
		t.Errorf("MsgID = %q, want m1", got.MsgID)
	}
}

func TestDedupCacheMiss(t *testing.T) {
	c := connection.NewDedupCache(10)
	if got := c.Get("nonexistent"); got != nil {
		t.Errorf("expected nil for miss, got %v", got)
	}
}

func TestDedupCacheIdempotentSet(t *testing.T) {
	c := connection.NewDedupCache(10)
	resp := envelope.NewRequest("t1", "m1", "test.action", nil)
	c.Set("msg-1", resp)
	c.Set("msg-1", resp) // second set should be no-op
	if c.Get("msg-1") == nil {
		t.Error("entry should still exist after duplicate set")
	}
}

func TestDedupCacheEviction(t *testing.T) {
	c := connection.NewDedupCache(3)

	// Fill cache with 3 entries, then add 2 more to trigger eviction.
	for i := 0; i < 5; i++ {
		id := ids[i]
		resp := envelope.NewRequest("t1", id, "test.action", nil)
		c.Set(id, resp)
	}

	// First entries should be evicted.
	for i := 0; i < 2; i++ {
		if got := c.Get(ids[i]); got != nil {
			t.Errorf("expected entry %d (%s) to be evicted", i, ids[i])
		}
	}
	// Most recent should still exist.
	for i := 2; i < 5; i++ {
		if got := c.Get(ids[i]); got == nil {
			t.Errorf("expected entry %d (%s) to exist", i, ids[i])
		}
	}
}

func TestDedupCacheDefaultCapacity(t *testing.T) {
	c := connection.NewDedupCache(0) // should default to 1024
	if c == nil {
		t.Fatal("expected non-nil cache")
	}
}

var ids = []string{"a", "b", "c", "d", "e"}
