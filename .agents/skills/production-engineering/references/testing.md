# Testing Reference — Verifying Production Behavior

Testing is the verification arm of every topic in this library. This file is the cross-topic playbook: what to test at each layer, how to test failure paths, and how the test suite earns its place in CI.

## The Testing Pyramid for Services

| Layer | Scope | Tools | Speed | Notes |
| --- | --- | --- | --- | --- |
| Unit | Pure functions, small classes | pytest (+ `hypothesis`) | ms | Mock nothing you can avoid; test the logic, not the framework. |
| Component | One service + real DB | pytest + testcontainers (Postgres, Redis) | 1-10s | Transactions must roll back; assert invariants (`stock >= 0`). |
| Integration | Service ↔ neighbors | docker-compose + httpx/grpc clients | 10-60s | Real protocols (HTTP/gRPC), fake third parties (Wiremock). |
| Contract | Producer/consumer agreement | Pact, or schema validation in CI | seconds | Broken-consumer detection before merge. |
| E2E/Smoke | Deployed env | blackbox probe, k6 smoke | seconds | Post-deploy gate; keep tiny. |
| Load/Chaos | SLOs under stress | k6, Locust, toxiproxy, chaos-mesh | minutes | Staging only; measure p50/p95/p99; find the wall. |

## Failure-Path Tests (the tests that actually catch production bugs)

Every fallback deserves a test — happy-path-only suites protect nothing:

- **Timeout**: monkeypatch the client to sleep > timeout; assert the 504/503/fallback path and that nothing hangs.
- **Retry exhaustion**: fake fails N times then succeeds; assert attempts == N+1 and final success; fake always fails → assert DLQ write + alert emission.
- **Idempotency**: call the endpoint twice with the same `Idempotency-Key`; assert one side effect and identical responses (also under concurrency: `asyncio.gather × 20`).
- **Circuit breaker**: N consecutive failures → open; assert short-circuit without network; half-open probe recovers.
- **Pool exhaustion**: fill the pool; assert clean 429/503, not thread starvation — and recover after release.
- **Cache stampede**: expire a hot key; 20 concurrent readers; assert a single origin call (single-flight lock works).
- **Deadlock victim**: two transactions lock A→B and B→A; assert one aborts, the retried one commits, invariant holds.
- **Migration**: up → assert `alembic check` clean → downgrade → assert schema clean → upgrade again. Run against a seeded copy at ≥1M rows for index/backfill realism.
- **N+1**: count queries per request with an event listener (`before_cursor_execute`); assert ≤ expected constant.

## The Query-Count Test (copy-pasta worth having)

```python
def test_no_n_plus_one(db_session, client):
    calls = []
    def _count(*args, **kwargs): calls.append(1)
    event.listen(engine, "before_cursor_execute", lambda *a, **k: _count())
    resp = client.get("/api/orders")   # page of 50
    event.remove(engine, "before_cursor_execute", ...)
    assert resp.status_code == 200
    assert len(calls) <= 4             # 1 orders + 1 batched children + 2 auth lookups
```

## Load Testing Basics

- Ramp to **2x expected peak**, hold 5-10 minutes; watch p95/p99 (not averages), queue depths, pool wait, 5xx.
- Warm and cold cache runs are different tests — measure both; cold start (`#89`) belongs in the report.
- Capacity test answers: at what RPS does p99 breach SLO? That's your headroom math (`#92`).
- k6 thresholds: `http_req_duration: ['p(95)<300', 'p(99)<800']`, `http_req_failed: ['rate<0.01']` — fail the build when wrong.

## Chaos in Tests

Kill dependencies in staging and assert the degradation contract: dependency down → breaker opens → fallback (cached/degraded) served → metric emitted → alert fires. Re-run quarterly; postmortems convert chaos findings into tests.

## CI Gates (in dependency order)

1. lint + format (ruff), types (mypy/ty)
2. unit + component (`pytest tests/ -q`)
3. migration up/down on seeded copy
4. contract tests
5. security scans (bandit/pip-audit/osv-scanner)
6. build + image scan (trivy)
7. deploy staging → smoke → load (nightly)

**Rule:** a test that cannot fail for the bug you fear is not a test for that bug — write it until you've watched it fail.
