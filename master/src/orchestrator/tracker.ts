import { Envelope } from "../protocol/types";
import { createLogger } from "../logger";

const logger = createLogger("master");

interface PendingEntry {
  envelope: Envelope;
  targetWorkerId: string;
  sentAt: number;
  retryCount: number;
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

  private chunkGroups = new Map<string, ChunkGroup>();
  private readonly CHUNK_TIMEOUT_MS = 30_000;
  private readonly MAX_CHUNK_GROUPS = 500;

  // ── Pending management ─────────────────────────────────────────────

  track(msgId: string, env: Envelope, targetWorkerId: string): boolean {
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

  resolve(msgId: string): void {
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

  /** Reap expired orphan requests (Brain disconnected mid-flight). */
  reapOrphans(): number {
    const now = Date.now();
    let reaped = 0;
    for (const [msgId, entry] of this.pending.entries()) {
      if (now - entry.sentAt > this.ORPHAN_TTL_MS) {
        this.pending.delete(msgId);
        reaped++;
      }
    }
    return reaped;
  }

  /** Number of pending entries. */
  pendingCount(): number {
    return this.pending.size;
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
