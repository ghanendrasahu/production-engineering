---
topic: 107
title: Build Caching
category: I
skill: production-engineering
status: stable
---

# 107 — Build Caching

## 1. Topic name and metadata

- **Number:** 107 of 111
- **Title:** Build Caching
- **Category:** I — Infrastructure and Build Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [devops-infrastructure.md](../references/infrastructure.md)
- **Topic file:** `.agents/skills/production-engineering/topics/107-build-caching.md`

## 2. What it is

Reusing prior compilation artifacts, dependency downloads, and layer results so builds take seconds instead of minutes — correctness-preserving, keyed by inputs.

## 3. Why it exists

Builds must be correct first — then incremental and fast.

## 4. The engineering problem it solves

20-minute CI builds kill flow, delay feedback, and double infra cost; missing/incoherent caches often cause flaky rebuilds with stale artifacts.

## 5. How it works internally

Layers: package-manager cache (uv/pip/npm downloads), layer caching (Docker layer per Dockerfile instruction — copy lockfiles before source), remote build cache (GHA cache/registry layer cache (type=gha, type=registry), BuildKit; Turbo/Nx/Bazel for polyglot monorepos (task-graph hashing)), compiler caches (ccache/sccache). Correctness: cache keys must include all inputs that change the output (lockfile, source hash); cache invalidation on wrong inputs serves stale artifacts silently — prefer cache misses (slow but correct) to stale correctness.

## 6. Architecture and design principles

Build graph spans three tiers — manager cache (uv/pip/npm), layer cache (Docker/BuildKit), and monorepo task cache (Turbo/Nx/Bazel via input hashing). CI hits registry/GHA caches to short-circuit work.

**Design principles for this category:** Everything reproducible from source; humans propose, pipelines apply; drift is an incident in waiting.

## 7. When to use it

Any build > 30s.

## 8. When NOT to use it

Trivially fast builds (no cache to hit).

**Alternatives:** remote execution (Bazel RBE), prebuilt base images, monorepo task runners (Turbo/Nx), artifact registry promotion.

## 9. Implementation strategies

```dockerfile
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev   # cached unless lockfiles change
COPY src ./src
```

```yaml
- uses: actions/cache@v4
  with: { path: ~/.cache/uv, key: uv-${{ hashFiles('uv.lock') }} }
# BuildKit: docker buildx build --cache-from=type=gha --cache-to=type=gha,mode=max
```

## 10. Production-grade implementation

**Scenario:** Monorepo 40 packages: BuildKit registry cache + GHA cache: image build 18min→2min cold / 20s warm; CI cost −70%; correctness preserved via cache keys bound to lockfile hashes and `uv sync --locked`.

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

Docker layer caching for 8GB model images — cache weights separately from code; CI pulls weights via init container, not COPY.

## 15. Security considerations

Cache poisoning → compromised builds — verify checksums, sign (cosign), registry isolation.

## 16. Performance considerations

Build infra cost is CI time + runner minutes; cache layers well and builds go 10-100x faster — the ROI is developer velocity, not runtime.

## 17. Common mistakes

Cache-key on branch name; `--no-cache` as norm ("it's flaky"); caching secrets/keys in layers; copying everything first; ignoring cache size growth; "works on my machine" caches.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `cache_hit_ratio` (build), `build_duration_seconds`, registry cache misses

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

CI job with cache disabled on schedule (verify green); hash-key audit; artifact provenance (digest) check; clean-room build from empty cache weekly; cache-hit metric in pipeline dashboard.

## 21. Deployment considerations

IaC changes: plan-in-PR, apply from CI only, state locks required, drift alerts on out-of-band console writes; rollback = revert commit + apply.

## 22. Production-readiness checklist

- [ ] Lockfile-first copies
- [ ] Cache keys from lockfile+source hashes
- [ ] Registry cache in CI (gha mode=max)
- [ ] BuildKit everywhere
- [ ] Prune cache policy
- [ ] Measure hit rate
- [ ] Immutable artifacts by digest after build
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Stale artifacts from wrong cache key (missing source hash → old code shipped!); `COPY . .` before dependency install (busts cache every change); package cache poisoning (a bad wheel cached forever); cache-miss storm after fleet upgrade; registry cache auth expiry breaking all builds; caching `node_modules` across platforms (binary mismatch → runtime crashes); `--cache-from` with no fallback.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://docs.docker.com/build/cache/
- https://github.com/moby/buildkit

**Related topics in this library:** `#6 CI/CD`, `#7 Docker`, `#103 Semantic Versioning`, `#108 Dependency Hell`, `#107 Build Caching` pairs with `#104 Infrastructure as Code`.
