---
topic: 104
title: Infrastructure as Code
category: I
skill: production-engineering
status: stable
---

# 104 — Infrastructure as Code

## 1. Topic name and metadata

- **Number:** 104 of 111
- **Title:** Infrastructure as Code
- **Category:** I — Infrastructure and Build Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [devops-infrastructure.md](../references/infrastructure.md)
- **Topic file:** `.agents/skills/production-engineering/topics/104-infrastructure-as-code.md`

## 2. What it is

Describing infrastructure (networks, clusters, DBs, DNS, IAM) in declarative version-controlled code, applied by automation — reproducible, reviewable, auditable.

## 3. Why it exists

Infrastructure must be reproducible, reviewed, and auditable.

## 4. The engineering problem it solves

Console-clicked infrastructure drifts invisibly; disaster means re-deriving a config from someone's memory; audits are impossible; environments diverge.

## 5. How it works internally

Tools: Terraform/Pulumi (multi-cloud, declarative HCL/TS), CloudFormation/CDK (AWS), config-in-K8s itself. State (who owns what exists) lives in a remote backend (S3+DynamoDB lock); plan → review diff → apply; GitOps (ArgoCD) reconciles cluster state continuously. IaC applies to data-plane (K8s) via Helm/Kustomize and cloud via TF. Key shift: humans propose, pipeline applies; no console writes (immutable infra principle).

## 6. Architecture and design principles

Git repo (IaC source) -> CI plan/apply -> cloud provider APIs; remote state with locks; GitOps layer (ArgoCD/Flux) reconciles cluster state continuously; console writes forbidden (break glass only).

**Design principles for this category:** Everything reproducible from source; humans propose, pipelines apply; drift is an incident in waiting.

## 7. When to use it

Any infrastructure beyond a single VM — always.

## 8. When NOT to use it

Throwaway experiments (but graduate quickly).

**Alternatives:** ClickOps (never), config management only (Ansible — good for OS config, weak on cloud APIs), Pulumi (real language).

## 9. Implementation strategies

```
terraform init → terraform plan (shows diff) → PR review → terraform apply (CI)
GitOps: git push → ArgoCD syncs cluster within minutes, drift-alert on out-of-band changes
```

## 10. Production-grade implementation

**Scenario:** Full AWS environment (VPC, EKS, RDS, Route53, IAM) from one repo; new region rebuilt from scratch in 50 minutes for DR drill; security group rules reviewed in PRs; zero console changes in 18 months (detected via drift alerts; 2 attempted emergencies reverted).

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

Not applicable — this concept operates below or beside the LLM layer; it applies to AI systems only indirectly (e.g., via the platform that runs them). Do not force AI-specific machinery here; apply the standard pattern unchanged.

## 15. Security considerations

IaC review catches open security groups; policy-as-code (OPA/conftest) gates.

## 16. Performance considerations

Build infra cost is CI time + runner minutes; cache layers well and builds go 10-100x faster — the ROI is developer velocity, not runtime.

## 17. Common mistakes

ClickOps; state in laptop; mutable shared accounts; `apply -auto-approve` from dev machines; unpinned modules from internet; ignoring plan output; snowflake "temporary" fixes via console that become permanent.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `drift_detections_total`, `iac_apply_duration_seconds`

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Apply in isolated sandbox; `terraform validate`/`tflint`; conftest policies (no 0.0.0.0/0 ingress); drift alert drill; full-destroy-and-rebuild DR test quarterly; plan-diff PR review gate.

## 21. Deployment considerations

IaC changes: plan-in-PR, apply from CI only, state locks required, drift alerts on out-of-band console writes; rollback = revert commit + apply.

## 22. Production-readiness checklist

- [ ] Remote state + locking
- [ ] Workspaces per env (or dirs)
- [ ] Plan-in-PR
- [ ] Apply only from CI
- [ ] Minimal console access (break glass)
- [ ] Modules with pinned versions
- [ ] Policy as code (conftest/opa) for guardrails
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** State file leaked/corrupted (no remote backend lock → concurrent applies destroy state); `terraform destroy` against the wrong workspace; plan not reviewed (surprise destroy); secrets in .tf (use vault provider/SSM); console drift outpacing IaC; applying prod before staging; no lockfile (TF version skew); module sprawl with no standards.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://developer.hashicorp.com/terraform/docs
- https://www.terragrunt.dev/docs/

**Related topics in this library:** `#105 Terraform`, `#106 Helm Charts`, `#6 CI/CD`, `#7 Docker`, `#83 Disaster Recovery`, `#67 Secrets Management`.
