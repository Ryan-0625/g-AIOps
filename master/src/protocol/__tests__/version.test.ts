import { negotiate } from "../version";

describe("negotiate", () => {
  it("picks highest common minor version", () => {
    expect(negotiate({ min: "1.0", max: "1.3" }, { min: "1.0", max: "1.5" })).toBe("1.3");
    expect(negotiate({ min: "1.0", max: "1.5" }, { min: "1.2", max: "1.4" })).toBe("1.4");
    expect(negotiate({ min: "1.0", max: "1.0" }, { min: "1.0", max: "1.0" })).toBe("1.0");
  });

  it("returns null on major version mismatch", () => {
    expect(negotiate({ min: "1.0", max: "1.5" }, { min: "2.0", max: "2.1" })).toBeNull();
  });

  it("returns null on no overlapping minor range", () => {
    expect(negotiate({ min: "1.0", max: "1.2" }, { min: "1.3", max: "1.5" })).toBeNull();
  });
});
