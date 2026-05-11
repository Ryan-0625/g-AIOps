/**
 * Sliding-window rate limiter for per-worker message flow control.
 *
 * Tracks the number of messages received from each worker within a rolling
 * time window. When a worker exceeds the burst limit, the excess is either
 * dropped or the connection flagged.
 */
export class SlidingWindowRateLimiter {
  /** workerId → ring buffer of event timestamps (ms) */
  private windows = new Map<string, number[]>();

  /**
   * @param windowMs  width of the sliding window in ms (default 1000)
   * @param maxEvents max events allowed per window (default 100)
   */
  constructor(
    private readonly windowMs: number = 1000,
    private readonly maxEvents: number = 100,
  ) {}

  /**
   * Allow? Returns true if the event is within the limit, false if it should
   * be throttled. Also prunes the caller's stale entries.
   */
  allow(workerId: string): boolean {
    const now = Date.now();
    const cutoff = now - this.windowMs;

    let events = this.windows.get(workerId);
    if (!events) {
      events = [];
      this.windows.set(workerId, events);
    }

    // Prune entries outside the window.
    // Since insertions are roughly chronological, we can drop from the front.
    while (events.length > 0 && events[0] < cutoff) {
      events.shift();
    }

    if (events.length >= this.maxEvents) {
      return false;
    }

    events.push(now);
    return true;
  }

  /**
   * Remove a worker's tracking data (e.g. on disconnect).
   */
  reset(workerId: string): void {
    this.windows.delete(workerId);
  }

  /**
   * Prune stale entries for all tracked workers. Returns the number of
   * workers whose data was removed entirely (idle beyond the window).
   */
  reap(): number {
    const now = Date.now();
    const cutoff = now - this.windowMs;
    let removed = 0;

    for (const [workerId, events] of this.windows.entries()) {
      while (events.length > 0 && events[0] < cutoff) {
        events.shift();
      }
      if (events.length === 0) {
        this.windows.delete(workerId);
        removed++;
      }
    }

    return removed;
  }

  /** Number of tracked workers. */
  size(): number {
    return this.windows.size;
  }
}
