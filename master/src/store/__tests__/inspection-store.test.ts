import { InspectionStore, InspectionConfig, ProbeType, AlertRule } from '../inspection-store';

function makeInspection(overrides: Partial<InspectionConfig> = {}): InspectionConfig {
  return {
    id: 'test-inspection-1',
    name: 'Test Inspection',
    description: 'A test inspection',
    enabled: true,
    probe_type: 'port.check' as ProbeType,
    probe_params: { host: 'localhost', port: 80 },
    target_mode: 'all',
    schedule_mode: 'interval',
    interval_seconds: 300,
    timeout_seconds: 30,
    alert_rules: [
      { metric: 'reachable', operator: '==', threshold: false, severity: 'critical', message: 'Port unreachable' },
    ],
    notify_channels: ['log'],
    created_at: Date.now(),
    updated_at: Date.now(),
    created_by: 'test',
    ...overrides,
  };
}

describe('InspectionStore', () => {
  let store: InspectionStore;

  beforeEach(() => {
    store = new InspectionStore();
  });

  describe('CRUD', () => {
    it('creates and retrieves an inspection', () => {
      const cfg = makeInspection();
      store.createInspection(cfg);
      expect(store.getInspection(cfg.id)).toBeDefined();
      expect(store.getInspection(cfg.id)!.name).toBe('Test Inspection');
    });

    it('lists all inspections', () => {
      store.createInspection(makeInspection({ id: 'a', name: 'A' }));
      store.createInspection(makeInspection({ id: 'b', name: 'B' }));
      expect(store.listInspections()).toHaveLength(2);
    });

    it('lists only enabled inspections', () => {
      store.createInspection(makeInspection({ id: 'a', enabled: true }));
      store.createInspection(makeInspection({ id: 'b', enabled: false }));
      expect(store.listInspections(true)).toHaveLength(1);
    });

    it('updates an inspection', () => {
      store.createInspection(makeInspection());
      const updated = store.updateInspection('test-inspection-1', { interval_seconds: 600 });
      expect(updated).toBe(true);
      expect(store.getInspection('test-inspection-1')!.interval_seconds).toBe(600);
    });

    it('returns false when updating non-existent inspection', () => {
      expect(store.updateInspection('nonexistent', { name: 'X' })).toBe(false);
    });

    it('deletes an inspection', () => {
      store.createInspection(makeInspection());
      expect(store.deleteInspection('test-inspection-1')).toBe(true);
      expect(store.getInspection('test-inspection-1')).toBeUndefined();
    });

    it('returns false when deleting non-existent inspection', () => {
      expect(store.deleteInspection('nonexistent')).toBe(false);
    });
  });

  describe('Results', () => {
    it('stores and retrieves results', () => {
      store.createInspection(makeInspection());
      store.storeResult({
        id: 'result-1',
        inspection_id: 'test-inspection-1',
        worker_id: 'worker-1',
        timestamp: Date.now(),
        duration_ms: 100,
        probe_type: 'port.check',
        probe_params: {},
        success: true,
        data: { reachable: true },
        alerts_triggered: [],
        status: 'pass',
      });
      const results = store.getResults('test-inspection-1');
      expect(results).toHaveLength(1);
      expect(results[0].status).toBe('pass');
    });

    it('trims old results when exceeding max', () => {
      store.createInspection(makeInspection());
      // Add more results than MAX_RESULTS allows
      for (let i = 0; i < 100; i++) {
        store.storeResult({
          id: "result-${i}",
          inspection_id: 'test-inspection-1',
          worker_id: 'worker-1',
          timestamp: Date.now(),
          duration_ms: i,
          probe_type: 'port.check',
          probe_params: {},
          success: true,
          data: {},
          alerts_triggered: [],
          status: 'pass',
        });
      }
      const results = store.getResults('test-inspection-1', 200);
      expect(results.length).toBeLessThanOrEqual(100);
    });

    it('gets latest result for an inspection', () => {
      store.createInspection(makeInspection());
      store.storeResult(makeResult('old', 'pass', 100));
      store.storeResult(makeResult('latest', 'fail', 200));
      const latest = store.getLatestResult('test-inspection-1');
      expect(latest!.id).toBe('latest');
    });
  });

  describe('Alert Evaluation', () => {
    it('triggers alert when rule matches', () => {
      store.createInspection(makeInspection());
      const results = store.evaluateAlerts(
        makeInspection(),
        'worker-1',
        { reachable: false },
        'result-1',
      );
      expect(results).toHaveLength(1);
      expect(results[0].triggered).toBe(true);
      expect(results[0].severity).toBe('critical');
    });

    it('does not trigger alert when rule does not match', () => {
      const results = store.evaluateAlerts(
        makeInspection(),
        'worker-1',
        { reachable: true },
        'result-1',
      );
      expect(results).toHaveLength(1);
      expect(results[0].triggered).toBe(false);
    });

    it('evaluates numeric comparisons', () => {
      const rule: AlertRule = { metric: 'usage_pct', operator: '>', threshold: 80, severity: 'warning', message: 'High disk' };
      const cfg = makeInspection({ alert_rules: [rule] });
      const pass = store.evaluateAlerts(cfg, 'w1', { usage_pct: '85.0' }, 'r1');
      expect(pass[0].triggered).toBe(true);
      const fail = store.evaluateAlerts(cfg, 'w1', { usage_pct: '50.0' }, 'r1');
      expect(fail[0].triggered).toBe(false);
    });

    it('evaluates string contains operator', () => {
      const rule: AlertRule = { metric: 'status', operator: 'contains', threshold: 'error', severity: 'critical', message: 'Error found' };
      const cfg = makeInspection({ alert_rules: [rule] });
      const match = store.evaluateAlerts(cfg, 'w1', { status: 'connection_error' }, 'r1');
      expect(match[0].triggered).toBe(true);
      const noMatch = store.evaluateAlerts(cfg, 'w1', { status: 'running_ok' }, 'r1');
      expect(noMatch[0].triggered).toBe(false);
    });

    it('evaluates nested metric paths', () => {
      const rule: AlertRule = { metric: 'certificates.0.days_remaining', operator: '<', threshold: 30, severity: 'warning', message: 'Cert expires' };
      const cfg = makeInspection({ alert_rules: [rule] });
      const result = store.evaluateAlerts(cfg, 'w1', {
        certificates: [{ days_remaining: 15 }],
      }, 'r1');
      expect(result[0].triggered).toBe(true);
    });
  });

  describe('Alert Management', () => {
    it('acknowledges an alert', () => {
      store.createInspection(makeInspection());
      // Trigger an alert via evaluateAlerts
      store.evaluateAlerts(makeInspection(), 'worker-1', { reachable: false }, 'result-ack');
      const alerts = store.getAlerts(10, true);
      expect(alerts).toHaveLength(1);
      expect(store.acknowledgeAlert(alerts[0].id, 'admin')).toBe(true);
      expect(store.getAlerts(10, true)).toHaveLength(0);
    });

    it('returns alert stats', () => {
      store.createInspection(makeInspection({ id: 'stats-test' }));
      store.evaluateAlerts(makeInspection({ id: 'stats-test' }), 'w1', { reachable: false }, 'r1');
      store.evaluateAlerts(makeInspection({ id: 'stats-test' }), 'w1', { reachable: false, disk: { usage_pct: 99 } }, 'r2');
      const stats = store.getAlertStats();
      expect(stats.total).toBeGreaterThanOrEqual(1);
      expect(stats.unacknowledged).toBeGreaterThanOrEqual(1);
    });
  });
});

function makeResult(id: string, status: 'pass' | 'fail' | 'error', durationMs: number): any {
  return {
    id,
    inspection_id: 'test-inspection-1',
    worker_id: 'worker-1',
    timestamp: Date.now(),
    duration_ms: durationMs,
    probe_type: 'port.check' as ProbeType,
    probe_params: {},
    success: status === 'pass',
    data: { reachable: status === 'pass' },
    alerts_triggered: [],
    status,
  };
}




  describe("Exception & Boundary", () => {
    it("handles concurrent result storage without data loss", () => {
      const store = new InspectionStore();
      const cfg = makeInspection({ id: "concurrent-test" });
      store.createInspection(cfg);

      // Simulate concurrent writes
      const results = Array.from({ length: 50 }, (_, i) => ({
        id: "concurrent-result-" + i,
        inspection_id: "concurrent-test",
        worker_id: "worker-" + (i % 3),
        timestamp: Date.now(),
        duration_ms: i * 10,
        probe_type: "port.check" as ProbeType,
        probe_params: {},
        success: true,
        data: { reachable: true, index: i },
        alerts_triggered: [],
        status: "pass" as const,
        error: undefined,
      }));

      // Store all results
      for (const r of results) {
        store.storeResult(r);
      }

      const retrieved = store.getResults("concurrent-test", 100);
      expect(retrieved).toHaveLength(50);
    });

    it("handles result with missing optional fields", () => {
      const store = new InspectionStore();
      const cfg = makeInspection({ id: "minimal-result" });
      store.createInspection(cfg);

      // Minimal result with only required fields
      const minimalResult = {
        id: "minimal-1",
        inspection_id: "minimal-result",
        worker_id: "w1",
        timestamp: Date.now(),
        duration_ms: 0,
        probe_type: "port.check" as ProbeType,
        probe_params: {},
        success: false,
        data: {},
        alerts_triggered: [],
        status: "error" as const,
        error: "Connection timeout",
      };
      store.storeResult(minimalResult);
      const results = store.getResults("minimal-result");
      expect(results).toHaveLength(1);
      expect(results[0].error).toBe("Connection timeout");
    });

    it("trims results at MAX_RESULTS boundary", () => {
      const store = new InspectionStore();
      const cfg = makeInspection({ id: "boundary-results" });
      store.createInspection(cfg);

      // Add exactly MAX_RESULTS + 10 results
      const MAX = 10000; // matches MAX_RESULTS
      for (let i = 0; i < MAX + 10; i++) {
        store.storeResult({
          id: "br-" + i,
          inspection_id: "boundary-results",
          worker_id: "w1",
          timestamp: Date.now(),
          duration_ms: i,
          probe_type: "port.check" as ProbeType,
          probe_params: {},
          success: true,
          data: {},
          alerts_triggered: [],
          status: "pass" as const,
        });
      }

      // Should not exceed MAX_RESULTS
      const results = store.getResults("boundary-results", MAX + 100);
      expect(results.length).toBeLessThanOrEqual(MAX);
    });

    it("trims alerts at MAX_ALERTS boundary", () => {
      const store = new InspectionStore();
      const cfg = makeInspection({ id: "boundary-alerts" });
      store.createInspection(cfg);

      // Trigger more alerts than MAX_ALERTS
      const MAX = 5000; // matches MAX_ALERTS
      for (let i = 0; i < MAX + 50; i++) {
        store.evaluateAlerts(
          makeInspection({ id: "boundary-alerts" }),
          "w1",
          { reachable: false },
          "result-alert-" + i,
        );
      }

      const stats = store.getAlertStats();
      expect(stats.total).toBeLessThanOrEqual(MAX);
    });

    it("handles null/undefined values in alert evaluation", () => {
      const store = new InspectionStore();

      // Null value
      const nullResult = store.evaluateAlerts(
        makeInspection({ id: "null-test", alert_rules: [
          { metric: "status", operator: "==", threshold: "ok", severity: "warning", message: "Not ok" },
        ]}),
        "w1",
        { status: null },
        "r-null",
      );
      expect(nullResult[0].triggered).toBe(false);

      // Undefined value
      const undefResult = store.evaluateAlerts(
        makeInspection({ id: "undef-test", alert_rules: [
          { metric: "missing.field", operator: "==", threshold: "ok", severity: "warning", message: "Missing" },
        ]}),
        "w1",
        {},
        "r-undef",
      );
      expect(undefResult[0].triggered).toBe(false);

      // String "null"
      const strNullResult = store.evaluateAlerts(
        makeInspection({ id: "strnull-test", alert_rules: [
          { metric: "status", operator: "==", threshold: "null", severity: "info", message: "Is null" },
        ]}),
        "w1",
        { status: "null" },
        "r-strnull",
      );
      expect(strNullResult[0].triggered).toBe(true);
    });

    it("handles deeply nested metric paths gracefully", () => {
      const store = new InspectionStore();
      const result = store.evaluateAlerts(
        makeInspection({ id: "deep-nested", alert_rules: [
          { metric: "a.b.c.d.e.f", operator: ">", threshold: 0, severity: "info", message: "Deep" },
        ]}),
        "w1",
        { a: { b: { c: { d: { e: { f: 42 } } } } } },
        "r-deep",
      );
      expect(result[0].triggered).toBe(true);
      expect(result[0].actual).toBe("42");

      // Partially missing path
      const missing = store.evaluateAlerts(
        makeInspection({ id: "partial-nested", alert_rules: [
          { metric: "a.b.c.x.y", operator: "==", threshold: "exists", severity: "info", message: "Partial" },
        ]}),
        "w1",
        { a: { b: { c: 42 } } },
        "r-partial",
      );
      expect(missing[0].triggered).toBe(false);
    });

    it("handles alert with empty rules list", () => {
      const store = new InspectionStore();
      const results = store.evaluateAlerts(
        makeInspection({ id: "empty-rules", alert_rules: [] }),
        "w1",
        { reachable: false },
        "r-empty",
      );
      expect(results).toHaveLength(0);
    });

    it("evaluates '!=' operator correctly", () => {
      const store = new InspectionStore();
      const rule: AlertRule = { metric: "status", operator: "!=", threshold: "ok", severity: "warning", message: "Bad" };
      const cfg = makeInspection({ alert_rules: [rule] });

      // Different value should trigger
      const diff = store.evaluateAlerts(cfg, "w1", { status: "error" }, "r1");
      expect(diff[0].triggered).toBe(true);

      // Same value should not trigger
      const same = store.evaluateAlerts(cfg, "w1", { status: "ok" }, "r2");
      expect(same[0].triggered).toBe(false);
    });

    it("evaluates 'not_contains' operator correctly", () => {
      const store = new InspectionStore();
      const rule: AlertRule = { metric: "message", operator: "not_contains", threshold: "timeout", severity: "info", message: "No timeout" };
      const cfg = makeInspection({ alert_rules: [rule] });

      const noMatch = store.evaluateAlerts(cfg, "w1", { message: "all good" }, "r1");
      expect(noMatch[0].triggered).toBe(true);

      const match = store.evaluateAlerts(cfg, "w1", { message: "connection timeout" }, "r2");
      expect(match[0].triggered).toBe(false);
    });

    it("acknowledgeAlert returns false for already acknowledged alerts", () => {
      const store = new InspectionStore();
      store.createInspection(makeInspection({ id: "double-ack" }));
      store.evaluateAlerts(makeInspection({ id: "double-ack" }), "w1", { reachable: false }, "r-ack");
      const alerts = store.getAlerts(10);
      expect(alerts.length).toBeGreaterThanOrEqual(1);

      // First ack should succeed
      expect(store.acknowledgeAlert(alerts[0].id, "admin")).toBe(true);
      // Second ack should fail
      expect(store.acknowledgeAlert(alerts[0].id, "admin")).toBe(false);
    });

    it("acknowledgeAlert returns false for nonexistent alert", () => {
      const store = new InspectionStore();
      expect(store.acknowledgeAlert("nonexistent-alert-id", "admin")).toBe(false);
    });

    it("getLatestResult returns undefined when no results for worker", () => {
      const store = new InspectionStore();
      store.createInspection(makeInspection({ id: "no-results" }));
      const latest = store.getLatestResult("no-results", "nonexistent-worker");
      expect(latest).toBeUndefined();
    });

    it("getLatestResult without workerId returns latest overall", () => {
      const store = new InspectionStore();
      store.createInspection(makeInspection({ id: "latest-overall" }));
      // Use makeResult but with explicit inspection_id matching the created inspection
      const oldResult = makeResult("old", "pass", 100);
      oldResult.inspection_id = "latest-overall";
      store.storeResult(oldResult);
      const newResult = makeResult("new", "fail", 200);
      newResult.inspection_id = "latest-overall";
      store.storeResult(newResult);
      const latest = store.getLatestResult("latest-overall");
      expect(latest!.id).toBe("new");
    });

    it("getResultsByWorker filters correctly", () => {
      const store = new InspectionStore();
      store.createInspection(makeInspection({ id: "by-worker" }));

      store.storeResult({
        id: "w1-r1", inspection_id: "by-worker", worker_id: "worker-1",
        timestamp: Date.now(), duration_ms: 10, probe_type: "port.check" as ProbeType,
        probe_params: {}, success: true, data: {}, alerts_triggered: [], status: "pass" as const,
      });
      store.storeResult({
        id: "w2-r1", inspection_id: "by-worker", worker_id: "worker-2",
        timestamp: Date.now(), duration_ms: 20, probe_type: "port.check" as ProbeType,
        probe_params: {}, success: true, data: {}, alerts_triggered: [], status: "pass" as const,
      });

      const worker1Results = store.getResultsByWorker("worker-1");
      expect(worker1Results).toHaveLength(1);
      expect(worker1Results[0].worker_id).toBe("worker-1");
    });
  });
