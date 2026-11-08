---
topic: 2
title: Caching
category: A
skill: production-engineering
status: stable
---

# 002 — Caching

## 1. Topic name and metadata

- **Number:** 2 of 111
- **Title:** Caching
- **Category:** A — Backend Architecture and API Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [backend-architecture.md](../references/architecture.md)
- **Topic file:** `.agents/skills/production-engineering/topics/002-caching.md`

## 2. What it is

Storing the result of expensive work close to consumers so repeat requests are served cheaply and quickly, with a defined freshness and eviction policy.

## 3. Why it exists

Reading from origin every time is too slow and too expensive at scale.

## 4. The engineering problem it solves

Every read hitting the database or an LLM re-pays full cost and latency; hot data causes lock and CPU contention; origin outages become user-facing outages if there is no cached fallback.

## 5. How it works internally

Cache-aside (check cache → miss → fetch origin → set with TTL), read-through (cache fetches on miss), write-through (write cache and origin synchronously), write-back (write cache now, origin async — fastest, least durable). Eviction: LRU/LFU, TTL expiry, explicit invalidation. `stale-while-revalidate` serves the stale value while refreshing asynchronously; single-flight locks prevent cache stampedes (thundering herd) when a hot key expires.

## 6. Architecture and design principles

Browser cache → CDN → reverse proxy cache (Nginx `proxy_cache`) → application cache (in-process, e.g. lru_cache) → shared Redis/Memcached → database buffer pool → read replicas. Placement higher up serves more traffic with less origin cost.

**Design principles for this category:** Statelessness by design; every control is enforced at a boundary (edge/gateway/service); config over code; bounded resources everywhere.

## 7. When to use it

Read-heavy workload on stable data, expensive computation (LLM calls, reports, joins), per-key hotness known.

## 8. When NOT to use it

Data must be strongly consistent (balances, inventory counts) without invalidation; write frequency exceeds read frequency; dataset is tiny.

**Alternatives:** read replicas (`#29 Read Replicas`), denormalization, view materialization.

## 9. Implementation strategies

Redis for shared app cache; key design `service:entity:id:v3` with version in key for cheap "invalidation"; TTL jitter (base ± random) to avoid synchronized expiry; single-flight via `SET NX PX` or `cachelock`; negative caching for 404s with short TTL.

```python
import json, time, hashlib, redis
r = redis.Redis(decode_responses=True)

def get_user(uid: int):
    key = f"user:{uid}:v2"
    hit = r.get(key)
    if hit:
        return json.loads(hit)
    lock = r.set(f"lock:{key}", "1", nx=True, px=2000)
    row = db_fetch(uid)               # origin
    if row is None:
        r.setex(key, 30, "null")      # negative cache
        return None
    r.setex(key, 300 + int(time.time() * 1000) % 60, json.dumps(row))
    if lock:
        r.delete(f"lock:{key}")
    return row
```

## 10. Production-grade implementation

**Scenario:** Product catalog: 40k QPS reads, 50 QPS writes. Redis cache-aside, TTL 5 min + jitter, 97% hit ratio; origin Postgres load drops from 40k to ~1.2k QPS. LLM response cache on SHA-256 of normalized prompt + model + temperature saved 34% of token spend on a support bot.

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

Response-level caching middleware that hashes the path+query and sets `Cache-Control: public, max-age=60, stale-while-revalidate=300`, returning `304 Not Modified` on `If-None-Match` with a stored ETag.

## 13. Distributed-system considerations

Across instances this concept only works if the state it relies on (limits, locks, caches) is externalized — Redis, DB, or the edge — never in process memory alone.

## 14. AI/ML/LLM application examples where relevant

Exact-match caching on hash(model, normalized prompt, params) and semantic caching (embedding similarity ~0.95) cuts 20-40% of calls on repetitive workloads. Tenant-scope all keys.

## 15. Security considerations

Tenant-scope cache keys; never cache secrets or PII; short TTLs.

## 16. Performance considerations

The gateway/LB path adds ~1-3 ms; caches save 10-100x origin work; counters in Redis add one RTT — keep them on the hot path small.

## 17. Common mistakes

Caching without an invalidation strategy; caching everything "just in case"; infinite TTLs with no eviction policy; caching error responses; using the cache as the source of truth; cache-aside on write-heavy paths where the miss cost exceeds the value.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `cache_hit_ratio`, `cache_misses_total`, `cache_evictions_total`

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

pytest with fakeredis: miss path calls origin once, second call is a hit; TTL jitter verified; invalidation after write test; stampede test with one key expiring under 20 concurrent asyncio requests and assert origin called once.

## 21. Deployment considerations

Roll out behind a canary or flag; watch 5xx + p99; rollback = traffic selector flip (gateway), not a rebuild.

## 22. Production-readiness checklist

- [ ] Cache-aside + explicit TTL as the default
- [ ] Version keys for deploy-time invalidation
- [ ] Tag-based invalidation for lists/aggregates
- [ ] Jitter TTLs
- [ ] Monitor hit ratio and eviction count
- [ ] Set `maxmemory` and `maxmemory-policy allkeys-lru`
- [ ] Cache negative results briefly
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Hot key expires and 5k concurrent requests hit the origin (stampede) — mitigate with single-flight lock or early revalidation; stale data served after a write — mitigate with write-through or tag-based invalidation; cache poisoning by unvalidated input keys; unbounded memory growth (no maxmemory policy) evicting useful keys LRU-wise; per-user data under a shared key leaking across users.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://learn.microsoft.com/azure/architecture/patterns/cache-aside
- https://redis.io/docs/latest/develop/using-tickets/

**Related topics in this library:** `#2 Caching` pairs with `#50 Cache Invalidation`, `#49 Edge Caching`, `#48 CDN`, `#38 Distributed Locks` (single-flight), `#28 Connection Pooling`, `#44 Backpressure`.
