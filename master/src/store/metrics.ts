/** Runtime metrics — Worker load, queue depth, connection count. */

export interface RuntimeMetrics {
  /** Connected Worker count. */
  workerCount: number;
  /** Pending request count. */
  pendingCount: number;
  /** Priority queue depth. */
  queueDepth: number;
  /** Active approval requests. */
  approvalCount: number;
  /** Total requests processed since start. */
  totalProcessed: number;
  /** Requests processed in current minute (for rate calculation). */
  requestsThisMinute: number;
  /** Accumulated truncated responses. */
  truncatedCount: number;
  /** Accumulated error responses. */
  errorCount: number;
  /** Process uptime (seconds). */
  uptimeSeconds: number;
}

export class MetricsCollector {
  private startTime = Date.now();
  private _totalProcessed = 0;
  private _requestsThisMinute = 0;
  private _truncatedCount = 0;
  private _errorCount = 0;
  private minuteWindow = Date.now();

  /** Call on every completed request. */
  recordRequest(status: "success" | "failure", truncated: boolean): void {
    this._totalProcessed++;
    const now = Date.now();
    if (now - this.minuteWindow > 60_000) {
      this._requestsThisMinute = 0;
      this.minuteWindow = now;
    }
    this._requestsThisMinute++;
    if (truncated) this._truncatedCount++;
    if (status === "failure") this._errorCount++;
  }

  snapshot(
    workerCount: number,
    pendingCount: number,
    queueDepth: number,
    approvalCount: number,
  ): RuntimeMetrics {
    return {
      workerCount,
      pendingCount,
      queueDepth,
      approvalCount,
      totalProcessed: this._totalProcessed,
      requestsThisMinute: this._requestsThisMinute,
      truncatedCount: this._truncatedCount,
      errorCount: this._errorCount,
      uptimeSeconds: Math.floor((Date.now() - this.startTime) / 1000),
    };
  }

  get totalProcessed(): number {
    return this._totalProcessed;
  }
}
