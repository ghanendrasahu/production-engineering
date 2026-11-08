---
topic: 76
title: CORS
category: D
skill: production-engineering
status: stable
---

# 076 — CORS

## 1. Topic name and metadata

- **Number:** 76 of 111
- **Title:** CORS
- **Category:** D — Security Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [security-engineering.md](../references/security.md)
- **Topic file:** `.agents/skills/production-engineering/topics/076-cors.md`

## 2. What it is

Cross-Origin Resource Sharing — the browser-enforced mechanism controlling which origins may read responses from a server; preflight (OPTIONS) checks for non-simple requests.

## 3. Why it exists

Browsers need explicit permission to let origins read responses.

## 4. The engineering problem it solves

Browsers block cross-origin reads (same-origin policy); developers thus misconfigure CORS "to make errors go away", often by reflecting any Origin with credentials — which reopens the exact hole SOP closes.

## 5. How it works internally

Preflight: browser sends `OPTIONS` with `Origin` + `Access-Control-Request-Method/Headers`; server responds with allowed origin/methods/headers and `Access-Control-Max-Age` (cache preflight). Simple requests skip preflight. With credentials (cookies), `Access-Control-Allow-Origin: *` is invalid — must echo the specific origin and `Allow-Credentials: true`. Response without proper header → browser blocks JS from reading it (server still processed the request — CORS is not an access control for non-browser clients). Vary: Origin must be set when echoing dynamic origins (cache correctness).

## 6. Architecture and design principles

Edge/proxy or app middleware; preflight caching at CDN.

**Design principles for this category:** Deny by default; least privilege; defense in depth — no single control carries the weight; shift security left into CI.

## 7. When to use it

Browser SPA + separate API origin — yes.

## 8. When NOT to use it

Same-origin deployment (no CORS needed at all — simplest); non-browser clients (curl/mobile unaffected — use auth, not CORS).

**Alternatives:** same-origin proxy (BFF pattern — avoids CORS entirely), cookie-based same-site subdomains, postMessage for iframes.

## 9. Implementation strategies

```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["https://app.example.com"],
                   allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"],
                   allow_credentials=True, max_age=600)
```

Explicit allowlist beats regex (`.*\.example\.com` accidentally matches `badexample.com.evil.com`).

## 10. Production-grade implementation

**Scenario:** SPA on `app.example.com` + API on `api.example.com`: middleware allowlist both, `allow_credentials=true` for cookie session, preflight cached `max_age=600`, `Vary: Origin` set — zero CORS errors, no wildcard anywhere.

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

Not applicable — this concept is infrastructure/protocol level; there is no FastAPI-specific surface. Apply it underneath FastAPI through configuration, middleware, or dependencies (section 9). Do not force a fake integration.

## 13. Distributed-system considerations

Security is global: identity, secrets, and policy must be consistent everywhere the workload runs — one unpatched region or sidecar undoes the rest.

## 14. AI/ML/LLM application examples where relevant

SSE from your API needs correct CORS for the web UI origin; don't reflect arbitrary origins.

## 15. Security considerations

Explicit allowlist; never reflect arbitrary origins; credentials only with named origins.

## 16. Performance considerations

TLS + auth cost ~1-10 ms per request — amortized by keepalive and token caching; never skip payment for security 'perf' reasons without measuring.

## 17. Common mistakes

Reflect any Origin; `*` with credentials; wildcards in regex; disabling browser checks; CORS as a security control; forgetting preflight cache → every POST costs two round trips.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `cors_rejections_total`, preflight cache hit rate

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

curl OPTIONS with Origin header → assert allowlist honored; verify 401/403 without preflight success; E2E browser test from the real SPA; assert `Vary: Origin` in responses; scan for `*` in config.

## 21. Deployment considerations

Treat every change to auth/secrets/TLS as security-sensitive: staged rollout, monitoring on rejection rates, and a documented rollback that also rotates anything exposed.

## 22. Production-readiness checklist

- [ ] Explicit origin allowlist
- [ ] Credentials only with specific origins
- [ ] `Vary: Origin`
- [ ] Cache preflights
- [ ] Minimal methods/headers
- [ ] Keep cookies SameSite=Lax/Strict
- [ ] Remember CORS doesn't protect server actions — CSRF/auth do
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** `allow_origins=["*"]` + `allow_credentials=true` → browsers reject, apps "work" via disabling checks; arbitrary-origin reflection → CSRF-ish data theft; missing `Vary: Origin` → CDN serves cached response with wrong origin header to another origin; preflight not cached → latency added per call; allowing `*` methods/headers "temporarily"; CORS configured but cookies still SameSite=None without Secure (modern browsers block).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS

**Related topics in this library:** `#77 CSRF`, `#69 OAuth`, `#76 CORS` pairs with `#4 Reverse Proxies`, `#79 XSS` (why credentials in headers matters).
