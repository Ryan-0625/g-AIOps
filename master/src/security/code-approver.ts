/**
 * CodeApprover — 工具代码安全审批
 *
 * 对于 Brain 生成的工具代码，在部署前执行安全检查:
 * 1. 静态规则扫描（禁止的危险模式）
 * 2. 风险等级评估
 * 3. 高风险代码 → 需要人工审批
 */
import { createLogger } from "../logger";

const logger = createLogger("master");

export interface CodeApprovalResult {
  approved: boolean;
  reason?: string;
  requiresHumanReview: boolean;
  warnings?: string[];
}

const DANGEROUS_PATTERNS: RegExp[] = [
  /rm\s+(-rf?)\s+\//,
  /mkfs\.\w+/,
  /dd\s+if=.*of=\/dev\//,
  /chmod\s+777/,
  /(bash|sh|perl|python).*(-i|>&\/dev\/tcp\/)/,
  /chown\s+/,
  /reboot|shutdown\s+-[rh]/,
  /curl\s+.*\|.*(bash|sh)/,
];

export class CodeApprover {
  async approveCode(
    action: string,
    code: string,
    riskLevel: string,
  ): Promise<CodeApprovalResult> {
    const warnings: string[] = [];

    // 1. Scan for dangerous patterns.
    for (const pattern of DANGEROUS_PATTERNS) {
      if (pattern.test(code)) {
        warnings.push(`Dangerous pattern matched: ${pattern.source}`);
      }
    }

    if (warnings.length > 0) {
      logger.warn("Code approval rejected by static analysis", {
        action,
        data: { warnings },
      });
      return {
        approved: false,
        reason: "Static analysis failed",
        requiresHumanReview: true,
        warnings,
      };
    }

    // 2. Check risk level.
    if (riskLevel === "dangerous") {
      return {
        approved: false,
        reason: "Dangerous risk level requires human approval",
        requiresHumanReview: true,
      };
    }

    // 3. Read-only tools are auto-approved.
    if (riskLevel === "readonly") {
      return {
        approved: true,
        requiresHumanReview: false,
      };
    }

    // 4. Write tools need light review (auto-approve for now, but log).
    logger.info("Write-level tool auto-approved", { action });
    return {
      approved: true,
      requiresHumanReview: false,
    };
  }
}
