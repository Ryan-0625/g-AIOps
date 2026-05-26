import { CodeApprover } from "../code-approver";

describe("CodeApprover", () => {
  let approver: CodeApprover;

  beforeEach(() => {
    approver = new CodeApprover();
  });

  // U-M-36: Approve safe code
  it("should approve safe code [U-M-36]", async () => {
    const result = await approver.approveCode("system.info", "return os.hostname()", "readonly");
    expect(result.approved).toBe(true);
  });

  // U-M-36: Approve ping script
  it("should approve ping operation [U-M-36b]", async () => {
    const result = await approver.approveCode("ping.icmp", "ping -c 1 localhost", "readonly");
    expect(result.approved).toBe(true);
  });

  // U-M-37: Require human review for dangerous actions
  it("should require human review for dangerous action [U-M-37]", async () => {
    const result = await approver.approveCode("exec.run", "rm -rf /", "dangerous");
    expect(result.approved).toBe(false);
    expect(result.requiresHumanReview).toBe(true);
  });

  // U-M-37: Dangerous patterns in code
  it("should reject code with dangerous patterns [U-M-37b]", async () => {
    const result = await approver.approveCode("exec.run", "eval('rm -rf /')", "dangerous");
    expect(result.approved).toBe(false);
    expect(result.warnings?.length ?? 0).toBeGreaterThan(0);
  });

  // CHAOS-17: Malicious action name
  it("should handle malicious action name [CHAOS-17]", async () => {
    const result = await approver.approveCode("exec.run; rm -rf /", "echo test", "dangerous");
    expect(result.approved).toBe(false);
  });

  // Edge: Empty code
  it("should approve empty code for readonly actions", async () => {
    const result = await approver.approveCode("system.info", "", "readonly");
    expect(result.approved).toBe(true);
  });
});
