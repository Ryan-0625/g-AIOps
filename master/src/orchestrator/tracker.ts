import { Envelope } from "../protocol/types";
import { createLogger } from "../logger";

const logger = createLogger("master");

interface PendingEntry {
  envelope: Envelope;
  targetWorkerId: string;
  sentAt: number;
  retryCount: number;
}

interface CompletedEntry {
  response: Envelope;
  completedAt: number;
}

interface ChunkGroup {
  traceId: string;
  chunks: Map<number, string>;
  totalChunks: number;
  firstChunkAt: number;
}

export class Tracker {
  private pending = new Map<string, PendingEntry>();
  private readonly MAX_PENDING = 10_000;
  private readonly ORPHAN_TTL_MS = 300_000; // 5 min

  private completed = new Map<string, CompletedEntry>();
  private readonly MAX_COMPLETED = 10_000;
  private readonly COMPLETED_TTL_MS = 300_000; // 5 min

  private chunkGroups = new Map<string, ChunkGroup>();
  private readonly CHUNK_TIMEOUT_MS = 30_000;
  private readonly MAX_CHUNK_GROUPS = 500;

  private _draining = false;

  get draining(): boolean {
    return this._draining;
  }

  // ── Pending management ─────────────────────────────────────────────

  track(msgId: string, env: Envelope, targetWorkerId: string): boolean {
    if (this._draining) {
      logger.warn("Tracker draining, rejecting request", { msgId });
      return false;
    }
    if (this.pending.size >= this.MAX_PENDING) {
      logger.error("Tracker full, rejecting request", { msgId, data: { pending: this.pending.size } });
      return false;
    }
    this.pending.set(msgId, {
      envelope: env,
      targetWorkerId,
      sentAt: Date.now(),
      retryCount: 0,
    });
    return true;
  }

  resolve(msgId: string, response?: Envelope): void {
    if (response) {
      if (this.completed.size >= this.MAX_COMPLETED) {
        // Evict oldest entry to stay under limit.
        const oldest = this.completed.entries().next().value;
        if (oldest) this.completed.delete(oldest[0]);
      }
      this.completed.set(msgId, { response, completedAt: Date.now() });
    }
    this.pending.delete(msgId);
  }

  getPending(): Map<string, PendingEntry> {
    return this.pending;
  }

  getPendingForWorker(workerId: string): PendingEntry[] {
    const result: PendingEntry[] = [];
    for (const entry of this.pending.values()) {
      if (entry.targetWorkerId === workerId) result.push(entry);
    }
    return result;
  }

  /** Reap expired orphan requests (Brain disconnected mid-flight) and stale completed results. */
  reapOrphans(): number {
    const now = Date.now();
    let reaped = 0;
    for (const [msgId, entry] of this.pending.entries()) {
      if (now - entry.sentAt > this.ORPHAN_TTL_MS) {
        this.pending.delete(msgId);
        reaped++;
      }
    }
    reaped += this.reapCompleted();
    return reaped;
  }

  /** Number of pending entries. */
  pendingCount(): number {
    return this.pending.size;
  }

  drain(timeoutMs: number = 8000): Promise<void> {
    this._draining = true;
    logger.info("Tracker draining", { data: { pending: this.pending.size, timeoutMs } });
    return new Promise((resolve) => {
      const start = Date.now();
      const poll = () => {
        if (this.pending.size === 0) {
          resolve();
          return;
        }
        if (Date.now() - start >= timeoutMs) {
          logger.warn("Tracker drain timeout", { data: { remaining: this.pending.size } });
          resolve();
          return;
        }
        setTimeout(poll, 100);
      };
      poll();
    });
  }

  /** Retrieve a completed result by msg_id. */
  getCompleted(msgId: string): CompletedEntry | undefined {
    return this.completed.get(msgId);
  }

  /** Iterate all completed entries (for trace lookup). */
  getCompletedEntries(): Map<string, CompletedEntry> {
    return this.completed;
  }

  /** Reap completed entries older than TTL. */
  reapCompleted(maxAgeMs: number = this.COMPLETED_TTL_MS): number {
    const now = Date.now();
    let reaped = 0;
    for (const [msgId, entry] of this.completed.entries()) {
      if (now - entry.completedAt > maxAgeMs) {
        this.completed.delete(msgId);
        reaped++;
      }
    }
    return reaped;
  }

  // ── Chunk assembly ─────────────────────────────────────────────────

  /** Add a chunk; returns the full assembled payload when all chunks arrive. */
  addChunk(traceId: string, index: number, total: number, content: string): string | null {
    let group = this.chunkGroups.get(traceId);
    if (!group) {
      if (this.chunkGroups.size >= this.MAX_CHUNK_GROUPS) {
        logger.error("Too many chunk groups, discarding", { trace_id: traceId });
        return null;
      }
      group = { traceId, chunks: new Map(), totalChunks: total, firstChunkAt: Date.now() };
      this.chunkGroups.set(traceId, group);
    }

    group.chunks.set(index, content);

    if (group.chunks.size >= group.totalChunks) {
      const parts: string[] = [];
      for (let i = 0; i < group.totalChunks; i++) {
        parts.push(group.chunks.get(i) ?? "");
      }
      this.chunkGroups.delete(traceId);
      return parts.join("");
    }

    return null;
  }

  /** Reap expired chunk groups. */
  reapChunks(): number {
    const now = Date.now();
    let reaped = 0;
    for (const [traceId, group] of this.chunkGroups.entries()) {
      if (now - group.firstChunkAt > this.CHUNK_TIMEOUT_MS) {
        this.chunkGroups.delete(traceId);
        reaped++;
      }
    }
    return reaped;
  }
}
