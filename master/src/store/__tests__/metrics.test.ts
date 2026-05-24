import { MetricsCollector } from "../metrics";

describe("MetricsCollector", () => {
  let metrics: MetricsCollector;

  beforeEach(() => {
    metrics = new MetricsCollector();
  });

  it("starts with zero counts", () => {
    jest.useFakeTimers();
    jest.setSystemTime(Date.now());

    const snap = metrics.snapshot(0, 0, 0, 0);
    expect(snap.totalProcessed).toBe(0);
    expect(snap.requestsThisMinute).toBe(0);
    expect(snap.truncatedCount).toBe(0);
    expect(snap.errorCount).toBe(0);

    jest.useRealTimers();
  });

  it("records successful requests", () => {
    metrics.recordRequest("success", false);
    metrics.recordRequest("success", false);
    metrics.recordRequest("success", false);

    const snap = metrics.snapshot(0, 0, 0, 0);
    expect(snap.totalProcessed).toBe(3);
    expect(snap.requestsThisMinute).toBe(3);
    expect(snap.errorCount).toBe(0);
  });

  it("records failure requests", () => {
    metrics.recordRequest("failure", false);
    const snap = metrics.snapshot(0, 0, 0, 0);
    expect(snap.errorCount).toBe(1);
  });

  it("records truncated responses", () => {
    metrics.recordRequest("success", true);
    const snap = metrics.snapshot(0, 0, 0, 0);
    expect(snap.truncatedCount).toBe(1);
  });

  it("resets requestsThisMinute after window expires", () => {
    jest.useFakeTimers();
    jest.setSystemTime(0);

    metrics.recordRequest("success", false);
    let snap = metrics.snapshot(0, 0, 0, 0);
    expect(snap.requestsThisMinute).toBe(1);

    // Advance past the 60s window
    jest.setSystemTime(61_000);
    snap = metrics.snapshot(0, 0, 0, 0);
    expect(snap.requestsThisMinute).toBe(0);

    jest.useRealTimers();
  });

  it("snapshot captures runtime metrics", () => {
    metrics.recordRequest("success", false);

    const snap = metrics.snapshot(5, 10, 3, 2);
    expect(snap.workerCount).toBe(5);
    expect(snap.pendingCount).toBe(10);
    expect(snap.queueDepth).toBe(3);
    expect(snap.approvalCount).toBe(2);
    expect(snap.uptimeSeconds).toBeGreaterThanOrEqual(0);
  });

  it("totalProcessed getter returns correct value", () => {
    expect(metrics.totalProcessed).toBe(0);
    metrics.recordRequest("success", false);
    expect(metrics.totalProcessed).toBe(1);
    metrics.recordRequest("failure", false);
    expect(metrics.totalProcessed).toBe(2);
  });
});
