---
topic: 4
title: Reverse Proxies
category: A
skill: production-engineering
status: stable
---

# 004 — Reverse Proxies

## 1. Topic name and metadata

- **Number:** 4 of 111
- **Title:** Reverse Proxies
- **Category:** A — Backend Architecture and API Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [backend-architecture.md](../references/architecture.md)
- **Topic file:** `.agents/skills/production-engineering/topics/004-reverse-proxies.md`

## 2. What it is

A server positioned in front of application origins that accepts client requests, performs cross-cutting duties (TLS termination, routing, caching, compression, security headers), and forwards to the origin.

## 3. Why it exists

Origins need one protected, TLS-terminating front door that routes and shields.

## 4. The engineering problem it solves

Applications shouldn't implement TLS termination, WAF rules, compression, and routing themselves; origins need protection from direct exposure and a stable public identity.

## 5. How it works internally

Terminates TLS (handshake, cert chain, SNI-based virtual hosting, HTTP/2 h2 or HTTP/3 QUIC), rewrites/headers (Host, X-Forwarded-For), routes by path/host/header to upstreams, optionally caches responses (shared cache key), enforces limits (client body size, rate limit), buffers (for slow clients, proxy buffering saves origin from holding connections).

## 6. Architecture and design principles

Client → CDN/edge → reverse proxy (Nginx/Traefik/Envoy/HAProxy) → upstream app → database. Often the same process is both LB and TLS terminator.

**Design principles for this category:** Statelessness by design; every control is enforced at a boundary (edge/gateway/service); config over code; bounded resources everywhere.

## 7. When to use it

Any production deployment (basically always), TLS termination, static file offload, caching, WAF.

## 8. When NOT to use it

Pure L4 internal service-to-service (mTLS mesh may be better).

**Alternatives:** cloud LB (ALB/NLB), Traefik (K8s-native), Envoy, CDN edge.

## 9. Implementation strategies

Nginx: `proxy_pass`, `proxy_set_header X-Forwarded-Proto $scheme`, `proxy_cache_path`, `gzip on`, `server_tokens off`, TLS via certbot (Let's Encrypt) or cloud cert manager; TLS 1.2/1.3 only; HSTS; OCSP stapling.

```nginx
server { listen 443 ssl http2; server_name app.example.com;
  ssl_certificate /etc/letsencrypt/live/app/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/app/privkey.pem;
  add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
  location / { proxy_pass http://upstream; proxy_set_header Host $host;
               proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; } }
```

## 10. Production-grade implementation

**Scenario:** Nginx terminates TLS, gzips, serves `/static` directly (expires 1 year), proxies `/api` to 4 FastAPI replicas with `proxy_cache` on `/api/products` (10s TTL, 94% hit), client max body 10MB. TLS handshake cost amortized by keepalive; p50 static asset latency falls from 40ms to 8ms.

**To reach production grade, combine the implementation in section 9 with these non-negotiables:**

- Wire the section 19 signals into dashboards and alerts *before* the rollout — an unmeasured control is decorative.
- Bake the control into the pipeline, not the runbook: IaC/CI enforces it on every deploy; humans should not be the enforcement layer (`#6 CI/CD`, `#104 Infrastructure as Code`).
- Load and failure-test it at 2x expected traffic, in staging with production-like data volume, before declaring it done (`#26 Query Optimization`, `#91 Latency`).
- Roll out behind a canary or flag with automatic rollback on SLO burn (`#53 Canary Releases`, `#51 Feature Flags`), and document the rollback path in the runbook.
- Verify the dependent data path explicitly: migrations, secrets, certificates, and IAM policies ship with the same change.

## 11. Code examples (Python)

N/A (infrastructure); verify app behavior behind a proxy by trusting `X-Forwarded-Proto/For` only from a known proxy — FastAPI/Starlette `TrustedHostMiddleware` + `forwarded_allow_ips` in uvicorn.

## 12. FastAPI integration where relevant

```python
# uvicorn --proxy-headers --forwarded-allow-ips '*' app:app
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="10.0.0.0/8")
```

## 13. Distributed-system considerations

Across instances this concept only works if the state it relies on (limits, locks, caches) is externalized — Redis, DB, or the edge — never in process memory alone.

## 14. AI/ML/LLM application examples where relevant

Terminate TLS at the edge; stream LLM SSE through with `proxy_buffering off` / `X-Accel-Buffering: no` — a buffering proxy destroys token-by-token UX.

## 15. Security considerations

Proxy hides versions/cookies; TLS terminates here — harden before the app trusts headers.

## 16. Performance considerations

The gateway/LB path adds ~1-3 ms; caches save 10-100x origin work; counters in Redis add one RTT — keep them on the hot path small.

## 17. Common mistakes

Passing TLS straight through without inspection (sometimes correct, but you lose routing); proxying trust headers blindly; proxy as single point of failure without HA; serving dynamic apps with caching on by default; misconfigured buffering breaking streaming.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `proxy_upstream_time_seconds`, 5xx rate, TLS handshake failures

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

`curl -I https://app` verify HSTS/headers; 413 test with oversized body; streaming test confirming tokens flush (SSE/LLM); cert expiry alert test; upstream kill test to confirm502/504 behavior and recovery.

## 21. Deployment considerations

Roll out behind a canary or flag; watch 5xx + p99; rollback = traffic selector flip (gateway), not a rebuild.

## 22. Production-readiness checklist

- [ ] Terminate TLS at proxy with cert automation (certbot/ACME) or cloud LB
- [ ] Hide versions (`server_tokens off`)
- [ ] Add security headers (CSP, HSTS, X-Content-Type-Options)
- [ ] HTTP/2 or HTTP/3
- [ ] `proxy_read_timeout` ≥ app's longest internal deadline
- [ ] `proxy_buffering off` for streaming
- [ ] Monitor cert expiry.
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Proxy buffers a streaming response and breaks SSE/LLM token streaming (must set `proxy_buffering off` / `X-Accel-Buffering: no`); `X-Forwarded-For` trusted from anywhere → IP spoofing for rate limits/audit; TLS cert expiry not monitored → total outage; `client_max_body_size` rejecting legitimate uploads (413); upstream timeout lower than app's internal timeout → 504 while app completes work.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://nginx.org/en/docs/http/ngx_http_proxy_module.html

**Related topics in this library:** `#3 Load Balancing`, `#48 CDN`, `#49 Edge Caching`, `#71 TLS`, `#74 WAF`, `#22 WebSockets` (proxy upgrade headers), `#24 Server-Sent Events`.
