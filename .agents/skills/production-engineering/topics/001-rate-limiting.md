---
topic: 1
title: Rate Limiting
category: A
skill: production-engineering
status: stable
---

# 001 — Rate Limiting

## 1. Topic name and metadata

- **Number:** 1 of 111
- **Title:** Rate Limiting
- **Category:** A — Backend Architecture and API Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [backend-architecture.md](../references/architecture.md)
- **Topic file:** `.agents/skills/production-engineering/topics/001-rate-limiting.md`

## 2. What it is

A control that bounds how many requests a client or operation may make per time window, rejecting or delaying excess traffic.

## 3. Why it exists

One misbehaving client must not degrade the service for everyone else.

## 4. The engineering problem it solves

One buggy client, noisy tenant, or bot can exhaust database connections and CPU, degrading the service for everyone and inflating cost. LLM endpoints make this worse: each abandoned request may still bill tokens.

## 5. How it works internally

Token bucket (refill at a steady rate, burst up to bucket size) and sliding-window log/counter (count requests in the trailing window) are the two dominant designs. Leaky bucket smooths output to a constant rate. Implementations store counters in Redis with atomic `INCR`+`EXPIRE` or a Lua script that performs check-and-decrement atomically; local-memory buckets work per-instance but under-count globally and drift on scale-out.

## 6. Architecture and design principles

Enforced at three layers — edge (CDN/WAF), gateway (per-tenant quotas, API keys), and service middleware (per-user/per-route limits). Position matters: edge rejects cheaply before consuming origin capacity.

**Design principles for this category:** Statelessness by design; every control is enforced at a boundary (edge/gateway/service); config over code; bounded resources everywhere.

## 7. When to use it

Public API, expensive endpoints, multi-tenant SaaS, LLM/token cost control, abuse response.

## 8. When NOT to use it

Internal single-process jobs with bounded concurrency (use backpressure instead); as the only protection against a DDoS (use edge/CDN).

**Alternatives:** queue-based smoothing, autoscaling headroom, `#44 Backpressure` inside the service.

## 9. Implementation strategies

Redis Lua token bucket; response headers `X-RateLimit-Limit/Remaining/Reset` and `Retry-After: 37`; return HTTP 429 with a problem+json body. For FastAPI, slowapi (limits) or a custom dependency works; for Nginx, `limit_req_zone`.

```
redis-cli SCRIPT LOAD ... ; EVALSHA <sha> 1 ratelimit:user:42 100 1
```

```python
import time, redis
r = redis.Redis(decode_responses=True)
LUA = """local t=redis.call('HMGET',KEYS[1],'ts','tokens'); local now=tonumber(ARGV[3]); local win=tonumber(ARGV[1]); local rate=tonumber(ARGV[2]); local ts=tonumber(t[1]) or now; local tok=tonumber(t[2]) or rate; local refill=(now-ts)*rate/win; tok=math.min(rate,tok+refill); if tok>=1 then tok=tok-1; redis.call('HMSET',KEYS[1],'ts',now,'tokens',tok); redis.call('EXPIRE',KEYS[1],win*2); return {1,math.floor(tok)} else return {0,math.floor((1-tok)*win/rate)} end"""
allowed, info = r.eval(LUA, 1, "rl:u:42", 60, 60, int(time.time()))
```

## 10. Production-grade implementation

**Scenario:** 30k QPS API with a public search endpoint: edge WAF caps 500 req/s per IP, gateway caps 10k/day per API key tier, Redis-backed per-user limit 60 req/min on `/v1/generate`. Zombies retrying do not pass the gateway because 429s are not retried blindly by well-behaved clients.

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

```python
from fastapi import FastAPI, Depends, HTTPException, Request

async def rate_limit(request: Request):
    ok, retry_after = check_bucket(request.client.host)
    if not ok:
        raise HTTPException(429, detail="rate limit exceeded", headers={"Retry-After": str(retry_after)})

@app.get("/api/search", dependencies=[Depends(rate_limit)])
async def search(q: str): ...
```

## 13. Distributed-system considerations

Across instances this concept only works if the state it relies on (limits, locks, caches) is externalized — Redis, DB, or the edge — never in process memory alone.

## 14. AI/ML/LLM application examples where relevant

LLM endpoints are token-priced per call — rate-limit per tenant AND by tokens (prompt+max_tokens), not one request per unit. Shed with 429 + Retry-After before the GPU queues.

## 15. Security considerations

Key counters by tenant/user, not IP alone — avoid leaking behavioral fingerprints.

## 16. Performance considerations

The gateway/LB path adds ~1-3 ms; caches save 10-100x origin work; counters in Redis add one RTT — keep them on the hot path small.

## 17. Common mistakes

Fixed-window counters (boundary bursts at window edges); in-process counters in a multi-replica deployment; rate-limiting after the expensive work ran; a single global limit for everything; no 429 body; silently queueing instead of rejecting.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `rate_limit_rejections_total{route,tenant}`; 429 ratio; Redis ops latency

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

pytest with fakeredis asserting the Nth+1 request is rejected; concurrent test with 50 threads hammering one key; verify `Retry-After` header value; load test to confirm gateway sheds rather than origin falling over.

## 21. Deployment considerations

Roll out behind a canary or flag; watch 5xx + p99; rollback = traffic selector flip (gateway), not a rebuild.

## 22. Production-readiness checklist

- [ ] Return `Retry-After` and clear 429s
- [ ] Separate limits per route class (read vs write)
- [ ] Rate-limit at the earliest layer
- [ ] Use Redis Lua for atomicity
- [ ] Make limits configurable via env
- [ ] Expose limit state in headers
- [ ] Exempt health checks
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Counter drift under clock skew across Redis multi-instance → users bypass limits; shared global key without TTL leaks memory; limiting only per-IP → NAT'd corporate networks blocked; limiting writes but not reads → database still dies on read storms; returning 200 with empty body instead of 429 confuses clients.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://learn.microsoft.com/azure/architecture/patterns/throttling
- https://nginx.org/en/docs/http/ngx_http_limit_req_module.html

**Related topics in this library:** `#3 Load Balancing`, `#4 Reverse Proxies`, `#5 API Gateways`, `#11 Timeouts`, `#44 Backpressure`, `#75 DDoS Protection`, `#90 Serverless Limits` (LLM quotas).
