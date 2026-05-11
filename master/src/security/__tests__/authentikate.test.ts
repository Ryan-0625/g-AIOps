import { authenticate, extractBearer } from "../authentikate";

describe("authenticate", () => {
  it("accepts matching token", () => {
    expect(authenticate("secret", "secret")).toBe(true);
  });

  it("rejects mismatching token", () => {
    expect(authenticate("secret", "wrong")).toBe(false);
  });

  it("rejects empty token", () => {
    expect(authenticate("", "secret")).toBe(false);
  });
});

describe("extractBearer", () => {
  it("extracts token from header", () => {
    expect(extractBearer("Bearer mytoken123")).toBe("mytoken123");
  });

  it("returns null for missing header", () => {
    expect(extractBearer(undefined)).toBeNull();
  });

  it("returns null for malformed header", () => {
    expect(extractBearer("Basic dXNlcjpwYXNz")).toBeNull();
  });
});
