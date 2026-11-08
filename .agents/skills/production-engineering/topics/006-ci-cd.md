---
topic: 6
title: CI/CD
category: A
skill: production-engineering
status: stable
---

# 006 — CI/CD

## 1. Topic name and metadata

- **Number:** 6 of 111
- **Title:** CI/CD
- **Category:** A — Backend Architecture and API Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [devops-infrastructure.md](../references/infrastructure.md)
- **Topic file:** `.agents/skills/production-engineering/topics/006-ci-cd.md`

## 2. What it is

Continuous Integration (every push is tested and merged hot) + Continuous Delivery/Deployment (every green build is a releasable, automatically deployed artifact).

## 3. Why it exists

Manual build-and-deploy is slow, error-prone, and unrepeatable.

## 4. The engineering problem it solves

Big-bang integration and manual deploys are error-prone, slow, and unrepeatable — the deploy itself shouldn't be a ceremony.

## 5. How it works internally

Pipeline stages: lint → unit tests → build (immutable artifact tagged with commit SHA) → integration/contract tests → security scan (deps, SAST, secrets) → publish (registry) → deploy to staging → smoke tests → deploy to prod (canary/rolling). GitHub Actions OIDC for cloud auth (no static keys). Branch protection: PR must pass checks; environment protection rules (required reviewers) for prod.

## 6. Architecture and design principles

Git push → Actions runner → registry → staging env → prod env; deploy pipeline declared in repo (`.github/workflows/`).

**Design principles for this category:** Statelessness by design; every control is enforced at a boundary (edge/gateway/service); config over code; bounded resources everywhere.

## 7. When to use it

Always — no production software without CI.

## 8. When NOT to use it

N/a.

**Alternatives:** n/a — the only choice is self-hosted vs SaaS runners and how much automation in delivery stage.

## 9. Implementation strategies

```yaml
# .github/workflows/deploy.yml (excerpt)
on:
  push: { branches: [main] }
permissions: { id-token: write, contents: read }
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pipx run uv sync && uv run pytest -x
      - run: uv run ruff check . && uv run mypy src
  deploy:
    needs: test
    environment: production          # requires reviewers/approval
    steps:
      - uses: aws-actions/configure-aws-credentials@v4
        with: { role-to-assume: arn:aws:iam::123:role/gha-deploy, aws-region: us-east-1 }
      - run: helm upgrade --install app ./charts/app --values values-prod.yaml --atomic --timeout 10m
```

## 10. Production-grade implementation

**Scenario:** 3 commits/day → each deploys in ~8 min (test 3m, build 1m, deploy 4m); rollback rate 1.5%; PRs can't merge without green; prod deploys auto after staging smoke passes; incident correlation via SHA in every metric.

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

Across instances this concept only works if the state it relies on (limits, locks, caches) is externalized — Redis, DB, or the edge — never in process memory alone.

## 14. AI/ML/LLM application examples where relevant

Prompts, model versions, and eval suites flow through the same CI: prompt diff → eval gate → canary rollout of the model/prompt, with auto-rollback on quality regression.

## 15. Security considerations

Pipelines hold deploy credentials — OIDC with short-lived tokens, never static keys in YAML.

## 16. Performance considerations

The gateway/LB path adds ~1-3 ms; caches save 10-100x origin work; counters in Redis add one RTT — keep them on the hot path small.

## 17. Common mistakes

`continue-on-error`; manual "deploy Friday" runbooks; building twice (staging build ≠ prod build); secrets echoed to logs; no lint/format gate; 40-minute pipelines.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `ci_pipeline_duration_seconds`, failure rate, deploy frequency

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Pipeline on every PR; deliberate failing test → merge blocked; secrets scan blocks; staging smoke blocks prod; rollback drill via redeploy of previous SHA.

## 21. Deployment considerations

Roll out behind a canary or flag; watch 5xx + p99; rollback = traffic selector flip (gateway), not a rebuild.

## 22. Production-readiness checklist

- [ ] Build once, promote everywhere
- [ ] OIDC not keys
- [ ] Lock deps (uv.lock/package-lock)
- [ ] Fast pipeline (<10min target)
- [ ] Smoke tests post-deploy
- [ ] Artifact retention
- [ ] Cache dependencies
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** CI too slow (30min → devs skip it locally → breakage); no branch protection; deploy without staging; secrets in workflow YAML (OIDC instead); flaky tests tolerated (`continue-on-error` → rot); building per-environment (config drift — build once, promote); no deployment rollback automation; pipeline that passes but artifact broken (build/test drift — same interpreter everywhere, use containers).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://docs.github.com/en/actions
- https://www.github.com/features/actions

**Related topics in this library:** `#7 Docker`, `#8 Kubernetes`, `#104 Infrastructure as Code`, `#107 Build Caching`, `#102 API Versioning`, `#55 Rollbacks`, `#53 Canary Releases`.
