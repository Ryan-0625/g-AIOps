import { Router, Request, Response } from "express";
import { Registry } from "../store/registry";
import { Tracker } from "../orchestrator/tracker";
import { Approver } from "../security/approver";

export function healthRouter(registry: Registry, tracker: Tracker, approver: Approver): Router {
  const router = Router();

  router.get("/health", (_req: Request, res: Response) => {
    res.json({
      status: "ok",
      uptime: process.uptime(),
      workers: {
        online: registry.onlineCount(),
      },
      orchestrator: {
        pending: tracker.pendingCount(),
      },
      security: {
        pendingApprovals: approver.pendingCount(),
      },
    });
  });

  return router;
}
