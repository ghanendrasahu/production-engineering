---
topic: 77
title: CSRF
category: D
skill: production-engineering
status: stable
---

# 077 — CSRF

## 1. Topic name and metadata

- **Number:** 77 of 111
- **Title:** CSRF
- **Category:** D — Security Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [security-engineering.md](../references/security.md)
- **Topic file:** `.agents/skills/production-engineering/topics/077-csrf.md`

## 2. What it is

Cross-Site Request Forgery — an attack in which a victim's browser, already authenticated via cookies, is tricked into submitting a forged state-changing request the attacker controls.

## 3. Why it exists

Cookie-ambient authority is forgeable without SameSite or a token.

## 4. The engineering problem it solves

Sessions-in-cookies are sent automatically; without CSRF defenses, a malicious page can transfer money/change email as the user (though not read responses).

## 5. How it works internally

Defenses: (1) **SameSite cookies** (`Lax` by default in modern browsers — blocks cross-site cookies on non-top-level POSTs; `Strict` blocks even on links; `None` requires Secure). (2) **Synchronizer token**: server issues a per-session random token embedded in forms/headers; server validates on mutation (double-submit cookie or server-side session token). (3) **Custom header check**: require a non-"simple" header (e.g., `X-CSRF-Token`) that triggers preflight — cross-origin forms can't set it. (4) Fetch metadata headers (`Sec-Fetch-Site: cross-site` → reject) increasingly supported.

## 6. Architecture and design principles

App middleware + cookie attributes; enforced only on cookie-authenticated mutating endpoints; API-token endpoints are immune (token not ambient).

**Design principles for this category:** Deny by default; least privilege; defense in depth — no single control carries the weight; shift security left into CI.

## 7. When to use it

Any cookie-authenticated mutation endpoint.

## 8. When NOT to use it

Stateless bearer-token APIs (no ambient authority) — still verify CSRF not applicable.

**Alternatives:** SameSite=Strict for high-security apps; BFF pattern; request-signing for non-browser clients.

## 9. Implementation strategies

```python
# FastAPI: DoubleSubmitCookie / SameSite=Lax + Origin check
@app.middleware("http")
async def csrf_guard(request, call_next):
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.cookies.get("session"):
        if request.headers.get("sec-fetch-site") == "cross-site": return JSONResponse(403, ...)
        if request.headers.get("x-csrf-token") != request.cookies.get("csrf"): return JSONResponse(403, ...)
```

## 10. Production-grade implementation

**Scenario:** Banking portal switched to `SameSite=Lax` cookies + `X-CSRF-Token` echo; a reported forged-transfer PoC now fails with 403; annual pentest clean.

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

Set session cookie `SameSite=Lax, HttpOnly, Secure`; CSRF token cookie + `X-CSRF-Token` header on mutations; SPA reads csrf cookie and echoes in header.

## 13. Distributed-system considerations

Security is global: identity, secrets, and policy must be consistent everywhere the workload runs — one unpatched region or sidecar undoes the rest.

## 14. AI/ML/LLM application examples where relevant

Cookie-authenticated AI chat needs CSRF tokens — SameSite=Lax + custom header.

## 15. Security considerations

SameSite=Lax; custom token header; Sec-Fetch-Site check — defense in depth.

## 16. Performance considerations

TLS + auth cost ~1-10 ms per request — amortized by keepalive and token caching; never skip payment for security 'perf' reasons without measuring.

## 17. Common mistakes

Cookie session without any CSRF protection; CSRF token static per user; token in form URL/logs; exempting "trusted" endpoints; CORS `*` with credentials (`#76`) re-opening it.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `csrf_rejections_total`, samesite-none usage count

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Forged cross-site POST with victim cookies → 403; missing header → 403; SameSite behavior in Playwright E2E from a different origin; Sec-Fetch-Site injection test; webhook signature test.

## 21. Deployment considerations

Treat every change to auth/secrets/TLS as security-sensitive: staged rollout, monitoring on rejection rates, and a documented rollback that also rotates anything exposed.

## 22. Production-readiness checklist

- [ ] SameSite=Lax default
- [ ] Cookies HttpOnly+Secure
- [ ] Double-submit token for SPAs
- [ ] Custom header + preflight
- [ ] Sec-Fetch-Site checks where available
- [ ] Never mutate on GET
- [ ] Don't rely on one layer (defense in depth)
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** SameSite=None + Secure but no token → CSRF open (some browsers still allow top-level POST nav); CSRF middleware exempts `/webhooks` but not checking signatures (unauthenticated but forged-ish — verify HMAC); token in URL (leaks via referer); GET endpoint mutating state (CSRF-anything, also a cache-poisoning hazard); relying on Referer checks alone; webhook cookies inherited from parent domain (`Domain=.example.com`) across apps.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html

**Related topics in this library:** `#76 CORS`, `#69 OAuth`, `#79 XSS` (XSS defeats CSRF defenses — token read by script), `#71 TLS`.
