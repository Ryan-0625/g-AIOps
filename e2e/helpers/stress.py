"""Stress test runner — concurrent request execution with statistics."""

import asyncio
import time
from statistics import median, quantiles


class StressResult:
    """Aggregated stress-test statistics."""

    def __init__(self):
        self.total = 0
        self.success = 0
        self.failure = 0
        self.rate_limited = 0
        self.latencies: list[float] = []
        self.errors: list[str] = []

    @property
    def success_rate(self) -> float:
        return (self.success / self.total * 100) if self.total > 0 else 0.0

    def report(self) -> str:
        """Return a formatted stress-test report."""
        lines = [
            "=" * 50,
            "STRESS TEST REPORT",
            "=" * 50,
            f"Total requests:  {self.total}",
            f"Success:         {self.success} ({self.success_rate:.1f}%)",
            f"Failures:        {self.failure}",
            f"Rate limited:    {self.rate_limited}",
        ]
        if self.latencies:
            sorted_lats = sorted(self.latencies)
            p50 = median(sorted_lats)
            p95 = quantiles(sorted_lats, n=20)[18] if len(sorted_lats) >= 20 else sorted_lats[-1]
            p99 = quantiles(sorted_lats, n=100)[98] if len(sorted_lats) >= 100 else sorted_lats[-1]
            avg = sum(sorted_lats) / len(sorted_lats)
            lines.extend([
                "",
                f"Latency (seconds):",
                f"  min:    {min(sorted_lats):.4f}",
                f"  avg:    {avg:.4f}",
                f"  p50:    {p50:.4f}",
                f"  p95:    {p95:.4f}",
                f"  p99:    {p99:.4f}",
                f"  max:    {max(sorted_lats):.4f}",
            ])
        if self.errors:
            lines.extend(["", f"Sample errors ({min(5, len(self.errors))} shown):"])
            for err in self.errors[:5]:
                lines.append(f"  - {err}")
        lines.append("=" * 50)
        return "\n".join(lines)


class StressRunner:
    """Run concurrent requests and collect statistics.

    Usage::

        runner = StressRunner()
        result = await runner.run_concurrent(api_client, requests, concurrency=10)
        print(result.report())
    """

    async def run_concurrent(
        self,
        api_client,
        requests: list[dict],
        concurrency: int = 10,
    ) -> StressResult:
        """Execute a list of request configs concurrently with semaphore."""
        result = StressResult()
        sem = asyncio.Semaphore(concurrency)

        async def _execute(req: dict) -> None:
            async with sem:
                start = time.monotonic()
                try:
                    resp = await api_client.execute(**req)
                    elapsed = time.monotonic() - start
                    result.total += 1
                    result.latencies.append(elapsed)
                    if resp["status_code"] == 429:
                        result.rate_limited += 1
                        result.failure += 1
                    elif resp.get("status") == "failure":
                        result.failure += 1
                        err = resp.get("error", {})
                        if isinstance(err, dict):
                            err_code = err.get("code", "unknown")
                        else:
                            err_code = str(err)
                        if len(result.errors) < 100:
                            result.errors.append(
                                f"{req.get('action', '?')}: {err_code}"
                            )
                    else:
                        result.success += 1
                except Exception as e:
                    result.total += 1
                    result.failure += 1
                    if len(result.errors) < 100:
                        result.errors.append(f"{req.get('action', '?')}: {e}")

        await asyncio.gather(*[_execute(r) for r in requests])
        return result
