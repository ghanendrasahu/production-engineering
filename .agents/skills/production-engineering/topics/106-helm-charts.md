---
topic: 106
title: Helm Charts
category: I
skill: production-engineering
status: stable
---

# 106 — Helm Charts

## 1. Topic name and metadata

- **Number:** 106 of 111
- **Title:** Helm Charts
- **Category:** I — Infrastructure and Build Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [devops-infrastructure.md](../references/infrastructure.md)
- **Topic file:** `.agents/skills/production-engineering/topics/106-helm-charts.md`

## 2. What it is

Parameterized Kubernetes YAML packages (charts) with templates, default values, and release history — `helm install/upgrade/rollback` manages versioned application deployments.

## 3. Why it exists

Kubernetes YAML must be parameterized, versioned, and rollback-able.

## 4. The engineering problem it solves

Raw K8s YAML copy-pasted per environment diverges and is error-prone; Helm gives templating, values injection, dependency packaging, and rollback.

## 5. How it works internally

Chart = `Chart.yaml` + `values.yaml` + `templates/*.yaml` (Go templates with sprig functions); `values.yaml` overridden by `-f prod-values.yaml` / `--set`; releases tracked in a K8s Secret (sh.helm.release.v1) with revision history; `helm rollback chart 3` restores prior manifests; `helm template` renders locally for review; `helm upgrade --install --atomic` auto-rolls back on failure; charts from repos (Artifact Hub) or OCI registries.

## 6. Architecture and design principles

Chart (templates + values) -> `helm template` renders final manifests -> K8s API; release revisions stored as Secrets for audit and rollback; charts vendored in repo or pulled from an OCI registry.

**Design principles for this category:** Everything reproducible from source; humans propose, pipelines apply; drift is an incident in waiting.

## 7. When to use it

Repeated K8s deploys across services/envs — the default packaging.

## 8. When NOT to use it

Single-cluster single-app (raw manifests acceptable); someone proposes templating everything (use Kustomize instead of Helm's complexity).

**Alternatives:** Kustomize (overlays, simpler), CDK8s, timoni, raw manifests, ArgoCD App-of-Apps.

## 9. Implementation strategies

```bash
helm create app && helm upgrade --install api ./charts/app -f values-prod.yaml \
  --namespace payments --atomic --timeout 5m --wait
helm template api ./charts/app -f values-prod.yaml > /tmp/rendered.yaml   # review diff
helm rollback api 41 --namespace payments
```

values-prod.yaml: `replicas: 6`, `image.tag: v2.4.1`, `resources.*`, `envFrom: secretRef`.

## 10. Production-grade implementation

**Scenario:** One chart (Python FastAPI + sidecar + HPA + Service + Ingress + PDB + NetworkPolicy) deployed for 14 environments; values files per env; chart versioned independently (v1.9.0); rollback in 20s during a bad deploy; chart testing in CI with `helm template` + `kubectl --dry-run=server` + integration cluster.

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

Helm charts for inference servers (vLLM values: TP size, max-num-seqs, GPU resources, probes).

## 15. Security considerations

Values files are input — validate with schema; no secrets; image digests.

## 16. Performance considerations

Build infra cost is CI time + runner minutes; cache layers well and builds go 10-100x faster — the ROI is developer velocity, not runtime.

## 17. Common mistakes

Raw YAML forks; secrets in values.yaml; charts as god-objects with 1000 flags; unreviewed public charts; `--force` as habit; no rollback practice; editing live objects then "helm save" drift.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `helm_release_revisions`, upgrade failures, `--atomic` rollbacks

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

`helm lint`; `helm template` snapshot tests; `helm unittest` plugin; kind-cluster smoke install in CI; rollback test; schema validation (values.schema.json); policy check (kyverno).

## 21. Deployment considerations

IaC changes: plan-in-PR, apply from CI only, state locks required, drift alerts on out-of-band console writes; rollback = revert commit + apply.

## 22. Production-readiness checklist

- [ ] `--atomic --wait` always
- [ ] Chart versioning + CHANGELOG
- [ ] Values hierarchy per env
- [ ] Lint (helm lint) in CI
- [ ] Render-and-diff in PRs
- [ ] ExternalSecrets for creds
- [ ] Chart tests (template snapshot)
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Untested template change renders invalid YAML in prod (CI must run `helm template` + validation); `--set` typo silently creating new empty value; values sprawl (500-line values-prod with duplication — use hierarchy and `tpl`); secrets in values committed to git (externalSecrets/sealed-secrets instead); chart upgrades across major versions breaking CRDs (`--atomic` mandatory); installing internet charts without review (supply chain); no resource limits in chart defaults.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://helm.sh/docs/
- https://helm.sh/docs/chart_best_practices/

**Related topics in this library:** `#7 Docker`, `#8 Kubernetes`, `#104 Infrastructure as Code`, `#105 Terraform`, `#6 CI/CD`, `#55 Rollbacks`.
