---
topic: 103
title: Semantic Versioning
category: H
skill: production-engineering
status: stable
---

# 103 — Semantic Versioning

## 1. Topic name and metadata

- **Number:** 103 of 111
- **Title:** Semantic Versioning
- **Category:** H — Networking and Communication
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [networking-apis.md](../references/networking.md)
- **Topic file:** `.agents/skills/production-engineering/topics/103-semantic-versioning.md`

## 2. What it is

`MAJOR.MINOR.PATCH` (semver 2.0.0): MAJOR = incompatible API changes, MINOR = backwards-compatible features, PATCH = backwards-compatible fixes — a machine- and human-readable change contract.

## 3. Why it exists

Version numbers must tell the truth about compatibility.

## 4. The engineering problem it solves

Without meaning in version numbers, dependency resolution is guesswork; one bump can silently break a fleet — semver makes compatibility explicit and tooling trustworthy.

## 5. How it works internally

Rules: 0.x = initial dev (anything may change); 1.0.0 first stable; MAJOR bump for breaks; MINOR for additions; PATCH for fixes. Pre-release tags: `1.4.0-rc.1`. Build metadata after `+`. Ranges in manifests (`^1.4.0` = any ≥1.4 <2.0; `~` = patch-level) interact with lockfiles (poetry.lock/uv.lock/package-lock) — lockfiles pin exact, constraints allow compatible; libraries publish semver; apps lock. Deprecation inside semver: mark deprecated in docs, remove only on MAJOR.

## 6. Architecture and design principles

Convention inside every published artifact: version lives in packaging metadata (pyproject/package.json), git tags, registry artifacts and changelogs; consumers express intent as semver ranges; lockfiles pin exactness for apps.

**Design principles for this category:** Choose transport by semantics (ordering, latency, loss tolerance); name everything through discovery, never literals.

## 7. When to use it

Any published library or internal SDK/service artifact — always.

## 8. When NOT to use it

N/a (it's a convention; use it).

**Alternatives:** date versioning (CalVer — good for apps/distributions like Ubuntu), 0.x for honest instability.

<!--END-->

## 9. Implementation strategies

```
pyproject.toml: version = "2.3.1"
^2.3.1  → allows 2.4.0, never 3.0.0
git tag v2.4.0 → CI builds & publishes; changelog from conventional commits
```

Conventional Commits (`feat:`/`fix:`/`feat!:`) automate bump selection.

## 10. Production-grade implementation

**Scenario:** Internal SDK `orders-client`: semver enforced by `semantic-release` in CI; dependabot proposes only patch/minor automatically; MAJOR upgrades arrive as planned migrations with codemods; zero surprise breaks in 6 services across 4 months.

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

Prompt template = API surface — semver-ish for prompts is overkill; pin `prompt_version` in logs/metrics.

## 15. Security considerations

Semver lies → unsafe upgrades — pin majors, scan diffs, CI contract tests.

## 16. Performance considerations

Protocol choice is throughput choice: HTTP/2 multiplexing, gRPC streaming, QUIC vs TCP trade loss sensitivity against HOL blocking.

## 17. Common mistakes

Manual version bumps; `^0.x` assumptions (0.y.z is all-breaking); `latest` in prod; breaking change snuck in MINOR; tags and pyproject drift; no lockfile in app repos.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `breaking_changes_blocked_total`, release success rate

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

CI gates: lockfile freshness, changelog presence, semver lint (commit analyzer); staging ingest of new minor; consumer contract tests (Pact) across dependent services.

## 21. Deployment considerations

Protocol/version changes are deploys too: enable H2/H3 at the edge first, verify clients, then simplify origins; DNS/cert changes rehearsed with low TTL.

## 22. Production-readiness checklist

- [ ] Conventional commits + automated release
- [ ] Lockfiles for apps, semver ranges for libraries
- [ ] `feat!`/`BREAKING CHANGE:` signals MAJOR
- [ ] Deprecate before remove
- [ ] Pin CI tools
- [ ] Verify upgrade in staging before automerge (dependabot grouping)
- [ ] Changelog per release
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Breaking change in MINOR ("it's only adding a header" — it wasn't); 0.x forever (users fear upgrades — fine, but be honest about stability); lockfile ignored (production ≠ tested version); releasing 1.0.0 prematurely (compat burden); version bumps by one dev without review; changelog inconsistent with tags; transitive deps floating (`latest`) — untraceable builds.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://semver.org/
- https://www.conventionalcommits.org/

**Related topics in this library:** `#102 API Versioning`, `#6 CI/CD`, `#106 Helm Charts`, `#107 Build Caching`, `#108 Dependency Hell`, `#81 Database Migrations`.
