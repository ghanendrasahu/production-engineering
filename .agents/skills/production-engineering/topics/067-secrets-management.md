---
topic: 67
title: Secrets Management
category: D
skill: production-engineering
status: stable
---

# 067 — Secrets Management

## 1. Topic name and metadata

- **Number:** 67 of 111
- **Title:** Secrets Management
- **Category:** D — Security Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [security-engineering.md](../references/security.md)
- **Topic file:** `.agents/skills/production-engineering/topics/067-secrets-management.md`

## 2. What it is

Storage, distribution, rotation, and audit of credentials (API keys, DB passwords, certs) so they never live in source code, images, or logs.

## 3. Why it exists

Secrets in code are public from the moment they are committed.

## 4. The engineering problem it solves

A secret in Git or an image layer is public forever — the single most common initial access vector in real breaches; rotation without tooling is impossible in practice.

## 5. How it works internally

A secrets manager (Vault, AWS Secrets Manager, GCP Secret Manager, Azure Key Vault, K8s Secrets + external-secrets operator, sealed-secrets) holds encrypted secrets, issues short-lived dynamic credentials (Vault DB dynamic secrets, AWS STS), enforces policy on access, and audits every read. Injection mechanisms: env vars at deploy time (ok, but visible to process env), files mounted from CSI drivers, or app-side fetch at startup with cache + TTL. Rotation: dual-credential overlap window — new secret issued, old revoked after consumers move.

## 6. Architecture and design principles

CI/CD retrieves secrets at deploy; app reads at startup/runtime; no secret in Docker image or repo; K8s: External Secrets Operator syncs Vault/AWS SM → K8s Secret mounted as env/volume (encrypt etcd!).

**Design principles for this category:** Deny by default; least privilege; defense in depth — no single control carries the weight; shift security left into CI.

## 7. When to use it

Always — no exceptions for production.

## 8. When NOT to use it

N/a.

**Alternatives:** platform-native (K8s CSI + cloud KMS-backed stores), dynamic credentials (Vault), workload identity (IRSA/Workload Identity — no secret at all).

## 9. Implementation strategies

```bash
vault kv put secret/prod/db password=$(openssl rand -base64 32)
vault read -field=password secret/prod/db
# k8s: externalSecret or sealedSecret YAML synced from Vault/SM
```

```python
import os
DATABASE_URL = os.environ["DATABASE_URL"]   # injected by platform, never committed
```

## 10. Production-grade implementation

**Scenario:** RDS credentials rotated by Vault every 30 days with dynamic secrets per pod; a leaked key from an old commit loses access within 30 days; audit log shows which identity read which secret; zero long-lived DB passwords anywhere in configs.

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

`pydantic-settings` `BaseSettings` loading `DATABASE_URL`, `STRIPE_API_KEY` from env with `.env` only in local dev (gitignored); refuse to boot if `APP_ENV=prod` and any key missing.

## 13. Distributed-system considerations

Security is global: identity, secrets, and policy must be consistent everywhere the workload runs — one unpatched region or sidecar undoes the rest.

## 14. AI/ML/LLM application examples where relevant

Provider API keys are crown jewels — manager, rotation, per-tenant routing keys never in logs.

## 15. Security considerations

The root control — manager + rotation + audit + no env sprawl.

## 16. Performance considerations

TLS + auth cost ~1-10 ms per request — amortized by keepalive and token caching; never skip payment for security 'perf' reasons without measuring.

## 17. Common mistakes

`.env` in repo; secrets in Dockerfile/base images; one shared secret for all services (blast radius = everything); rotation "when convenient"; secrets in frontend env vars (`NEXT_PUBLIC_*`); logging request headers wholesale.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `secret_age_days`, `secret_rotation_failures`, access denials

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Scan CI with detect-secrets/gitleaks; rotate a staging secret and verify zero-downtime; verify app refuses boot without keys; assert no env key appears in logs on error paths; periodic access-audit review.

## 21. Deployment considerations

Treat every change to auth/secrets/TLS as security-sensitive: staged rollout, monitoring on rejection rates, and a documented rollback that also rotates anything exposed.

## 22. Production-readiness checklist

- [ ] Manager, never files
- [ ] Dynamic short-lived credentials where possible
- [ ] Rotation automation
- [ ] Least-privilege per secret
- [ ] Audit on access
- [ ] Scrub secrets from logs
- [ ] `.gitignore` + pre-commit `detect-secrets`
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Secret committed → must rotate immediately (prevention beats cleanup; git history rewritening doesn't unpublish); env var logged by a debug middleware ("dumping config") → log scrubber + denylist; secret rotation without overlap → prod 500s; K8s Secret base64 is not encryption — etcd unencrypted at rest; secrets baked into Docker layers visible via `docker history`; CI logs echoing env during debug builds.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://www.vaultproject.io/docs/
- https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html

**Related topics in this library:** `#68 IAM`, `#72 Encryption at Rest`, `#71 TLS`, `#6 CI/CD` (secrets in pipelines), `#67 Secrets Management` pairs with `#73 Encryption in Transit`.
