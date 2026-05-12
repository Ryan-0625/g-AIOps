import { Envelope } from "../protocol/types";
import { Registry } from "../store/registry";
import { createLogger } from "../logger";

const logger = createLogger("master");

export type ApprovalStatus = "pending" | "approved" | "rejected" | "expired";

export interface ApprovalRequest {
  id: string;
  envelope: Envelope;
  targetWorkerId: string;
  createdAt: number;
  expiresAt: number;
  status: ApprovalStatus;
}

type ApprovalCallback = (req: ApprovalRequest) => void;

/**
 * Approver manages human approval for high-risk operations.
 *
 * An approval request expires after APPROVAL_TIMEOUT_MS. When approving,
 * the Approver checks the target Worker is still online — if not, the
 * approval is rejected with "worker offline".
 */
export class Approver {
  private active = new Map<string, ApprovalRequest>();
  private readonly APPROVAL_TIMEOUT_MS = 300_000; // 5 minutes

  constructor(
    private registry: Registry,
    private onReject?: ApprovalCallback,
    private onApprove?: ApprovalCallback,
  ) {}

  requestApproval(env: Envelope, targetWorkerId: string): ApprovalRequest {
    const req: ApprovalRequest = {
      id: env.msg_id,
      envelope: env,
      targetWorkerId,
      createdAt: Date.now(),
      expiresAt: Date.now() + this.APPROVAL_TIMEOUT_MS,
      status: "pending",
    };

    this.active.set(req.id, req);

    // Auto-expire.
    setTimeout(() => {
      const current = this.active.get(req.id);
      if (current && current.status === "pending") {
        current.status = "expired";
        const online = this.registry.isOnline(targetWorkerId);
        logger.warn("Approval expired", {
          msg_id: req.id,
          data: { targetWorkerId, workerOnline: online },
        });
        this.active.delete(req.id);
        this.onReject?.(current);
      }
    }, this.APPROVAL_TIMEOUT_MS);

    return req;
  }

  approve(approvalId: string): { success: boolean; workerStillOnline: boolean } {
    const req = this.active.get(approvalId);
    if (!req || req.status !== "pending") {
      return { success: false, workerStillOnline: false };
    }

    const online = this.registry.isOnline(req.targetWorkerId);
    if (!online) {
      req.status = "expired";
      this.active.delete(approvalId);
      return { success: false, workerStillOnline: false };
    }

    req.status = "approved";
    this.active.delete(approvalId);
    this.onApprove?.(req);
    return { success: true, workerStillOnline: true };
  }

  reject(approvalId: string): boolean {
    const req = this.active.get(approvalId);
    if (!req || req.status !== "pending") return false;
    req.status = "rejected";
    this.active.delete(approvalId);
    this.onReject?.(req);
    return true;
  }

  pendingCount(): number {
    return this.active.size;
  }
}
