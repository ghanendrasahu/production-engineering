---
topic: 42
title: Garbage Collection
category: B
skill: production-engineering
status: stable
---

# 042 — Garbage Collection

## 1. Topic name and metadata

- **Number:** 42 of 111
- **Title:** Garbage Collection
- **Category:** B — Database Engineering and Distributed Systems
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [distributed-systems.md](../references/distributed-systems.md)
- **Topic file:** `.agents/skills/production-engineering/topics/042-garbage-collection.md`

## 2. What it is

Automatic reclamation of unreachable memory; in CPython, reference counting plus a generational cycle detector; in JVM/Go/JavaScript-style engines, tracing collectors (G1, ZGC, concurrent mark-sweep) with pause characteristics.

## 3. Why it exists

GC pauses are a P99 disease wearing other diseases' clothes.

## 4. The engineering problem it solves

GC pauses manifest as P99/P999 spikes that look like "slow DB" or "noisy neighbor"; misconfigured collectors cause stop-the-world freezes or excessive CPU overhead.

## 5. How it works internally

CPython: every object has a refcount; reaching zero frees immediately (deterministic) — no long pauses; cycles broken by generational GC (3 generations, thresholds 700/10/10 allocations — tunable via `gc.set_threshold`); `gc.disable()` can help short-lived fork-heavy workers but hides cycles. JVM: allocation in young gen, survivors promoted; G1/ZGC aim for < 200ms pauses; humongous objects and old-gen pressure cause full GCs. Go: concurrent mark-sweep, sub-millisecond pauses typical, assist overhead under high allocation rate. Practical rule: know your runtime's pause profile and measure allocation rate, not just heap size.

## 6. Architecture and design principles

Runtime feature; visible to ops via GC metrics, allocation rates, heap utilization, pause histograms.

**Design principles for this category:** Measure before mutating; the primary is the system of record; correctness invariants belong in constraints and transactions, not app code.

## 7. When to use it

You operate any runtime — GC tuning is always relevant for latency-sensitive services.

## 8. When NOT to use it

Short scripts.

**Alternatives:** allocation-free hot paths, manual memory arenas (Rust/C++), region-based allocators off-heap.

## 9. Implementation strategies

Python: measure `gc.get_stats()` and counts; freeze long-lived objects (`gc.freeze()` on startup) to cut cycle GC work; avoid creating reference cycles in hot paths (return new objects, don't tangle graphs); prefer streaming generators over giant lists. JVM: ZGC (`-XX:+UseZGC`) or G1 tuning (`-XX:MaxGCPauseMillis=100`); Go: `GOGC=100` default, tune up with heap headroom.

## 10. Production-grade implementation

**Scenario:** Inference API p99 = 900ms; profiling showed allocation rate 800MB/s and G1 full GC every 4 minutes (200-400ms pauses); fixed by streaming embeddings + object reuse → full GCs gone, p99 = 60ms.

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

Avoid per-request allocations of large structures; reuse serializers/clients; streaming responses yield chunks instead of building whole bodies; `gc.freeze()` after loading models/warmup in the lifespan handler so startup objects are never scanned.

## 13. Distributed-system considerations

Distributed state is the hard part: replicas, shards, and lock holders disagree by milliseconds; correctness must survive that disagreement — single-writer, consensus, or commutative designs.

## 14. AI/ML/LLM application examples where relevant

vLLM allocates aggressively — CUDA caching allocator + GC stats in p99 during GC-heavy batch windows.

## 15. Security considerations

GC timing can leak secrets to co-tenants in shared runtimes — ML envs: dedicate nodes.

## 16. Performance considerations

DB performance dominates: connection pools, indexes, and lock discipline decide p99 more than any app code change.

## 17. Common mistakes

"Just add more memory"; ignoring GC logs during incident RCA; `gc.disable()` without leak audit; giant in-memory structures as "cache"; allocating per request in hot async paths; misreading GC time as database latency.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `gc_pause_seconds` p99, allocation rate, heap used after GC

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Load test measuring p99 + GC logs; allocation-rate benchmark; memory growth curve over 1h soak; container-limit test (GC behavior near ceiling); assert absence of full GCs in staging profile.

## 21. Deployment considerations

Ship with expand/contract migrations; zero-downtime requires old code on new schema during the roll — never deploy breaking DDL in the same release as the code that depends on it.

## 22. Production-readiness checklist

- [ ] Emit GC/pause metrics
- [ ] Know your runtime defaults
- [ ] Reduce per-request allocations
- [ ] Stream, don't materialize
- [ ] Freeze startup state
- [ ] Test P99 under sustained load, not just throughput
- [ ] Coordinate GC with deploys (warm before LB routes)
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Latency spikes every N minutes correlating to GC log; cgroup memory limit — GC sees less memory than heap needs → constant collection; C-extension allocated buffers invisible to GC but counted in RSS → OOM; disabling GC in CPython with cycles → true memory infinite growth; promotion of short-lived objects into old gen (premature tenure) thrashing.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://docs.python.org/3/library/gc.html
- https://docs.oracle.com/en/java/

**Related topics in this library:** `#41 Memory Leaks`, `#93 P99 Latency`, `#94 Tail Latency`, `#90 Serverless Limits`, `#58 Monitoring`.
