import { healthRouter } from "../health";
import { Registry } from "../../store/registry";
import { Tracker } from "../../orchestrator/tracker";

describe("Health Router", () => {
  let registry: Registry;
  let tracker: Tracker;
  let cfg: any;

  beforeEach(() => {
    registry = new Registry();
    tracker = new Tracker();
    cfg = { cluster_token: "test-token" };
  });

  it("returns a router function", () => {
    const router = healthRouter(registry, tracker, null as any, cfg);
    expect(router).toBeDefined();
    expect(typeof router).toBe("function");
  });

  it("reports worker count as 0 when no workers connected", () => {
    expect(registry.onlineCount()).toBe(0);
  });
});
