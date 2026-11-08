---
topic: 5
title: API Gateways
category: A
skill: production-engineering
status: stable
---

# 005 — API Gateways

## 1. Topic name and metadata

- **Number:** 5 of 111
- **Title:** API Gateways
- **Category:** A — Backend Architecture and API Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [backend-architecture.md](../references/architecture.md)
- **Topic file:** `.agents/skills/production-engineering/topics/005-api-gateways.md`

## 2. What it is

A single managed entry point for client APIs that centralizes cross-cutting concerns — routing, authentication, authorization, rate limiting, quotas, transformation, and observability — and routes requests to backend services.

## 3. Why it exists

A single enforcement point for auth, quotas, and routing beats N hand-rolled copies.

## 4. The engineering problem it solves

Without a gateway, every service re-implements auth, rate limits, and logging; clients must know every service address; security policy drifts per-service; internal topology leaks to clients.

## 5. How it works internally

Accepts all external traffic on one hostname, resolves route rules (path/method/host) to an upstream, applies a filter/middleware chain (TLS termination → WAF → authN (JWT/API key/mTLS) → authZ (scopes/RBAC) → rate limit/quota → request transformation (header injection, path rewrite) → forward), applies response policies (CORS, caching, header stripping), and emits metrics/traces keyed by route. Modern gateways (Kong, Envoy, Tyk, AWS API Gateway, cloud LB) run as plugins over a shared dataplane.

## 6. Architecture and design principles

Client → DNS → CDN → gateway → services (or monolith) → databases/queues. Internal service-to-service calls usually bypass the gateway.

**Design principles for this category:** Statelessness by design; every control is enforced at a boundary (edge/gateway/service); config over code; bounded resources everywhere.

## 7. When to use it

Multiple backends or clients, multi-tenant quotas, public API program, serverless.

## 8. When NOT to use it

A single modular monolith with 2 routes and one consumer — Nginx is enough; internal East-West traffic better served by a mesh.

**Alternatives:** service mesh (Envoy/Istio), cloud LB + app middleware, Nginx with Lua.

## 9. Implementation strategies

Kong on Kubernetes (Ingress or Gateway API) with plugins: `rate-limiting`, `jwt`, `key-auth`, `cors`, `prometheus`, `request-transformer`. OpenAPI contract per route; CI validates spec and pushes config. AWS API Gateway for serverless: stage variables, usage plans, API keys, Lambda integrations, custom domain.

```yaml
# Kong declarative config (kong.yml) excerpt
services:
- name: users-api
  url: http://users-svc:8000
  routes: [{ name: users, paths: ["/v1/users"], methods: [GET, POST] }]
  plugins:
  - name: rate-limiting
    config: { minute: 100, policy: redis, redis_host: redis }
  - name: jwt
```

## 10. Production-grade implementation

**Scenario:** 12 backend services behind Kong: one `kong.yml` in Git, CI lints it, per-route quotas (free tier 100/day, pro 100k), JWT verification at gateway so backends receive only `X-User-Id`/`X-Scopes`, CORS centralized, `/healthz` bypassed. Partner onboarding = add an API key + usage plan, zero code changes.

**To reach production grade, combine the implementation in section 9 with these non-negotiables:**

- Wire the section 19 signals into dashboards and alerts *before* the rollout — an unmeasured control is decorative.
- Bake the control into the pipeline, not the runbook: IaC/CI enforces it on every deploy; humans should not be the enforcement layer (`#6 CI/CD`, `#104 Infrastructure as Code`).
- Load and failure-test it at 2x expected traffic, in staging with production-like data volume, before declaring it done (`#26 Query Optimization`, `#91 Latency`).
- Roll out behind a canary or flag with automatic rollback on SLO burn (`#53 Canary Releases`, `#51 Feature Flags`), and document the rollback path in the runbook.
- Verify the dependent data path explicitly: migrations, secrets, certificates, and IAM policies ship with the same change.

## 11. Code examples (Python)

Client-side route helper fetching config; more usefully, verifying the gateway injected identity: `request.headers["X-User-Id"]` signed by the gateway between gateway and services.

## 12. FastAPI integration where relevant

```python
from fastapi import FastAPI, Header, HTTPException
import hmac, hashlib
async def verified_user(x_user_id: str = Header(...), x_signature: str = Header(...)):
    # trust only traffic from the gateway (signed, shared secret or mTLS)
    expected = hmac.new(SECRET, x_user_id.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, x_signature):
        raise HTTPException(401, "untrusted caller")
    return int(x_user_id)
```

## 13. Distributed-system considerations

Across instances this concept only works if the state it relies on (limits, locks, caches) is externalized — Redis, DB, or the edge — never in process memory alone.

## 14. AI/ML/LLM application examples where relevant

Unified API gateway centralizes per-tenant quotas, JWT/API-key auth, and token accounting for all model routes; never trust model-chosen tenant IDs — enforce server-side.

## 15. Security considerations

Gateway auth is necessary, not sufficient — re-enforce authorization at the service.

## 16. Performance considerations

The gateway/LB path adds ~1-3 ms; caches save 10-100x origin work; counters in Redis add one RTT — keep them on the hot path small.

## 17. Common mistakes

Business logic in the gateway (transformations only); no fallback auth in services (gateway-only security); single global quota; gateway config hot-patched in production without PR; exposing internal service URLs to mobile apps.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `gateway_request_total{route,status}`, quota rejections per tenant

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Contract-test routes in CI; integration tests against a gateway test instance; chaos test: take one upstream down → expect 502 only on its route; load test validating quota counters; verify header stripping at the edge.

## 21. Deployment considerations

Roll out behind a canary or flag; watch 5xx + p99; rollback = traffic selector flip (gateway), not a rebuild.

## 22. Production-readiness checklist

- [ ] Centralize authN at gateway, keep authZ close to data too
- [ ] Validate and strip inbound headers
- [ ] Idempotency key pass-through
- [ ] Circuit breaker per upstream
- [ ] Budget and benchmark gateway CPU
- [ ] Dashboard per route (RPS, p95, 5xx)
- [ ] Gateway config in Git with review
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Gateway becomes a SPOF or bottleneck (payloads, no keepalive, insufficient replicas); gateway outage blocks everything (region failover needed); secret leak in gateway config; authZ rules in gateway disagree with service-level checks (defense-in-depth still required); gateway retries upstreams causing double charges; request transformation bug silently drops headers (e.g. idempotency key).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://gateway-api.sigs.k8s.io/
- https://docs.aws.amazon.com/apigateway/

**Related topics in this library:** `#1 Rate Limiting`, `#3 Load Balancing`, `#4 Reverse Proxies`, `#67 Secrets Management`, `#69 OAuth`, `#102 API Versioning`, `#76 CORS`.
