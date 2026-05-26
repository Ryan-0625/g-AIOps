// InspectionStore — manages inspection configurations, results, and alert rules.
// Inspections are periodic checks that Master schedules and dispatches to Workers.
// Each inspection defines:
//   - What to check (via existing worker tools: port.check, http.get, ping.icmp, disk.usage, ssl.cert_check, process.list)
//   - Which workers to check (specific, group, or all)
//   - When to check (cron schedule or interval)
//   - Alert rules (thresholds that trigger notifications)

import { createLogger } from "../logger";

const logger = createLogger("master");

// --- Types ---

export type ProbeType =
  | "port.check"
  | "http.health"
  | "ping.icmp"
  | "disk.usage"
  | "ssl.cert_check"
  | "process.list"
  | "dns.lookup"
  | "service.status"
  | "custom.exec";

export interface AlertRule {
  metric: string;          // e.g. "reachable", "usage_pct", "status_code", "days_remaining"
  operator: ">" | "<" | "==" | "!=" | "contains" | "not_contains";
  threshold: number | string | boolean;
  severity: "info" | "warning" | "critical";
  message: string;         // Template with {metric}, {value}, {threshold}, {worker_id}, {target}
}

export interface InspectionConfig {
  id: string;
  name: string;
  description?: string;
  enabled: boolean;

  // What to check
  probe_type: ProbeType;
  probe_params: Record<string, unknown>;

  // Who to check
  target_mode: "all" | "worker_ids" | "tags";
  target_workers?: string[];   // specific worker IDs
  target_tags?: string[];      // worker tags

  // When to check
  schedule_mode: "interval" | "cron";
  interval_seconds?: number;   // for interval mode
  cron_expr?: string;          // for cron mode (future)
  timeout_seconds: number;

  // Alert rules
  alert_rules: AlertRule[];

  // Notification channels
  notify_channels: string[];   // "webhook", "log", etc.

  // Metadata
  created_at: number;
  updated_at: number;
  created_by: string;
}

export interface InspectionResult {
  id: string;
  inspection_id: string;
  worker_id: string;
  timestamp: number;
  duration_ms: number;
  probe_type: ProbeType;
  probe_params: Record<string, unknown>;
  success: boolean;
  error?: string;
  data: Record<string, unknown>;
  alerts_triggered: AlertEvalResult[];
  status: "pass" | "fail" | "error";
}

export interface AlertEvalResult {
  rule_index: number;
  metric: string;
  expected: string;
  actual: string;
  operator: string;
  severity: "info" | "warning" | "critical";
  triggered: boolean;
  message: string;
}

export interface AlertEvent {
  id: string;
  inspection_id: string;
  inspection_name: string;
  worker_id: string;
  timestamp: number;
  severity: "info" | "warning" | "critical";
  message: string;
  result_id: string;
  acknowledged: boolean;
  acknowledged_at?: number;
  acknowledged_by?: string;
}

// --- Store ---

export class InspectionStore {
  private inspections = new Map<string, InspectionConfig>();
  private results: InspectionResult[] = [];
  private alerts: AlertEvent[] = [];
  private readonly MAX_RESULTS = 10000;
  private readonly MAX_ALERTS = 5000;

  // --- Inspection CRUD ---

  createInspection(cfg: InspectionConfig): void {
    this.inspections.set(cfg.id, cfg);
    logger.info("Inspection created", { data: { id: cfg.id, name: cfg.name, probe: cfg.probe_type } });
  }

  updateInspection(id: string, updates: Partial<InspectionConfig>): boolean {
    const existing = this.inspections.get(id);
    if (!existing) return false;
    this.inspections.set(id, { ...existing, ...updates, updated_at: Date.now() });
    logger.info("Inspection updated", { data: { id } });
    return true;
  }

  deleteInspection(id: string): boolean {
    const existed = this.inspections.delete(id);
    if (existed) logger.info("Inspection deleted", { data: { id } });
    return existed;
  }

  getInspection(id: string): InspectionConfig | undefined {
    return this.inspections.get(id);
  }

  listInspections(enabledOnly = false): InspectionConfig[] {
    const all = Array.from(this.inspections.values());
    return enabledOnly ? all.filter(i => i.enabled) : all;
  }

  // --- Results ---

  storeResult(result: InspectionResult): void {
    this.results.push(result);
    // Trim old results
    if (this.results.length > this.MAX_RESULTS) {
      this.results = this.results.slice(-this.MAX_RESULTS);
    }
  }

  getResults(inspectionId: string, limit = 50): InspectionResult[] {
    return this.results
      .filter(r => r.inspection_id === inspectionId)
      .slice(-limit)
      .reverse();
  }

  getLatestResult(inspectionId: string, workerId?: string): InspectionResult | undefined {
    const filtered = this.results.filter(r =>
      r.inspection_id === inspectionId &&
      (workerId ? r.worker_id === workerId : true)
    );
    return filtered[filtered.length - 1];
  }

  getResultsByWorker(workerId: string, limit = 20): InspectionResult[] {
    return this.results
      .filter(r => r.worker_id === workerId)
      .slice(-limit)
      .reverse();
  }

  // --- Alerts ---

  storeAlert(alert: AlertEvent): void {
    this.alerts.push(alert);
    if (this.alerts.length > this.MAX_ALERTS) {
      this.alerts = this.alerts.slice(-this.MAX_ALERTS);
    }
  }

  getAlerts(limit = 50, unacknowledgedOnly = false): AlertEvent[] {
    let filtered = this.alerts;
    if (unacknowledgedOnly) {
      filtered = filtered.filter(a => !a.acknowledged);
    }
    return filtered.slice(-limit).reverse();
  }

  acknowledgeAlert(alertId: string, by: string): boolean {
    const alert = this.alerts.find(a => a.id === alertId);
    if (!alert || alert.acknowledged) return false;
    alert.acknowledged = true;
    alert.acknowledged_at = Date.now();
    alert.acknowledged_by = by;
    return true;
  }

  getAlertStats(): { total: number; unacknowledged: number; critical: number; warning: number } {
    const total = this.alerts.length;
    const unacknowledged = this.alerts.filter(a => !a.acknowledged).length;
    const critical = this.alerts.filter(a => a.severity === "critical").length;
    const warning = this.alerts.filter(a => a.severity === "warning").length;
    return { total, unacknowledged, critical, warning };
  }

  // --- Alert Evaluation ---

  evaluateAlerts(
    inspection: InspectionConfig,
    workerId: string,
    data: Record<string, unknown>,
    resultId: string,
  ): AlertEvalResult[] {
    return inspection.alert_rules.map((rule, idx) => {
      const rawValue = this.resolveMetric(data, rule.metric);
      const actualStr = String(rawValue ?? "");
      const thresholdStr = String(rule.threshold);
      const triggered = this.compareValues(rawValue, rule.threshold, rule.operator);

      if (triggered) {
        const message = rule.message
          .replace(/{metric}/g, rule.metric)
          .replace(/{value}/g, actualStr)
          .replace(/{threshold}/g, thresholdStr)
          .replace(/{worker_id}/g, workerId);

        const alert: AlertEvent = {
          id: resultId + "-alert-" + idx,
          inspection_id: inspection.id,
          inspection_name: inspection.name,
          worker_id: workerId,
          timestamp: Date.now(),
          severity: rule.severity,
          message,
          result_id: resultId,
          acknowledged: false,
        };
        this.storeAlert(alert);
      }

      return {
        rule_index: idx,
        metric: rule.metric,
        expected: rule.operator + " " + thresholdStr,
        actual: actualStr,
        operator: rule.operator,
        severity: rule.severity,
        triggered,
        message: triggered
          ? "ALERT: " + rule.metric + " = " + actualStr + " (expected " + rule.operator + " " + thresholdStr + ")"
          : "OK: " + rule.metric + " = " + actualStr,
      };
    });
  }
  private resolveMetric(data: Record<string, unknown>, metric: string): unknown {
    const keys = metric.split(".");
    let value: unknown = data;
    for (const key of keys) {
      if (value && typeof value === "object") {
        value = (value as Record<string, unknown>)[key];
      } else {
        return undefined;
      }
    }
    return value;
  }

  private compareValues(actual: unknown, threshold: unknown, operator: string): boolean {
    // Null checks
    if (actual === undefined || actual === null) return operator === "!=";

    // Numeric comparison
    const numActual = typeof actual === "number" ? actual : Number(actual);
    const numThreshold = typeof threshold === "number" ? threshold : Number(threshold);

    if (!isNaN(numActual) && !isNaN(numThreshold)) {
      switch (operator) {
        case ">": return numActual > numThreshold;
        case "<": return numActual < numThreshold;
        case "==": return numActual === numThreshold;
        case "!=": return numActual !== numThreshold;
      }
    }

    // String comparison
    const strActual = String(actual);
    const strThreshold = String(threshold);
    switch (operator) {
      case "==": return strActual === strThreshold;
      case "!=": return strActual !== strThreshold;
      case "contains": return strActual.includes(strThreshold);
      case "not_contains": return !strActual.includes(strThreshold);
      default: return false;
    }
  }
}

