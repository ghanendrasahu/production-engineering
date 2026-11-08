---
topic: 105
title: Terraform
category: I
skill: production-engineering
status: stable
---

# 105 — Terraform

## 1. Topic name and metadata

- **Number:** 105 of 111
- **Title:** Terraform
- **Category:** I — Infrastructure and Build Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [devops-infrastructure.md](../references/infrastructure.md)
- **Topic file:** `.agents/skills/production-engineering/topics/105-terraform.md`

## 2. What it is

The dominant multi-cloud IaC tool: HCL-declared resources, a state file reconciling desired vs actual, and a plan/apply workflow.

## 3. Why it exists

One tool should plan and apply cloud state from version control.

## 4. The engineering problem it solves

Same as `#104` — but Terraform specifically because it spans AWS/GCP/Azure/K8s with one workflow and a huge provider ecosystem.

## 5. How it works internally

Providers expose resources as schemas; TF builds a dependency graph → parallelizes → computes diffs against state; backends (S3+DynamoDB or TFCloud) store state and lock it; workspaces isolate envs; modules encapsulate reusable sets ("vpc", "eks"); `terraform plan -out=tfplan` freezes the apply; drift = state vs reality divergence (use refresh + orphan detection). Safety: never `apply` unreviewed plan; `prevent_destroy` lifecycle for critical resources (DBs, buckets); `-replace` for surgical recreation.

## 6. Architecture and design principles

HCL source -> dependency graph -> provider plugins -> cloud APIs; state (who owns what) lives in a remote backend with locking; workspaces/dirs per environment; CI is the only writer.

**Design principles for this category:** Everything reproducible from source; humans propose, pipelines apply; drift is an incident in waiting.

## 7. When to use it

Cloud infra with any complexity — the default.

## 8. When NOT to use it

K8s-only config (Helm/Kustomize better fit for cluster apps); team prefers Pulumi/CDK deliberately.

**Alternatives:** CDK/Pulumi (general languages), Ansible (OS config), Crossplane (K8s-native IaC for cloud).

## 9. Implementation strategies

```hcl
terraform { backend "s3" { bucket = "tf-state"; dynamodb_table = "tf-lock"; key = "prod/app.tf"; }
  required_version = ">= 1.6" }
resource "aws_db_instance" "main" {
  identifier = "app-prod"; engine = "postgres"; instance_class = "db.m6g.large"
  allocated_storage = 100; storage_encrypted = true; multi_az = true
  lifecycle { prevent_destroy = true } }
output "db_endpoint" { value = aws_db_instance.main.endpoint }
```

## 10. Production-grade implementation

**Scenario:** 6 TF workspaces (3 apps × staging/prod); PR shows "2 to add, 1 to change"; DB instance protected with prevent_destroy; weekly drift scan (`terraform plan -detailed-exitcode`) alerts on out-of-band changes; new dev env spun up in 25 minutes from module.

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

GPU infra in Terraform: node pools, MIG partitions, IAM for S3 model buckets — plan reviews catch quota surprises.

## 15. Security considerations

State holds DB passwords — remote backend encrypted, IAM-scoped, versioned.

## 16. Performance considerations

Build infra cost is CI time + runner minutes; cache layers well and builds go 10-100x faster — the ROI is developer velocity, not runtime.

## 17. Common mistakes

Laptop state; `terraform destroy` in prod workflows; unpinned providers/modules; state bucket public; console + TF both managing same resource; one 2,000-line main.tf; no state backups; committing secrets (use SSM/Vault data sources).

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `terraform_plan_changes`, apply failures, state lock contentions

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

`terraform validate`+`fmt` in pre-commit; tflint; conftest policies (deny public buckets); applies in ephemeral sandbox accounts; destroy-test in sandbox quarterly; state backup test; drift monitoring.

## 21. Deployment considerations

IaC changes: plan-in-PR, apply from CI only, state locks required, drift alerts on out-of-band console writes; rollback = revert commit + apply.

## 22. Production-readiness checklist

- [ ] Remote state+lock
- [ ] Commit lock file
- [ ] Pin providers/modules
- [ ] Plan-in-PR
- [ ] Prevent_destroy on data stores
- [ ] Workspace per env
- [ ] CI-only apply
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** State lock not used → two applies interleave, corrupt state (mitigate: backend lock, one pipeline per workspace); plan apply skew (built hours ago); provider version float (lock .terraform.lock.hcl — commit it); secret in state (state contains DB passwords! encrypt bucket, restrict access); module from registry compromised supply chain (pin version + checksum); `-target` abused to skip deps → inconsistent apply; destroy on wrong workspace (name workspaces carefully, use dirs).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://developer.hashicorp.com/terraform/docs
- https://github.com/terraform-linters/tflint

**Related topics in this library:** `#104 Infrastructure as Code`, `#106 Helm Charts`, `#6 CI/CD`, `#67 Secrets Management`, `#83 Disaster Recovery`, `#108 Dependency Hell` (modules pinning).
