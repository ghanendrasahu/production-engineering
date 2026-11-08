---
topic: 50
title: Cache Invalidation
category: B
skill: production-engineering
status: stable
---

# 050 — Cache Invalidation

## 1. Topic name and metadata

- **Number:** 50 of 111
- **Title:** Cache Invalidation
- **Category:** B — Database Engineering and Distributed Systems
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [scaling-caching.md](../references/performance.md)
- **Topic file:** `.agents/skills/production-engineering/topics/050-cache-invalidation.md`

## 2. What it is

Cache invalidation removes or supersedes cached entries when underlying data changes so readers never observe stale values.

## 3. Why it exists

Caches are only as good as their invalidation discipline.

## 4. The engineering problem it solves

Stale data is a business incident: a revoked permission honored, a price shown after it changed. Manual purges are not a plan.

## 5. How it works internally

Four mechanisms dominate. Time-based: TTL bounds staleness but guarantees none below it. Delete-on-write races an in-flight read that repopulates old data — delete before commit or version the key. Versioned keys: bump a counter so old keys become garbage — memory for race-free reads. Tag purge: keys sit in tag sets (`SADD tag:product:42 key`) walked on invalidation. `SET NX PX` locks stop stampedes; pub/sub (`#16 Pub/Sub`) fans evictions out.

## 6. Architecture and design principles

Writer → cache-aside get/set on Redis → invalidation event (pub/sub or version bump) → local and edge caches (`#49 Edge Caching`) purged by tag.

**Design principles for this category:** Measure before mutating; the primary is the system of record; correctness invariants belong in constraints and transactions, not app code.

## 7. When to use it

Any cached value can change while in flight and readers must not see pre-write data.

## 8. When NOT to use it

Data is immutable or content-addressed, or invalidation traffic would approach read traffic.

**Alternatives:** versioned keys, write-through caching, shorter TTLs, or read replicas (`#29 Read Replicas`).

## 9. Implementation strategies

Redis layout: `SETEX` values, tag sets (`SADD`/`SMEMBERS` + `DEL`), lock via `SET key:lock token NX PX 5000` with compare-and-delete Lua; at the edge, Cloudflare purge-by-tag or `Surrogate-Key`.

## 10. Production-grade implementation

**Scenario:** A shop caches 1.2M product keys at 60s TTL. TTL-only invalidation left a $49 item at $39 for 47 minutes; tag invalidation cut the stale window to <2s at 91% offload. Stampede locking capped a hot-key expiry at ~300 fetches instead of 40k, holding p95 at 70ms.

**To reach production grade, combine the implementation in section 9 with these non-negotiables:**

- Wire the section 19 signals into dashboards and alerts *before* the rollout — an unmeasured control is decorative.
- Bake the control into the pipeline, not the runbook: IaC/CI enforces it on every deploy; humans should not be the enforcement layer (`#6 CI/CD`, `#104 Infrastructure as Code`).
- Load and failure-test it at 2x expected traffic, in staging with production-like data volume, before declaring it done (`#26 Query Optimization`, `#91 Latency`).
- Roll out behind a canary or flag with automatic rollback on SLO burn (`#53 Canary Releases`, `#51 Feature Flags`), and document the rollback path in the runbook.
- Verify the dependent data path explicitly: migrations, secrets, certificates, and IAM policies ship with the same change.

## 11. Code examples (Python)

cache-aside with stampede lock and tag invalidation:

```python
import json, os, time
import redis

r = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
RELEASE = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) end"

def cache_get(key, loader, tags=(), ttl=60):
    if (raw := r.get(key)) is not None:
        return json.loads(raw)
    token = os.urandom(8).hex()
    if r.set(f"{key}:lock", token, nx=True, px=5000):      # single-flight
        try:
            value = loader()
            pipe = r.pipeline().setex(key, ttl, json.dumps(value))
            for tag in tags:
                pipe.sadd(f"tag:{tag}", key).expire(f"tag:{tag}", ttl * 4)
            pipe.execute()
            return value
        finally:
            r.eval(RELEASE, 1, f"{key}:lock", token)
    for _ in range(50):                                    # wait for the winner
        time.sleep(0.01)
        if (raw := r.get(key)) is not None:
            return json.loads(raw)
    return loader()                                        # duplicate fetch beats a 5xx

def invalidate_tags(*tags) -> int:
    removed = 0
    for tag in tags:
        if members := r.smembers(f"tag:{tag}"):
            removed += len(members)
            r.delete(*members, f"tag:{tag}")
    return removed

print(cache_get("product:42", lambda: {"id": 42, "price": 19.99}, tags=("product:42",)))
invalidate_tags("product:42")   # post-write
```

## 12. FastAPI integration where relevant

service-layer cache-aside with invalidation on write:

```python
import json, os, redis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()
store = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)

class ProductIn(BaseModel):
    name: str
    price: float

@app.get("/products/{pid}")
def read_product(pid: str) -> dict:
    if not (raw := store.get(f"product:{pid}")):
        raise HTTPException(status_code=404, detail="not found")
    return json.loads(raw)

@app.put("/products/{pid}")
def write_product(pid: str, body: ProductIn) -> dict:
    data = {"id": pid, **body.model_dump()}        # commit to DB first
    if keys := store.smembers(f"tag:product:{pid}"):
        store.delete(*keys, f"tag:product:{pid}")
    store.setex(f"product:{pid}", 60, json.dumps(data))
    return data
```

## 13. Distributed-system considerations

Distributed state is the hard part: replicas, shards, and lock holders disagree by milliseconds; correctness must survive that disagreement — single-writer, consensus, or commutative designs.

## 14. AI/ML/LLM application examples where relevant

Model/prompt change → invalidate cached answers by version tag; TTL backstop; purge on corpus delete (embedding tombstones).

## 15. Security considerations

Purge/invalidation APIs are admin — gate them, audit every call.

## 16. Performance considerations

DB performance dominates: connection pools, indexes, and lock discipline decide p99 more than any app code change.

## 17. Common mistakes

- Caching with no invalidation plan: lowering the TTL is not a plan.
- Caching per-user data under a shared key.
- Unbounded cache growth: no `maxmemory` or eviction policy.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `invalidations_total`, `stale_served_seconds`, purge failures

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Load test cold vs. warm comparing origin rps and p95; write-then-read until the new value appears; `SCAN` for keys missing TTLs; kill Redis and confirm the service holds SLO.

## 21. Deployment considerations

Ship with expand/contract migrations; zero-downtime requires old code on new schema during the roll — never deploy breaking DDL in the same release as the code that depends on it.

## 22. Production-readiness checklist

- [ ] - Decide freshness per route: TTL for tolerant reads, invalidation for read-after-write. - Invalidate after the commit, or version keys for the refill race. - Invalidate by tag, never wildcard flush
- [ ] Cap tag sizes. - Protect hot keys with single-flight locks
- [ ] Publish invalidations to replicas.
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Thundering herd at TTL expiry: a latency sawtooth every TTL seconds.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).
- **Symptom:** Stale after write: a fire-and-forget delete is lost and old values persist for minutes.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).
- **Symptom:** Divergent copies: an instance misses the pub/sub eviction and keeps serving stale data.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://developer.mozilla.org/en-US/docs/Web/HTTP/Caching

**Related topics in this library:** `#2 Caching`, `#49 Edge Caching`, `#38 Distributed Locks`, `#39 Race Conditions`, `#36 Optimistic Locking`, `#16 Pub/Sub`
