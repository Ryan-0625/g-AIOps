import { Registry } from "../store/registry";

/**
 * Interceptor checks whether an action requires approval before execution.
 *
 * Decision logic:
 * 1. Look up the action's risk level from the Worker's capability advertisement.
 * 2. "readonly" → always allowed (no approval needed).
 * 3. "write" → requires approval.
 * 4. "dangerous" → requires approval + secondary confirmation.
 *
 * Falls back to a hardcoded high-risk list when no Worker has advertised the action yet.
 */
const FALLBACK_HIGH_RISK = new Set([
  "service.restart",
  "service.stop",
  "exec.run",
  "process.kill",
]);

export interface InterceptResult {
  allowed: boolean;
  requiresApproval: boolean;
  riskLevel: string;
}

export class Interceptor {
  private highRiskSet: Set<string>;

  constructor(
    private registry: Registry,
    highRiskActions?: string[],
  ) {
    this.highRiskSet = new Set(highRiskActions ?? FALLBACK_HIGH_RISK);
  }

  intercept(action: string): InterceptResult {
    const level = this.registry.getRiskLevel(action) || "readonly";

    switch (level) {
      case "dangerous":
        return { allowed: false, requiresApproval: true, riskLevel: "dangerous" };
      case "write":
        return { allowed: false, requiresApproval: true, riskLevel: "write" };
      case "readonly":
        return { allowed: true, requiresApproval: false, riskLevel: "readonly" };
      default:
        // Fallback for unknown risk levels.
        if (this.highRiskSet.has(action)) {
          return { allowed: false, requiresApproval: true, riskLevel: "unknown" };
        }
        return { allowed: true, requiresApproval: false, riskLevel: "unknown" };
    }
  }
}
