import { SlidingWindowRateLimiter } from "../flow-control";

describe("SlidingWindowRateLimiter", () => {
  it("allows first event within limit", () => {
    const limiter = new SlidingWindowRateLimiter(1000, 5);
    expect(limiter.allow("worker-1")).toBe(true);
  });

  it("allows up to max events within window", () => {
    const limiter = new SlidingWindowRateLimiter(1000, 3);
    expect(limiter.allow("w1")).toBe(true);
    expect(limiter.allow("w1")).toBe(true);
    expect(limiter.allow("w1")).toBe(true);
  });

  it("blocks when exceeding max events", () => {
    const limiter = new SlidingWindowRateLimiter(1000, 2);
    expect(limiter.allow("w1")).toBe(true);
    expect(limiter.allow("w1")).toBe(true);
    expect(limiter.allow("w1")).toBe(false);
  });

  it("allows different workers independently", () => {
    const limiter = new SlidingWindowRateLimiter(1000, 1);
    expect(limiter.allow("w1")).toBe(true);
    expect(limiter.allow("w1")).toBe(false);
    expect(limiter.allow("w2")).toBe(true);
    expect(limiter.allow("w2")).toBe(false);
  });

  it("resets clears worker tracking", () => {
    const limiter = new SlidingWindowRateLimiter(1000, 1);
    expect(limiter.allow("w1")).toBe(true);
    expect(limiter.allow("w1")).toBe(false);
    limiter.reset("w1");
    expect(limiter.allow("w1")).toBe(true);
  });

  it("reap removes idle workers", () => {
    const limiter = new SlidingWindowRateLimiter(10, 5);
    limiter.allow("w1");
    limiter.allow("w2");
    expect(limiter.size()).toBe(2);

    // Wait for window to pass, then reap.
    return new Promise<void>((resolve) => {
      setTimeout(() => {
        const removed = limiter.reap();
        expect(removed).toBe(2);
        expect(limiter.size()).toBe(0);
        resolve();
      }, 20);
    });
  });

  it("reap does not remove active workers", () => {
    const limiter = new SlidingWindowRateLimiter(1000, 5);
    limiter.allow("w1");
    limiter.allow("w2");

    const removed = limiter.reap();
    expect(removed).toBe(0);
    expect(limiter.size()).toBe(2);
  });

  it("size returns tracked worker count", () => {
    const limiter = new SlidingWindowRateLimiter(1000, 5);
    expect(limiter.size()).toBe(0);
    limiter.allow("w1");
    expect(limiter.size()).toBe(1);
    limiter.allow("w2");
    expect(limiter.size()).toBe(2);
  });

  it("allows event after window passes", () => {
    const limiter = new SlidingWindowRateLimiter(50, 1);
    expect(limiter.allow("w1")).toBe(true);
    expect(limiter.allow("w1")).toBe(false);

    return new Promise<void>((resolve) => {
      setTimeout(() => {
        expect(limiter.allow("w1")).toBe(true);
        resolve();
      }, 60);
    });
  });
});
