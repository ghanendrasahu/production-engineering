---
topic: 49
title: Edge Caching
category: B
skill: production-engineering
status: stable
---

# 049 — Edge Caching

## 1. Topic name and metadata

- **Number:** 49 of 111
- **Title:** Edge Caching
- **Category:** B — Database Engineering and Distributed Systems
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [scaling-caching.md](../references/performance.md)
- **Topic file:** `.agents/skills/production-engineering/topics/049-edge-caching.md`

## 2. What it is

Edge caching stores repeatable responses at the network edge — CDN PoPs, Cloudflare, Fastly, or an API gateway edge tier — and serves them without contacting the origin. It is the mechanism of keys, TTLs, revalidation, and eviction that makes a CDN work for dynamic traffic.

## 3. Why it exists

Offload origin traffic to the network's edge, not your datacenter.

## 4. The engineering problem it solves

Origin round-trips for repeated GETs waste hundreds of milliseconds and saturate origin capacity, even though most reads never change.

## 5. How it works internally

The edge builds a key `hash(method + host + path + sorted query + Vary-selected headers)` and looks it up in a bounded LRU store. A HIT serves immediately with `Age`; a MISS fetches the origin and stores the body for the TTL from `Cache-Control`/`s-maxage` (`no-store`, `private`, `Vary: *` are uncacheable). Near expiry it revalidates with `If-None-Match` (store only on 200, 304 when unchanged); `stale-while-revalidate` serves stale bytes while refreshing. LRU evicts coldest keys under pressure; surrogate-key purges evict thousands at once.

## 6. Architecture and design principles

`client → edge cache → (miss/stale) origin → app → Redis/DB`. App-written `Cache-Control`/`ETag`/`Vary` headers are the contract the edge obeys.

**Design principles for this category:** Measure before mutating; the primary is the system of record; correctness invariants belong in constraints and transactions, not app code.

## 7. When to use it

Traffic skews toward repeat GETs, responses are public or safely keyable, and origin latency or capacity is the constraint.

## 8. When NOT to use it

Reads must reflect writes immediately, requests are mostly unique, or the response cannot be shared across users.

**Alternatives:** Redis cache-aside (`#2 Caching`), read replicas (`#29 Read Replicas`), or no cache with a faster origin.

## 9. Implementation strategies

Nginx edge cache:

```nginx
proxy_cache_path /var/cache/nginx/api keys_zone=api_edge:200m
                 max_size=10g inactive=120s;
server {
  listen 443 ssl;
  location /public/ {
    proxy_cache           api_edge;
    proxy_cache_key       "$scheme$request_method$host$request_uri$cookie_lang";
    proxy_cache_valid     200 30s;
    proxy_cache_use_stale error timeout updating http_503;
    proxy_cache_lock      on;    # one upstream fetch per hot key
    add_header X-Cache-Status $upstream_cache_status always;
    proxy_pass http://api_upstream;
  }
}
```

## 10. Production-grade implementation

**Scenario:** A catalog API doing 4k rps of GETs gets `s-maxage=60` with `stale-while-revalidate=30`. Offload reaches 94% (240 origin rps instead of 4k) and p95 drops 210ms → 60ms in-region, 95ms distant; one hot key (18% of traffic) uses a 15s TTL with `proxy_cache_lock`, holding origin at ~30 rps.

**To reach production grade, combine the implementation in section 9 with these non-negotiables:**

- Wire the section 19 signals into dashboards and alerts *before* the rollout — an unmeasured control is decorative.
- Bake the control into the pipeline, not the runbook: IaC/CI enforces it on every deploy; humans should not be the enforcement layer (`#6 CI/CD`, `#104 Infrastructure as Code`).
- Load and failure-test it at 2x expected traffic, in staging with production-like data volume, before declaring it done (`#26 Query Optimization`, `#91 Latency`).
- Roll out behind a canary or flag with automatic rollback on SLO burn (`#53 Canary Releases`, `#51 Feature Flags`), and document the rollback path in the runbook.
- Verify the dependent data path explicitly: migrations, secrets, certificates, and IAM policies ship with the same change.

## 11. Code examples (Python)

deterministic edge cache keys:

```python
import hashlib, urllib.parse

VARY = ("accept-encoding", "accept-language")

def cache_key(method: str, url: str, headers: dict) -> str:
    p = urllib.parse.urlsplit(url)
    q = urllib.parse.urlencode(sorted(urllib.parse.parse_qsl(p.query, keep_blank_values=True)))
    vary = "|".join(f"{h}={headers.get(h, '').lower()}" for h in VARY)
    return "edge:" + hashlib.sha256(f"{method.upper()}|{p.path}|{q}|{vary}".encode()).hexdigest()

h = {"accept-encoding": "gzip", "accept-language": "en-US"}
assert cache_key("GET", "https://a.dev/c?b=2&a=1", h) == cache_key("GET", "https://a.dev/c?a=1&b=2", h)
```

## 12. FastAPI integration where relevant

middleware making responses edge-revalidatable:

```python
import hashlib
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

app = FastAPI()

class EdgeCache(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method != "GET" or not request.url.path.startswith("/public/"):
            return await call_next(request)
        resp = await call_next(request)
        body = b"".join([c async for c in resp.body_iterator])
        tag = '"' + hashlib.sha256(body).hexdigest()[:32] + '"'
        headers = {"ETag": tag,
                   "Cache-Control": "public, s-maxage=60, stale-while-revalidate=30"}
        if request.headers.get("if-none-match") == tag:
            return Response(status_code=304, headers=headers)
        return Response(body, status_code=resp.status_code, headers=headers)

app.add_middleware(EdgeCache)
```

## 13. Distributed-system considerations

Distributed state is the hard part: replicas, shards, and lock holders disagree by milliseconds; correctness must survive that disagreement — single-writer, consensus, or commutative designs.

## 14. AI/ML/LLM application examples where relevant

Edge cache for RAG answer cache only with `private` and tenant keys; mostly edge caching is for the web UI.

## 15. Security considerations

`Cache-Control: private` for personalized responses — shared edge caches leak otherwise.

## 16. Performance considerations

DB performance dominates: connection pools, indexes, and lock discipline decide p99 more than any app code change.

## 17. Common mistakes

- Caching with no invalidation plan.
- Caching personalized responses under a shared key.
- Unbounded cache growth with no size cap.
- Long TTLs on error responses, extending outages.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `edge_cache_hit_ratio`, `stale_responses_served_total`

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Load cold then warm (MISS → HIT, ≥90% ratio, p95 drop); assert `If-None-Match` returns 304 for an unchanged body; audit stored keys for leaked user IDs; disable the cache and confirm the origin still holds SLO.

## 21. Deployment considerations

Ship with expand/contract migrations; zero-downtime requires old code on new schema during the roll — never deploy breaking DDL in the same release as the code that depends on it.

## 22. Production-readiness checklist

- [ ] - Normalize keys: strip tracking params, sort query strings, key only body-changing headers. - Set `s-maxage` explicitly
- [ ] Let the app own freshness. - Use `stale-while-revalidate` plus single-flight locks to smooth expiry spikes. - Emit `X-Cache-Status`/`Age` and chart hit ratio per route.
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Thundering herd at TTL expiry: 40k clients revalidate one key in the same second.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).
- **Symptom:** Stale after write: a price changes but the copy lives another 55s.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).
- **Symptom:** Key explosion: `utm_*` params in the key drop hit ratio to 20%.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).
- **Symptom:** `Vary: Cookie` on a public route makes every visitor miss.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://developers.cloudflare.com/workers/
- https://developer.chrome.com/docs/devtools

**Related topics in this library:** `#2 Caching`, `#48 CDN`, `#50 Cache Invalidation`, `#93 P99 Latency`, `#99 HTTP/2 & HTTP/3`, `#38 Distributed Locks`
