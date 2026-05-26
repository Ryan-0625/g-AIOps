import express from "express";
import request from "supertest";
import { inspectionApiRouter } from "../inspection-api";
import { InspectionStore, ProbeType } from "../../store/inspection-store";
import { Inspector } from "../../orchestrator/inspector";
import { Registry } from "../../store/registry";

jest.mock("../../server/ws-server");

describe("InspectionAPI", () => {
  function makeValidBody() {
    return {
      name: "Test Inspection",
      probe_type: "port.check",
      probe_params: { host: "localhost", port: 80 },
      schedule_mode: "interval",
      interval_seconds: 60,
      alert_rules: [
        { metric: "reachable", operator: "==", threshold: false, severity: "critical", message: "Port unreachable" },
      ],
    };
  }

  function createApp() {
    const store = new InspectionStore();
    const registry = new Registry();
    const inspector = new Inspector(store, registry, null as any);
    const app = express();
    app.use(express.json());
    app.use(inspectionApiRouter(store, inspector, registry, "test-token"));
    return { app, store };
  }

  // U-M-06: Create inspection
  it("should create inspection [U-M-06]", async () => {
    const { app } = createApp();
    const res = await request(app).post("/api/v1/inspections")
      .set("Authorization", "Bearer test-token").send(makeValidBody());
    expect(res.status).toBe(201);
    expect(res.body.id).toBeDefined();
  });

  // U-M-07: Invalid probe_type
  it("should reject invalid probe_type [U-M-07]", async () => {
    const { app } = createApp();
    const res = await request(app).post("/api/v1/inspections")
      .set("Authorization", "Bearer test-token")
      .send({ ...makeValidBody(), probe_type: "invalid" });
    expect(res.status).toBe(400);
  });

  // U-M-08: interval < 10
  it("should reject interval_seconds < 10 [U-M-08]", async () => {
    const { app } = createApp();
    const res = await request(app).post("/api/v1/inspections")
      .set("Authorization", "Bearer test-token")
      .send({ ...makeValidBody(), interval_seconds: 5 });
    expect(res.status).toBe(400);
  });

  // U-M-09: Update non-existent
  it("should return 404 on update non-existent [U-M-09]", async () => {
    const { app } = createApp();
    const res = await request(app).put("/api/v1/inspections/nonexistent")
      .set("Authorization", "Bearer test-token").send({ name: "X" });
    expect(res.status).toBe(404);
  });

  // U-M-10: Toggle
  it("should toggle enabled state [U-M-10]", async () => {
    const { app, store } = createApp();
    const c = await request(app).post("/api/v1/inspections")
      .set("Authorization", "Bearer test-token").send(makeValidBody());
    await request(app).post("/api/v1/inspections/" + c.body.id + "/toggle")
      .set("Authorization", "Bearer test-token");
    expect(store.getInspection(c.body.id)?.enabled).toBe(false);
  });

  // U-M-11: Manual run
  it("should trigger manual run [U-M-11]", async () => {
    const { app } = createApp();
    const c = await request(app).post("/api/v1/inspections")
      .set("Authorization", "Bearer test-token").send(makeValidBody());
    const r = await request(app).post("/api/v1/inspections/run/" + c.body.id)
      .set("Authorization", "Bearer test-token");
    expect(r.status).toBe(200);
  });

  // U-M-12: Alerts stats
  it("should return alert stats [U-M-12]", async () => {
    const { app, store } = createApp();
    store.createInspection({
      id: "alert-test", name: "Alert", enabled: true,
      probe_type: "port.check" as ProbeType, probe_params: { host: "localhost", port: 1 },
      target_mode: "all", schedule_mode: "interval", interval_seconds: 60, timeout_seconds: 5,
      alert_rules: [{ metric: "reachable", operator: "==", threshold: true, severity: "critical", message: "Test" }],
      notify_channels: ["log"], created_at: Date.now(), updated_at: Date.now(), created_by: "test",
    });
    const res = await request(app).get("/api/v1/alerts/stats")
      .set("Authorization", "Bearer test-token");
    expect(res.status).toBe(200);
    expect(res.body).toBeDefined();
  });

  // Route registration
  it("should register correct routes", () => {
    const s = new InspectionStore();
    const r = new Registry();
    const router = inspectionApiRouter(s, new Inspector(s, r, null as any), r, "t");
    const stack = (router as any).stack || [];
    expect(stack.length).toBeGreaterThan(0);
  });
});
