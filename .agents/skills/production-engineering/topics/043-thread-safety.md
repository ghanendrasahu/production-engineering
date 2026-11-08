---
topic: 43
title: Thread Safety
category: B
skill: production-engineering
status: stable
---

# 043 — Thread Safety

## 1. Topic name and metadata

- **Number:** 43 of 111
- **Title:** Thread Safety
- **Category:** B — Database Engineering and Distributed Systems
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [distributed-systems.md](../references/distributed-systems.md)
- **Topic file:** `.agents/skills/production-engineering/topics/043-thread-safety.md`

## 2. What it is

A property of code that is correct when accessed by multiple threads concurrently — no data races, corrupted invariants, or visibility anomalies.

## 3. Why it exists

Two threads on shared mutable state: correctness is a decision, not luck.

## 4. The engineering problem it solves

Concurrent access to shared mutable state produces heisenbugs that pass all tests and corrupt production data exactly when it matters most (payroll, midnight batch).

## 5. How it works internally

Data race = two threads access same memory, at least one writes, no synchronization. Fixes: mutual exclusion (locks/semaphores), atomic operations (CAS), immutability, message passing (CSP/actor model), thread-local storage, confinement. CPython's GIL serializes bytecode — protects the interpreter, **not** your invariants: check-then-act across bytecodes still races, and the GIL is per-interpreter (3.13+ per-subinterpreter GILs change the picture).asyncio is single-threaded — races appear between await points, not between bytecodes; `asyncio.Lock` covers await-spanning critical sections.

## 6. Architecture and design principles

In-process concurrency model; crosses into distributed coordination at `#38`.

**Design principles for this category:** Measure before mutating; the primary is the system of record; correctness invariants belong in constraints and transactions, not app code.

## 7. When to use it

Always — review every shared mutable object.

## 8. When NOT to use it

Pure functions, no shared state (ideal).

**Alternatives:** immutable data structures, single-writer event pipelines, processes over threads (fork isolation), SQLite/Postgres for coordination.

## 9. Implementation strategies

```python
import threading
_lock = threading.Lock()
_counter = 0
def increment():
    global _counter
    with _lock:
        _counter += 1

import asyncio
_alock = asyncio.Lock()
async def aupdate(state):
    async with _alock:
        state.total += state.amount
```

Rules: no mutable module-level globals mutated per request; use immutable DTOs; queue-based handoff (`queue.Queue`, asyncio.Queue) for producer/consumer; `concurrent.futures` with proper futures handling; thread-local DB sessions.

## 10. Production-grade implementation

**Scenario:** A global `dict` metrics registry in a sync Flask shim under gunicorn threads: concurrent `+=` lost 0.3% increments; fixed with `threading.Lock` (or `prometheus_client` its own locking — delegate to it).

**To reach production grade, combine the implementation in section 9 with these non-negotiables:**

- Wire the section 19 signals into dashboards and alerts *before* the rollout — an unmeasured control is decorative.
- Bake the control into the pipeline, not the runbook: IaC/CI enforces it on every deploy; humans should not be the enforcement layer (`#6 CI/CD`, `#104 Infrastructure as Code`).
- Load and failure-test it at 2x expected traffic, in staging with production-like data volume, before declaring it done (`#26 Query Optimization`, `#91 Latency`).
- Roll out behind a canary or flag with automatic rollback on SLO burn (`#53 Canary Releases`, `#51 Feature Flags`), and document the rollback path in the runbook.
- Verify the dependent data path explicitly: migrations, secrets, certificates, and IAM policies ship with the same change.

## 11. Code examples (inline in section 9)

This concept has no standalone Python surface — its artifacts are configuration,
templates, or pipeline steps. All runnable material for it lives inline in **section 9 (Implementation strategies)** and **section 12 (FastAPI integration)** where applicable. Do not force a toy example here.

## 12. FastAPI integration where relevant

Handlers are async — shared request-independent clients (httpx, Redis) fine; per-request state passed as parameters; never store per-request data on module-level objects; sync endpoints (def) run in a threadpool — avoid shared mutable singletons entirely; middleware must not hold references across requests.

## 13. Distributed-system considerations

Distributed state is the hard part: replicas, shards, and lock holders disagree by milliseconds; correctness must survive that disagreement — single-writer, consensus, or commutative designs.

## 14. AI/ML/LLM application examples where relevant

Token counters, caches, and tool registries are shared state — asyncio.Lock within process; Redis/Postgres across.

## 15. Security considerations

Shared mutable state is a race condition waiting for a privilege boundary — confine state.

## 16. Performance considerations

DB performance dominates: connection pools, indexes, and lock discipline decide p99 more than any app code change.

## 17. Common mistakes

"The GIL makes me safe"; `global` counters without locks; mutable default arguments shared (def f(x, cache={})); check-then-act without lock; lock copied into background thread while original expires; asserting thread safety by running the test 1000 times on one machine.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `lock_wait_seconds` (app), race-detector counts in staging

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Stress tests: N threads hammering one counter, assert exact final value; hypothesis with concurrent futures; asyncio interleaving tests (gather with monkeypatched awaits); CI with forced GC/scheduling pressure; review of await boundaries in critical sections.

## 21. Deployment considerations

Ship with expand/contract migrations; zero-downtime requires old code on new schema during the roll — never deploy breaking DDL in the same release as the code that depends on it.

## 22. Production-readiness checklist

- [ ] Immutability by default (frozen dataclasses, tuples)
- [ ] Confine state
- [ ] Locks narrow and short
- [ ] Avoid shared state via message passing
- [ ] Use thread-safe primitives (Queue, prometheus_client)
- [ ] Review `await` spacing for invariant breaks
- [ ] Run with `PYTHONASYNCIODEBUG=1`
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Check-then-act race on shared cache (both compute, both write); double-checked locking without proper memory barriers; iterating a dict being mutated (RuntimeError); `list.append` is atomic-ish under GIL but logically not a transaction; coroutine race across `await` boundaries; requests leaking state through module globals; forked workers sharing CoW structures unexpectedly.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://docs.python.org/3/library/threading.html
- https://docs.python.org/3/library/asyncio-sync.html

**Related topics in this library:** `#39 Race Conditions`, `#44 Backpressure`, `#42 Garbage Collection`, `#40 Deadlocks` (in-process variant), `#38 Distributed Locks`.
