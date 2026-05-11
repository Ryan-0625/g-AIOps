/** Session state management — in-memory per-trace_id session tracking. */

export interface BrainSession {
  traceId: string;
  status: "pending" | "running" | "completed" | "failed";
  action: string;
  workerId: string;
  createdAt: number;
  completedAt?: number;
  error?: string;
}

export class SessionStore {
  private sessions = new Map<string, BrainSession>();
  private readonly MAX_SESSIONS = 10_000;

  set(session: BrainSession): boolean {
    if (this.sessions.size >= this.MAX_SESSIONS) {
      return false;
    }
    this.sessions.set(session.traceId, session);
    return true;
  }

  get(traceId: string): BrainSession | undefined {
    return this.sessions.get(traceId);
  }

  update(traceId: string, partial: Partial<BrainSession>): void {
    const existing = this.sessions.get(traceId);
    if (existing) {
      Object.assign(existing, partial);
    }
  }

  list(filter?: { status?: string }): BrainSession[] {
    const all = Array.from(this.sessions.values());
    if (filter?.status) {
      return all.filter(s => s.status === filter.status);
    }
    return all;
  }

  /** Remove sessions older than maxAgeMs. Returns count removed. */
  reap(maxAgeMs: number): number {
    const cutoff = Date.now() - maxAgeMs;
    let reaped = 0;
    for (const [traceId, session] of this.sessions.entries()) {
      const age = session.completedAt ?? session.createdAt;
      if (age < cutoff) {
        this.sessions.delete(traceId);
        reaped++;
      }
    }
    return reaped;
  }

  get size(): number {
    return this.sessions.size;
  }
}
