---
topic: 52
title: Blue-Green Deployment
category: C
skill: production-engineering
status: stable
---

# 052 — Blue-Green Deployment

## 1. Topic name and metadata

- **Number:** 52 of 111
- **Title:** Blue-Green Deployment
- **Category:** C — Deployment and Production Operations
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [deployment-operations.md](../references/deployment.md)
- **Topic file:** `.agents/skills/production-engineering/topics/052-blue-green-deployment.md`

## 2. What it is

Two full production environments (blue = current, green = new); deploy to green, validate, then switch all traffic over; rollback = flip back.

## 3. Why it exists

Two environments, one router: instant switch, instant rollback.

## 4. The engineering problem it solves

Zero-downtime cutover with instant revert — the safest high-ceremony rollout for stateful or big changes where rolling can't validate before traffic shift.

## 5. How it works internally

Router (LB/DNS/service selector) points 100% of traffic at one environment; new build boots green behind the router with smoke tests; switch flips a selector (K8s Service selector change, weighted LB target switch, or blue/green ALB target groups) — DNS switching is slow (TTL) so prefer LB/selector flip; data-plane compatibility required: green code must run on the shared DB (expand/contract migrations). After bake time, old environment is kept warm for fast flip-back, then torn down.

## 6. Architecture and design principles

Two identical stacks behind one router; shared database; router holds the flip switch; deployment tooling (ArgoCD, pipeline, or manual) performs flip + verification.

**Design principles for this category:** Everything declarative and reversible; the pipeline is the only writer; health must be observable from outside the process.

## 7. When to use it

Big/stateful releases needing rehearsed instant rollback; databases tolerate dual-version; capacity available.

## 8. When NOT to use it

Infra cost doubles unacceptably; frequent small deploys (rolling or canary cheaper); schema changes are destructive.

**Alternatives:** rolling with surge, canary, flags + rolling.

## 9. Implementation strategies

```yaml
# K8s: two Deployments + one Service selector flipped atomically
kind: Service
spec: { selector: { version: blue } }   # flip to green: kubectl patch svc/app -p '{"spec":{"selector":{"version":"green"}}}'
```

```bash
aws elbv2 modify-listener --listener-arn $ARN --default-actions Type=forward,TargetGroupArn=$GREEN_TG
```

## 10. Production-grade implementation

**Scenario:** Payment monolith v2.4 rebuilt; green boots, smoke suite passes (cert, DB rev, queue consumers), LB flips in 2 seconds; p95 identical; one anomalous error-budget burn 8 minutes later → flip back to blue instantly; zero user-facing downtime; postmortem: unknown env var in green — caught by smoke assertions added after.

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

Rollout safety across a fleet: probes, budgets, and automatic rollback are the distributed-systems controls for deployments — a bad pod must be ejected, not tolerated.

## 14. AI/ML/LLM application examples where relevant

Canary a new chatbot/UI revision the same way — with QA-approved prompt parity first.

## 15. Security considerations

Green must enforce identical auth — parity drift is a bypass.

## 16. Performance considerations

Rollout mechanisms are free at steady state; the wins come from staying ahead of capacity — probes and autoscalers prevent disasters, not milliseconds.

## 17. Common mistakes

DNS cutover with default TTL; incompatible migrations; flip without smoke; blue torn down immediately; sessions lost (sticky to color); one-off snowflake green.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `deploy_duration_seconds`, flip failures, blue/green traffic split

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Full E2E + load against green before flip; flip drill on staging; rollback drill timed; migration compatibility test (blue code on new schema); synthetic probes post-flip.

## 21. Deployment considerations

Automate through CI/CD: GitHub Actions (or equivalent) → image by digest → canary/rolling → smoke → auto-rollback on burn-rate alert. No manual steps in the critical path.

## 22. Production-readiness checklist

- [ ] Automated smoke gate before flip
- [ ] Flip via LB/selector not DNS
- [ ] Database expand/contract
- [ ] Bake window with auto-flip-back on alert
- [ ] Verify no config drift between colors (same image, same env shape)
- [ ] Keep blue during bake
- [ ] Connection draining
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Green works in smoke but breaks under 100% load (soak gap); DB migration not compatible with blue (rollback impossible — expand/contract needed); DNS flip too slow (TTL 300s of half-and-half traffic); shared cache/session poisoning between colors (cache version keys); warm-but-forgotten blue drifting (config rot if not redeployed); double capacity cost surprises; stateful connections reset on flip (drain via preStop).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://kubernetes.io/docs/concepts/workloads/controllers/deployment/

**Related topics in this library:** `#53 Canary Releases`, `#55 Rollbacks`, `#81 Database Migrations`, `#54 Rolling Deployments`, `#51 Feature Flags`.
