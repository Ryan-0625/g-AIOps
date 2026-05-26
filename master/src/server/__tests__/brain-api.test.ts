import { brainApiRouter } from "../brain-api";
import { Registry } from "../../store/registry";
import { Tracker } from "../../orchestrator/tracker";
import { Router as MasterRouter } from "../../orchestrator/router";
import { PriorityQueue } from "../../orchestrator/priority-queue";
import { Interceptor } from "../../security/interceptor";
import { Approver } from "../../security/approver";
import { WebSocketServer } from "../../server/ws-server";
import { MetricsCollector } from "../../store/metrics";
import express from "express";
import request from "supertest";

jest.mock("../../server/ws-server");

const CAPS = {
  actions: ["ping.icmp"],
  riskLevels: { "ping.icmp": "readonly" },
  timeouts: {},
  maxConcurrent: 5,
  workerVersion: "0.1.0",
  heartbeatInterval: 15,
};

describe("BrainAPI", () => {
  // U-M-03: Auth failure
  it("should reject invalid token [U-M-03]", async () => {
    const r = new Registry();
    const app = express();
    app.use(express.json());
    app.use(brainApiRouter(r, new PriorityQueue(), new MasterRouter(r), new Tracker(),
      null as any, new Interceptor(r), new Approver(r),
      new WebSocketServer(r, new Tracker(), new MasterRouter(r), new PriorityQueue(), "test-token") as any,
      "test-token", new MetricsCollector()));
    const res = await request(app).post("/api/v1/execute")
      .set("Authorization", "Bearer bad").send({ action: "ping", params: {}, trace_id: "t" });
    expect(res.status).toBe(401);
  });

  // U-M-03b: Missing auth
  it("should reject missing auth [U-M-03b]", async () => {
    const r = new Registry();
    const app = express();
    app.use(express.json());
    app.use(brainApiRouter(r, new PriorityQueue(), new MasterRouter(r), new Tracker(),
      null as any, new Interceptor(r), new Approver(r),
      new WebSocketServer(r, new Tracker(), new MasterRouter(r), new PriorityQueue(), "test-token") as any,
      "test-token", new MetricsCollector()));
    const res = await request(app).post("/api/v1/execute")
      .send({ action: "ping", params: {}, trace_id: "t" });
    expect(res.status).toBe(401);
  });

  // Routes registered
  it("should register routes", () => {
    const r = new Registry();
    const router = brainApiRouter(r, new PriorityQueue(), new MasterRouter(r),
      new Tracker(), null as any, new Interceptor(r), new Approver(r),
      new WebSocketServer(r, new Tracker(), new MasterRouter(r), new PriorityQueue(), "t") as any,
      "t", new MetricsCollector());
    const stack = (router as any).stack || [];
    expect(stack.length).toBeGreaterThan(0);
  });

  // U-M-01: Worker list (no auth)
  it("should reject worker list without auth", async () => {
    const r = new Registry();
    const app = express();
    app.use(express.json());
    app.use(brainApiRouter(r, new PriorityQueue(), new MasterRouter(r), new Tracker(),
      null as any, new Interceptor(r), new Approver(r),
      new WebSocketServer(r, new Tracker(), new MasterRouter(r), new PriorityQueue(), "test-token") as any,
      "test-token", new MetricsCollector()));
    const res = await request(app).get("/api/v1/workers");
    expect(res.status).toBe(401);
  });
});
