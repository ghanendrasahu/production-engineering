# Workflow — Performance Optimization

Use when latency regresses, throughput plateaus, or cost per request balloons. Strictly in order — skipping steps is how you optimize the wrong thing for a month.

## Step 1 — Prove the Problem

- Metric: which percentile/route/tenant regressed? (p50 vs p95 vs p99; staging vs prod)
- Window: since when? Correlate against deploys, migrations, traffic shift, expiry of TTLs.
- Blast radius: user-facing? internal batch? one tenant?

If no regression exists, stop — you're done (and should say so).

## Step 2 — Baseline & Budget

Capture p50/p95/p99 per route + the dependency breakdown for the slow path (gateway → service → DB → cache → external). Write the latency budget per hop. Profile with py-spy/pyinstrument (app), `EXPLAIN (ANALYZE, BUFFERS)` (DB), APM/OTel traces.

## Step 3 — Rank the Offenders

Produce a table: `hop → cost_ms → % of request → action candidate → expected win`. Optimize the top item only. Typical findings in order of frequency:

1. Missing index / bad plan (often 10-100x) → `#25`, `#26`
2. N+1 → selectinload / batched IN queries → `#27`
3. Connection pool exhaustion (wait visible in pool metrics) → `#28`
4. No cache / bad invalidation on hot read → `#2`, `#50`, `#2_caching`
5. Serialization overhead → orjson, protobuf
6. Lock contention / deadlocks → `#36`, `#37`, `#40`
7. Payload too large → compression, field selection, CDN

## Step 4 — Fix, Measure, Repeat

Change one thing; re-run the load test at the same concurrency; p99 and cost targets; keep or revert with data, not opinion. Cache before you add replicas — compute is usually cheaper to eliminate than capacity to add.

## Step 5 — Verify the Tail

On 2x-peak load: p99 within budget; cache-hit ratio; error rate; **cost per request** (`#88`) did not regress. Hedged requests only for idempotent reads with headroom (`#94`).

## Step 6 — Prevent Regression

Add the benchmark to CI (nightly k6 thresholds); `EXPLAIN` diff in PR for changed queries; dashboard the metric on the service board; write the before/after into the PR description; update SLO if the baseline moved legitimately.
