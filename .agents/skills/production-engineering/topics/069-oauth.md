---
topic: 69
title: OAuth
category: D
skill: production-engineering
status: stable
---

# 069 — OAuth

## 1. Topic name and metadata

- **Number:** 69 of 111
- **Title:** OAuth
- **Category:** D — Security Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [security-engineering.md](../references/security.md)
- **Topic file:** `.agents/skills/production-engineering/topics/069-oauth.md`

## 2. What it is

An authorization framework (OAuth 2.0/2.1) in which a user grants a third-party application limited access to their resources on another service, without sharing their password.

## 3. Why it exists

Users should grant scoped access, not share passwords.

## 4. The engineering problem it solves

The pre-OAuth world of password-sharing and stored credentials; applications needed access to user data without ever seeing the password, and users needed revocable, scoped grants.

## 5. How it works internally

Roles: resource owner, client, authorization server, resource server. Flows: authorization code + PKCE (the only safe flow for public/web apps — issues a code exchanged for tokens; PKCE prevents code interception), client credentials (machine-to-machine), refresh token grant (long-lived refresh + short-lived access). ID tokens (OpenID Connect) add identity to OAuth. Scopes bound access (`read:orders`). Tokens are bearer — transport security is mandatory (TLS). Revocation endpoint + introspection for opaque tokens; JWT access tokens validated locally via JWKS.

## 6. Architecture and design principles

Browser/app → provider (Google/Auth0/Keycloak) → redirect with code → backend exchanges code for tokens → validates JWT via JWKS → session/cookie for the app.

**Design principles for this category:** Deny by default; least privilege; defense in depth — no single control carries the weight; shift security left into CI.

## 7. When to use it

User-facing login, third-party integrations, SSO.

## 8. When NOT to use it

Pure machine-to-machine (client credentials subset), internal service mesh (mTLS + SPIFFE better).

**Alternatives:** session cookies after SSO, API keys for server-to-server (`#67`), mTLS, SAML (enterprise legacy).

## 9. Implementation strategies

```python
import requests
# authorization code + PKCE exchange
token = requests.post("https://idp/token", data={
    "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
    "client_id": CLIENT_ID, "code_verifier": verifier}).json()
```

JWKS verify: `jwt.decode(access_token, key=jwks_client.get_signing_key_from_jwt(token).key, algorithms=["RS256"], audience="my-api", issuer="https://idp")`.

## 10. Production-grade implementation

**Scenario:** Customer portal "Sign in with Google": Authlib, PKCE enforced, access token 15min, refresh 30d rotating, scopes `openid email profile read:orders`; a leaked token expires in 15min; Google revoked-credential events processed via webhook to clear app sessions.

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

`OAuth2PasswordBearer` or Authlib middleware; dependency validates JWT on every route; scopes checked per route via `Security(scopes_required)`; refresh tokens stored hashed, rotation on use.

## 13. Distributed-system considerations

Security is global: identity, secrets, and policy must be consistent everywhere the workload runs — one unpatched region or sidecar undoes the rest.

## 14. AI/ML/LLM application examples where relevant

User-facing AI apps use OAuth2+PKCE; service tokens for model-to-model calls — client credentials only, short TTL.

## 15. Security considerations

Scope minimally; PKCE; exact redirect URIs; rotation; introspect opaque tokens.

## 16. Performance considerations

TLS + auth cost ~1-10 ms per request — amortized by keepalive and token caching; never skip payment for security 'perf' reasons without measuring.

## 17. Common mistakes

Implicit flow (deprecated); password grant; custom "OAuth-like" homegrown; tokens in localStorage/XSS-exposed; scopes never reviewed ("read:all"); no revocation path.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `oauth_token_issuance_total`, `refresh_reuse_detected_total`

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Full integration against Keycloak in Docker-compose; tampered token → 401; expired token → refresh path; wrong-audience token → 401; refresh reuse → family invalidated; state mismatch → rejection.

## 21. Deployment considerations

Treat every change to auth/secrets/TLS as security-sensitive: staged rollout, monitoring on rejection rates, and a documented rollback that also rotates anything exposed.

## 22. Production-readiness checklist

- [ ] Authorization code + PKCE only
- [ ] State param
- [ ] Exact redirect URIs
- [ ] Short-lived access tokens
- [ ] Rotating refresh tokens with reuse detection (invalidate the family)
- [ ] Validate aud/iss/exp/alg
- [ ] Store tokens HttpOnly
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Missing PKCE (code interception); `state` parameter missing → CSRF on login; tokens in localStorage (XSS-stealable — prefer HttpOnly Secure SameSite cookie); refresh tokens never rotated/reused forever; redirect_uri wildcard (`https://*.app.com`) → token leak to attacker subdomain; accepting any `alg` in JWT verify (alg=none attack); no aud/iss check → token replay across services.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://www.rfc-editor.org/rfc/rfc6749
- https://datatracker.ietf.org/wg/oauth/documents/

**Related topics in this library:** `#70 JWT Rotation`, `#68 IAM`, `#71 TLS`, `#76 CORS`, `#77 CSRF`, `#69 OAuth` uses `#73 Encryption in Transit`.
