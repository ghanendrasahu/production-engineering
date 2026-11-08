---
topic: 41
title: Memory Leaks
category: B
skill: production-engineering
status: stable
---

# 041 — Memory Leaks

## 1. Topic name and metadata

- **Number:** 41 of 111
- **Title:** Memory Leaks
- **Category:** B — Database Engineering and Distributed Systems
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [distributed-systems.md](../references/distributed-systems.md)
- **Topic file:** `.agents/skills/production-engineering/topics/041-memory-leaks.md`

## 2. What it is

Memory allocated but never released, growing unboundedly over process lifetime — caches without eviction, unclosed resources, accumulating lists, reference cycles, or leaks in native extensions.

## 3. Why it exists

Unbounded growth kills processes hours after 'it works'.

## 4. The engineering problem it solves

The service works for hours then OOMs (Linux OOM-killer takes it down) or GC-thrash; Kubernetes restarts it in a crash loop; p99 latency spikes; data lost mid-request.

## 5. How it works internally

Python growth sources: module-level dict/list/set caches (no eviction); ORM session identity map holding objects; unclosed file/socket/DB handles; listener/callback registrations accumulating; C-extension leaks; circular references through __del__ (rare) — CPython ref counting usually cleans cycles via generational GC but cycles with finalizers can persist. Diagnose: `tracemalloc` snapshots diffed over hours, `objgraph` growth by type, `py-spy dump --native` for native, RSS trend via Prometheus `container_memory_working_set_bytes`. Restart band-aids mask but never fix — find the retained object.

## 6. Architecture and design principles

Any process: API servers, workers, schedulers. Leaks matter most in long-lived processes (not request-scoped ones).

**Design principles for this category:** Measure before mutating; the primary is the system of record; correctness invariants belong in constraints and transactions, not app code.

## 7. When to use it

Long-lived processes — always hunt leaks; batch jobs can be looser.

## 8. When NOT to use it

Short-lived CLI (not worth deep profiling).

**Alternatives:** process-per-request isolation (FaaS), scheduled restarts (band-aid, not a fix), bounded queues.

## 9. Implementation strategies

```python
import tracemalloc
tracemalloc.start()
snap1 = tracemalloc.take_snapshot()
# ...hours later...
for line in snap1.compare_to(tracemalloc.take_snapshot(), "lineno")[:10]:
    print(line)
```

Rules: caches use LRU with maxsize (functools.lru_cache(maxsize=512) / cachetools TTLCache); close resources (`with` / async context managers); SQLAlchemy sessions per-request and closed; no global mutable lists; periodic RSS alert (container_memory_working_set_bytes > 80% limit for 10min).

## 10. Production-grade implementation

**Scenario:** Embedding worker grew RSS 300MB → 4.2GB over 36h; tracemalloc showed a global list of every processed document's vector reference never cleared; fixed with bounded TTLCache; RSS flat at 700MB; alert added at 1.5GB.

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

Dependency creates/closes `Session` per request (GC'd); module-level `lru_cache` capped; streaming endpoints close upstream clients in finally; app factory avoids import-time globals holding refs.

## 13. Distributed-system considerations

Distributed state is the hard part: replicas, shards, and lock holders disagree by milliseconds; correctness must survive that disagreement — single-writer, consensus, or commutative designs.

## 14. AI/ML/LLM application examples where relevant

KV-cache leaks in long-lived inference servers — bound sessions, `--max-num-seqs`, restart per model deploy.

## 15. Security considerations

Long-lived objects retain references — scrub sensitive buffers; prefer immutable payloads.

## 16. Performance considerations

DB performance dominates: connection pools, indexes, and lock discipline decide p99 more than any app code change.

## 17. Common mistakes

"It restarts nightly, ship it"; unbounded module-level list/dict caches; catching and swallowing exceptions while holding references; long-lived ORM session as registry; no RSS metric — leaks discovered by customers.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `process_resident_memory_bytes` trend, GC count, top-growing allocator

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Long-running pytest/soak test: 5k iterations of a representative request, assert tracemalloc growth < 10MB; RSS plateau test; CI leak gate on micro-benchmarks; staging soak under production-like traffic; alert-verification drill.

## 21. Deployment considerations

Ship with expand/contract migrations; zero-downtime requires old code on new schema during the roll — never deploy breaking DDL in the same release as the code that depends on it.

## 22. Production-readiness checklist

- [ ] Bounded caches only
- [ ] Close everything (with/finally)
- [ ] Per-request scopes
- [ ] RSS alerting at 80% limit
- [ ] Leak reproduction test running N iterations asserting flat-ish RSS
- [ ] Py-spy/tracemalloc in staging profile
- [ ] Periodic dependency/native lib updates
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** OOM-kill under load spike (not steady state) — hard to reproduce in staging; GC-thrash P99 (memory near limit → GC work explodes); leak in a rarely-hit error path (only triggered on failures — nobody notices); connection pool sessions retained via long-lived registry → 500s from exhausted pools masquerading as DB issues; container restart hides leak → from metrics, "it self-heals" — until it doesn't.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://docs.python.org/3/library/tracemalloc.html

**Related topics in this library:** `#42 Garbage Collection`, `#28 Connection Pooling`, `#58 Monitoring`, `#40 Deadlocks` (different but often co-investigated), `#90 Serverless Limits` (memory ceiling).
