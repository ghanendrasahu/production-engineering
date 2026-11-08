---
topic: 108
title: Dependency Hell
category: I
skill: production-engineering
status: stable
---

# 108 — Dependency Hell

## 1. Topic name and metadata

- **Number:** 108 of 111
- **Title:** Dependency Hell
- **Category:** I — Infrastructure and Build Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [devops-infrastructure.md](../references/infrastructure.md)
- **Topic file:** `.agents/skills/production-engineering/topics/108-dependency-hell.md`

## 2. What it is

The accumulated failure modes of third-party dependencies: version conflicts, transitive breakage, unmaintained packages, supply-chain attacks, license incompatibility, and "works in CI, fails in prod" from environment drift.

## 3. Why it exists

Your service is the sum of dependencies you did not write.

## 4. The engineering problem it solves

Your service is the sum of dependencies you didn't write and don't fully understand; one bad release or unpinned transitive can halt the fleet (`left-pad`, event-stream, colors.js) — and slow silent rot.

## 5. How it works internally

Resolution: SAT/backtracking solvers (pip/poetry/uv/npm) pick versions satisfying constraints; conflicts when two packages want incompatible ranges. Defenses: lockfiles pin the full resolved graph (never `pip install` without pinning), SBOM (syft) for inventory, osv-scanner/pip-audit/dependabot for CVEs, license scanning (FOSSA), minimal dependencies policy (stdlib-first), vendored copies for critical paths, `pip-tools`/`uv pip compile` for bound-exact pins, virtualenv/poetry/uv isolation, one Python version per project (`requires-python`).

## 6. Architecture and design principles

Resolution happens at install time (lockfile -> exact graph); SBOM inventory flows from build to scanner to policy gate; private registry proxies act as a controlled choke point for supply-chain trust.

**Design principles for this category:** Everything reproducible from source; humans propose, pipelines apply; drift is an incident in waiting.

## 7. When to use it

Every project — dependency discipline is mandatory.

## 8. When NOT to use it

N/a.

**Alternatives:** vendored minimal deps, Rust/Go single-binary builds reducing runtime deps, monorepo shared pins.

<!--END-->

## 9. Implementation strategies

```bash
uv lock && uv sync --frozen          # exact, reproducible
pip-audit                            # CVEs
osv-scanner scan --recursive .
uv run pip check                     # dependency conflicts
npx npm-check-updates                # see upgrade candidates
```

SBOM in CI: `syft packages . -o cyclonedx-json`; diff SBOM per release.

## 10. Production-grade implementation

**Scenario:** A transitive dep introduced a segfault on glibc 2.36 via wheel mismatch; caught in staging because lockfile+reproducible env matched prod exactly; root-caused via SBOM in 20 minutes; fix: bump one top-level pin; lesson: reproducibility > speed.

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

Infrastructure is a distributed fleet too — state locks, drift detection, and idempotent applies are the concurrency control of machines, not processes.

## 14. AI/ML/LLM application examples where relevant

Pin CUDA/torch/vLLM matrix — one bad transformers bump breaks the whole fleet; lock and scan.

## 15. Security considerations

Dependency confusion — scoped namespaces, lockfiles, hash verification.

## 16. Performance considerations

Build infra cost is CI time + runner minutes; cache layers well and builds go 10-100x faster — the ROI is developer velocity, not runtime.

## 17. Common mistakes

`pip install -r requirements.txt` without pins; editing lockfiles by hand; ignoring patch CVEs for 6 months; dependabot automerge without tests; giant frameworks for "maybe" needs; no SBOM; force-upgrading everything in one PR.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `dependency_vulnerabilities_total{severity}`, conflict errors in CI

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

`uv sync --frozen` in CI (byte-identical env); osv gate; license scan; conflict `pip check`; quarterly dep-audit report; clean-env repro of prod in staging.

## 21. Deployment considerations

IaC changes: plan-in-PR, apply from CI only, state locks required, drift alerts on out-of-band console writes; rollback = revert commit + apply.

## 22. Production-readiness checklist

- [ ] Lock everything (apps)
- [ ] Ranges only in libraries
- [ ] Uv/poetry/npm ci in CI
- [ ] Dependabot + automerge for patches with CI green
- [ ] Osv-scanner gate on critical
- [ ] SBOM per release
- [ ] Dependency budget review quarterly
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Unpinned transitive → next CI run breaks (colors.js-style); `pip install pkg` directly in Dockerfile with no lockfile → untraceable runtime drift; CVE in abandoned package with no fix (fork/replace or drop); license: AGPL dependency in proprietary service; `^0.x` floating semantics re-interpreted; two packages requiring conflicting protobuf versions → import-time crashes; dependency confusion (private package name published to public registry — npm/pip pick public by default).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://osv.dev/
- https://pip.pypa.io/en/stable/

**Related topics in this library:** `#103 Semantic Versioning`, `#107 Build Caching`, `#6 CI/CD`, `#104 Infrastructure as Code`, `#109 Production Incidents` (supply-chain incidents), `#68 IAM` (least-privilege for registries).
