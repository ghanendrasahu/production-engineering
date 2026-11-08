---
topic: 70
title: JWT Rotation
category: D
skill: production-engineering
status: stable
---

# 070 — JWT Rotation

## 1. Topic name and metadata

- **Number:** 70 of 111
- **Title:** JWT Rotation
- **Category:** D — Security Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [security-engineering.md](../references/security.md)
- **Topic file:** `.agents/skills/production-engineering/topics/070-jwt-rotation.md`

## 2. What it is

The practice of issuing short-lived access tokens paired with long-lived but revocable refresh tokens, where refresh tokens rotate on each use so token theft has a bounded window and reuse is detectable.

## 3. Why it exists

A stolen token must expire soon, and its reuse must be detectable.

## 4. The engineering problem it solves

A leaked access token is a bearer credential valid until expiry; without rotation and reuse detection, an attacker maintains access indefinitely and you cannot tell the tokens apart.

## 5. How it works internally

Access token (JWT, 5-15min, stateless — verified via JWKS locally, no DB lookup). Refresh token (opaque or JWT, 7-30d, stored in DB/Redis). On refresh: verify → atomically revoke old + issue new refresh token in the same key family; if an already-used refresh token appears again, revoke the **entire family** (theft signal) → forced re-login. Revocation list checked on access-token validation only if truly stateless revocation is needed (use short expiry instead). Logout = family revoke.

## 6. Architecture and design principles

IdP or app-issued tokens; Redis family store; refresh endpoint with single-transaction rotation; device/session listing for users.

**Design principles for this category:** Deny by default; least privilege; defense in depth — no single control carries the weight; shift security left into CI.

## 7. When to use it

Stateless auth at scale with revocation needs — basically always.

## 8. When NOT to use it

Simple server-rendered app with session cookies (server-side sessions simpler).

**Alternatives:** opaque tokens + introspection (revocable instantly, more DB load), server-side sessions with idle timeout, mTLS for machines.

## 9. Implementation strategies

```python
def refresh(refresh_token: str):
    fam = r.get(f"rt:{hash(refresh_token)}")
    if fam is None:
        r.delete(f"family:{family_of(refresh_token)}")  # reuse detected → nuke family
        raise HTTPException(401, "refresh token reuse detected")
    new_refresh = issue(); r.set(f"rt:{hash(new_refresh)}", fam, ex=30*86400); r.delete(f"rt:{hash(refresh_token)}")
    return access_token(sub=fam.user), new_refresh
```

## 10. Production-grade implementation

**Scenario:** Mobile banking app: access 10min, refresh rotating 14d; a user pastes tokens into a malicious tool; first refresh by attacker succeeds (family moves), user's next refresh fails → family revoked → all sessions killed; push notification "suspicious sign-in"; incident closed without support call.

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

`POST /auth/refresh` performs rotation; `POST /auth/logout` deletes family keys; dependency validates access token signature/exp/aud/iss; `/me/sessions` lists active families for the user to revoke.

## 13. Distributed-system considerations

Security is global: identity, secrets, and policy must be consistent everywhere the workload runs — one unpatched region or sidecar undoes the rest.

## 14. AI/ML/LLM application examples where relevant

Short access tokens; rotate; reuse invalidates family — same discipline as any token-based API.

## 15. Security considerations

Refresh reuse kills the family — rotate always; short access tokens.

## 16. Performance considerations

TLS + auth cost ~1-10 ms per request — amortized by keepalive and token caching; never skip payment for security 'perf' reasons without measuring.

## 17. Common mistakes

7-day access tokens; no reuse detection; refresh without rotation; JWT always valid once issued ("stateless forever" fantasy); refresh tokens unhashed in DB; logout that only clears client storage.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `token_refresh_total`, family-revocations, `expired_token_rejected_total`

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Refresh twice with same old token → family revoked → 401 on both; logout → subsequent refresh 401; access token with wrong aud → 401; expiry boundary test with leeway; concurrent refresh from two tabs → only one wins.

## 21. Deployment considerations

Treat every change to auth/secrets/TLS as security-sensitive: staged rollout, monitoring on rejection rates, and a documented rollback that also rotates anything exposed.

## 22. Production-readiness checklist

- [ ] Short access expiry (5-15min)
- [ ] Rotating refresh with family-wide reuse kill
- [ ] Opaque or hashed-at-rest refresh tokens
- [ ] Per-device families
- [ ] Session listing + remote revoke
- [ ] Leeway in exp checks (clock skew, `#96`)
- [ ] Audit refresh events
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Reuse detection implemented but families not linked → theft undetected; refresh rotation not atomic (old token valid twice) → race creates two live tokens; long access-token lifetimes (24h+) defeat rotation; revocation store checked on every access request (defeats statelessness — just shorten expiry); refresh token in localStorage; family IDs guessable.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://datatracker.ietf.org/doc/html/rfc7519
- https://datatracker.ietf.org/doc/html/rfc6749

**Related topics in this library:** `#69 OAuth`, `#67 Secrets Management`, `#96 Clock Skew`, `#68 IAM`, `#71 TLS`.
