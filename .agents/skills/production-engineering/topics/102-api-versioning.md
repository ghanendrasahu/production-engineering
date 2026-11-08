---
topic: 102
title: API Versioning
category: H
skill: production-engineering
status: stable
---

# 102 — API Versioning

## 1. Topic name and metadata

- **Number:** 102 of 111
- **Title:** API Versioning
- **Category:** H — Networking and Communication
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [networking-apis.md](../references/networking.md)
- **Topic file:** `.agents/skills/production-engineering/topics/102-api-versioning.md`

## 2. What it is

The practice of evolving APIs while keeping existing clients working — by path (`/v1/`), header (`Accept: application/vnd.app.v2+json`), or date — with a documented deprecation lifecycle.

## 3. Why it exists

APIs must evolve without breaking clients in the field.

## 4. The engineering problem it solves

Breaking clients silently erodes trust; versioning gives everyone a migration runway and the provider a way to move forward.

## 5. How it works internally

Path versioning: `/v1/orders` and `/v2/orders` — visible, cacheable, simple, most common. Header/content negotiation: cleaner URLs, harder to test/debug. Date-based (Stripe: `2026-10-01`): strong immutability per release. Contract rules: additive changes free (new optional fields); breaking changes (renamed fields, removed endpoints, changed semantics, required new fields) require new version. Deprecation: `Sunset` + `Deprecation` headers (RFC 8594), 12-month window, docs + SDK bumps + migration guides, metrics per version to know who's left. Never: silent behavior change behind same version.

## 6. Architecture and design principles

Gateway/router maps version → handler; shared business logic underneath both versions; contract tests per version; error format stable across versions.

**Design principles for this category:** Choose transport by semantics (ordering, latency, loss tolerance); name everything through discovery, never literals.

## 7. When to use it

Any API consumed by others — always.

## 8. When NOT to use it

Pure internal prototyped API that will be rewritten (but you'll regret it).

**Alternatives:** date versioning (Stripe), media-type negotiation (GitHub/v3+json), additive-only + flags for internal services.

## 9. Implementation strategies

```python
router_v1 = APIRouter(prefix="/v1")
router_v2 = APIRouter(prefix="/v2")
app.include_router(router_v1); app.include_router(router_v2)
@app.middleware("http")
async def sunset_header(request, call_next):
    r = await call_next(request)
    if request.url.path.startswith("/v1/"): r.headers["Sunset"] = "Sat, 30 Oct 2027 00:00:00 GMT"; r.headers["Deprecation"] = "true"
    return r
```

## 10. Production-grade implementation

**Scenario:** v2 introduces required `idempotency_key` on POST /charges; shipped alongside v1; 14 months migration; per-version metrics show v1 traffic 40%→3%; deprecation emails; Sunset header live; v1 removed after SLA window; mobile clients guided via SDK min-version.

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

The network is the shared resource: ordering, loss, partitions, and clock skew are not pathologies — they are the medium. Design with them.

## 14. AI/ML/LLM application examples where relevant

Change `POST /chat` behavior? Version the model behavior contract — `x-model-version` header or path version.

## 15. Security considerations

N versions = N attack surfaces — Sunset headers and enforced deprecation.

## 16. Performance considerations

Protocol choice is throughput choice: HTTP/2 multiplexing, gRPC streaming, QUIC vs TCP trade loss sensitivity against HOL blocking.

## 17. Common mistakes

Header-only versioning invisible in URLs; breaking change Friday; v1 never removed; implicit latest; inconsistent error shapes across versions.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `requests_by_version{version}`, deprecation-header coverage

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Contract tests per version (schema validation); Sunset headers asserted; migration soak (v1 clients against v2 via adapter); usage metric assertions; rollback test (v2 flag off).

## 21. Deployment considerations

Protocol/version changes are deploys too: enable H2/H3 at the edge first, verify clients, then simplify origins; DNS/cert changes rehearsed with low TTL.

## 22. Production-readiness checklist

- [ ] Path versioning for simplicity
- [ ] Additive-only within a version
- [ ] Deprecation policy with Sunset headers
- [ ] Shared core, thin adapters
- [ ] Per-version usage metrics
- [ ] Contract tests per version
- [ ] 12-month minimum deprecation for public APIs
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Breaking change under same version; versioning only some endpoints (half-versioned API); unbounded version count (v1..v9 all live forever); missing Sunset communication; v2 = rewrite with drift (logic diverges — share core code); deprecating without telemetry (who is left?); date versioning with undated clients (guess which behavior).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://www.rfc-editor.org/rfc/rfc8594

**Related topics in this library:** `#103 Semantic Versioning`, `#5 API Gateways`, `#51 Feature Flags`, `#81 Database Migrations` (expand/contract mirrors this), `#100 gRPC` (proto evolution rules).
