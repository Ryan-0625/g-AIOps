/**
 * Master configuration loader.
 *
 * Loads config/master.yaml and merges with environment variable overrides.
 * Priority: environment variable > YAML file > code default.
 */

import fs from "fs";
import path from "path";
import yaml from "js-yaml";

// 鈹€鈹€ Type 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

export interface MasterConfig {
  server: {
    host: string;
    ws_port: number;
    api_port: number;
    ws: {
      max_connections: number;
      connection_rate_limit: number;
      heartbeat_check_interval: number;
    };
    api: {
      rate_limit: number;
      body_limit: string;
    };
  };
  cluster_token: string;
  security: {
    high_risk_actions: string[];
    approval_timeout: number;
  };
  worker: {
    heartbeat_miss_tolerance: number;
  };
  orchestrator: {
    max_pending: number;
    pending_ttl: number;
    broadcast_timeout: number;
    chunk_timeout: number;
  };
  priority: {
    aging: {
      p0_to_p1_after: number;
      p1_to_p2_after: number;
    };
  };
  logging: {
    level: string;
    format: string;
  };
  audit: {
    log_path: string;
    enabled: boolean;
  };
  inspection: {
    enabled: boolean;
    max_inspections: number;
    max_alerts: number;
    tick_interval_ms: number;
    default_interval_seconds: number;
    probe_timeout_seconds: number;
  };
}

// 鈹€鈹€ Defaults 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

const DEFAULTS: MasterConfig = {
  server: {
    host: "0.0.0.0",
    ws_port: 32080,
    api_port: 32080,
    ws: {
      max_connections: 5000,
      connection_rate_limit: 50,
      heartbeat_check_interval: 30,
    },
    api: {
      rate_limit: 120,
      body_limit: "5mb",
    },
  },
  cluster_token: "dev-token-change-in-production",
  security: {
    high_risk_actions: ["service.restart", "service.stop", "exec.run", "process.kill"],
    approval_timeout: 300,
  },
  worker: {
    heartbeat_miss_tolerance: 3,
  },
  orchestrator: {
    max_pending: 10000,
    pending_ttl: 300,
    broadcast_timeout: 10,
    chunk_timeout: 30,
  },
  priority: {
    aging: {
      p0_to_p1_after: 60,
      p1_to_p2_after: 120,
    },
  },
  logging: {
    level: "info",
    format: "json",
  },
  audit: {
    log_path: "/var/log/gaiops/audit.log",
    enabled: true,
  },
  inspection: {
    enabled: true,
    max_inspections: 100,
    max_alerts: 5000,
    tick_interval_ms: 10000,
    default_interval_seconds: 300,
    probe_timeout_seconds: 30,
  },
};

// 鈹€鈹€ Helper: deep merge (simple 1-level scalar override) 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

function mergeConfig(base: MasterConfig, overrides: Partial<MasterConfig>): MasterConfig {
  const result = { ...base };
  for (const key of Object.keys(overrides) as (keyof MasterConfig)[]) {
    const val = overrides[key];
    if (val !== undefined) {
      if (typeof val === "object" && !Array.isArray(val) && typeof result[key] === "object") {
        (result as any)[key] = { ...(result as any)[key], ...val };
      } else {
        (result as any)[key] = val;
      }
    }
  }
  return result;
}

// 鈹€鈹€ Env overrides 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

function envOverrides(): Partial<MasterConfig> {
  const overrides: Partial<MasterConfig> = {};

  if (process.env.MASTER_PORT) {
    const port = parseInt(process.env.MASTER_PORT, 10);
    overrides.server = {
      ...DEFAULTS.server,
      ws_port: port,
      api_port: port,
    };
  }
  if (process.env.CLUSTER_TOKEN) {
    overrides.cluster_token = process.env.CLUSTER_TOKEN;
  }
  if (process.env.AUDIT_LOG_PATH) {
    overrides.audit = { ...DEFAULTS.audit, log_path: process.env.AUDIT_LOG_PATH };
  }
  if (process.env.AUDIT_ENABLED !== undefined) {
    overrides.audit = { ...(overrides.audit || DEFAULTS.audit), enabled: process.env.AUDIT_ENABLED !== "false" };
  }
  if (process.env.LOG_LEVEL) {
    overrides.logging = { ...DEFAULTS.logging, level: process.env.LOG_LEVEL };
  }
  if (process.env.TLS_CERT_PATH && process.env.TLS_KEY_PATH) {
    // TLS info is consumed directly in index.ts from env
  }
  if (process.env.INSPECTION_ENABLED !== undefined) {
    overrides.inspection = { ...DEFAULTS.inspection, enabled: process.env.INSPECTION_ENABLED !== "false" };
  }

  return overrides;
}

// 鈹€鈹€ Load 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

let cached: MasterConfig | null = null;

/**
 * load reads and caches the configuration.
 *
 * Search order:
 *   1. MASTER_CONFIG_PATH env (absolute path)
 *   2. config/master.yaml relative to package root
 *   3. Defaults only
 */
export function load(): MasterConfig {
  if (cached) return cached;

  let fromFile: Partial<MasterConfig> = {};

  const configPath = process.env.MASTER_CONFIG_PATH || findConfigPath();
  if (configPath && fs.existsSync(configPath)) {
    try {
      const raw = yaml.load(fs.readFileSync(configPath, "utf-8")) as Record<string, any>;
      if (raw && typeof raw === "object") {
        fromFile = raw as unknown as Partial<MasterConfig>;
      }
    } catch (err) {
      console.error(`[config] Failed to parse ${configPath}:`, err);
    }
  }

  const merged = mergeConfig(DEFAULTS, fromFile);
  cached = mergeConfig(merged, envOverrides());
  return cached;
}

function findConfigPath(): string {
  // Walk up from __dirname to find project root containing config/
  let dir = path.resolve(__dirname, "..");
  for (let i = 0; i < 5; i++) {
    const candidate = path.join(dir, "config", "master.yaml");
    if (fs.existsSync(candidate)) return candidate;
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return "";
}

// 鈹€鈹€ Validation 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

export interface ConfigWarning {
  field: string;
  message: string;
}

export interface ConfigError {
  field: string;
  message: string;
}

/**
 * validate checks the loaded config for production-readiness.
 * Returns lists of warnings (non-fatal) and errors (fatal).
 */
export function validate(cfg: MasterConfig): { warnings: ConfigWarning[]; errors: ConfigError[] } {
  const warnings: ConfigWarning[] = [];
  const errors: ConfigError[] = [];

  // Cluster token must not be the dev default.
  if (cfg.cluster_token === "dev-token-change-in-production") {
    warnings.push({ field: "cluster_token", message: "Using dev default 鈥?set CLUSTER_TOKEN env var for production" });
  }
  if (cfg.cluster_token.length < 8) {
    warnings.push({ field: "cluster_token", message: `Length ${cfg.cluster_token.length} is short (recommend >= 16 chars)` });
  }

  // Numeric bounds.
  if (cfg.server.ws.max_connections <= 0) {
    errors.push({ field: "server.ws.max_connections", message: `Must be > 0, got ${cfg.server.ws.max_connections}` });
  }
  if (cfg.server.ws.connection_rate_limit <= 0) {
    errors.push({ field: "server.ws.connection_rate_limit", message: `Must be > 0, got ${cfg.server.ws.connection_rate_limit}` });
  }
  if (cfg.server.api.rate_limit <= 0) {
    errors.push({ field: "server.api.rate_limit", message: `Must be > 0, got ${cfg.server.api.rate_limit}` });
  }
  if (cfg.worker.heartbeat_miss_tolerance <= 0) {
    errors.push({ field: "worker.heartbeat_miss_tolerance", message: `Must be > 0, got ${cfg.worker.heartbeat_miss_tolerance}` });
  }
  if (cfg.orchestrator.max_pending <= 0) {
    errors.push({ field: "orchestrator.max_pending", message: `Must be > 0, got ${cfg.orchestrator.max_pending}` });
  }
  if (cfg.orchestrator.pending_ttl <= 0) {
    errors.push({ field: "orchestrator.pending_ttl", message: `Must be > 0, got ${cfg.orchestrator.pending_ttl}` });
  }
  if (cfg.security.approval_timeout <= 0) {
    errors.push({ field: "security.approval_timeout", message: `Must be > 0, got ${cfg.security.approval_timeout}` });
  }
  if (cfg.server.api.body_limit) {
    const match = cfg.server.api.body_limit.match(/^(\d+)(mb|kb|gb)$/i);
    if (!match) {
      errors.push({ field: "server.api.body_limit", message: `Invalid format: ${cfg.server.api.body_limit} (expected e.g. 5mb)` });
    }
  }

  // TLS cert file existence.
  const tlsCert = process.env.TLS_CERT_PATH;
  const tlsKey = process.env.TLS_KEY_PATH;
  if (tlsCert && !fs.existsSync(tlsCert)) {
    errors.push({ field: "TLS_CERT_PATH", message: `File not found: ${tlsCert}` });
  }
  if (tlsKey && !fs.existsSync(tlsKey)) {
    errors.push({ field: "TLS_KEY_PATH", message: `File not found: ${tlsKey}` });
  }

  return { warnings, errors };
}

/** Reset cache (for tests). */
export function reset(): void {
  cached = null;
}

