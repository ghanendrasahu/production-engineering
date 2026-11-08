---
topic: 87
title: Chaos Engineering
category: F
skill: production-engineering
status: stable
---

# 087 — Chaos Engineering

## 1. Topic name and metadata

- **Number:** 87 of 111
- **Title:** Chaos Engineering
- **Category:** F — Disaster Recovery and Reliability
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [reliability-recovery.md](../references/reliability.md)
- **Topic file:** `.agents/skills/production-engineering/topics/087-chaos-engineering.md`

## 2. What it is

The discipline of injecting controlled failures (kill instances, delay networks, fill disks, corrupt caches) into systems to discover weaknesses before they cause incidents, under observation with a clear hypothesis.

## 3. Why it exists

Untested resilience claims are theory, not resilience.

## 4. The engineering problem it solves

Untested resilience claims are theory; the first time your failover logic runs under real stress may not be during your drill — it's usually during your worst outage.

## 5. How it works internally

Scientific method: hypothesis ("if AZ-1 DB replica dies, writes continue with < 10s impact") → blast radius control (start with one staging instance, synthetic traffic) → steady-state metrics → inject (kill, partition, latency, CPU, error injection, dependency outage) → observe → fix → repeat in production with guardrails (abort on SLO breach). Tools: Chaos Mesh (K8s), LitmusChaos, AWS FIS, Gremlin, steady-state via Prometheus. Start small, narrow, rehearsed — not "delete prod".

## 6. Architecture and design principles

Chaos controller (Chaos Mesh/Litmus/AWS FIS) -> injects into targeted pods/zones -> steady-state metrics watched on dashboards -> auto-abort on SLO breach; experiments defined as versioned manifests in Git.

**Design principles for this category:** Assume failure; test recovery, not just uptime; the cheapest reliability is the one rehearsed before it is needed.

## 7. When to use it

Production systems serving real users where unexpected failure is unaffordable (so most systems).

## 8. When NOT to use it

Staging doesn't exist; system unobservable (no metrics — fix that first); team forbidden to touch prod.

**Alternatives:** failover drills only, disaster recovery tabletop exercises, simulation testing (Jepsen-style).

## 9. Implementation strategies

```yaml
# Chaos Mesh pod kill (excerpt)
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata: { name: kill-api-pod }
spec: { action: pod-kill, mode: one, selector: { namespaces: [prod], labelSelectors: {app: api} }, duration: "5m" }
```

```bash
# aws fis or litmusctl run experiment <id>  — then watch dashboards, abort on SLO breach
```

## 10. Production-grade implementation

**Scenario:** Quarterly game day: kill the primary Redis mid-cache-refresh and the team discovered the app had no fallback — cold cache + no stampede protection → 40% error rate; fixed with lock + stale-while-revalidate; next drill: clean recovery in 20s.

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

DR is inherently distributed: replication links, region failover, and cross-region consistency decide whether your 'HA' survives the disaster or just survives the drill.

## 14. AI/ML/LLM application examples where relevant

Chaos on the provider path: kill the provider in staging — does the fallback chain actually work? Verify TTFT SLO.

## 15. Security considerations

Chaos must not weaken auth to 'see' failures — inject around, not through controls.

## 16. Performance considerations

Failover/DR add replication RTT (sync) or a lag window (async) — choose per data class, not globally.

## 17. Common mistakes

Chaos without monitoring/abort; "delete a random prod host" (unplanned blast); chaos to prove smartness rather than find bugs; never re-testing the same failure; chaos instead of fixing known weaknesses; skipping the human comms plan.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `chaos_experiments_total`, steady-state violations per experiment

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

The practice itself is the test; verify abort switches work; staging-first protocol; game-day scorecard tracked over quarters (mean time to detect, mean time to recover).

## 21. Deployment considerations

DR/failover changes must be rehearsed: quarterly game days with measured RTO/RPO; record results; update the runbook after every rehearsal.

## 22. Production-readiness checklist

- [ ] Hypothesis + steady state required
- [ ] Narrow blast radius first (single pod, staging, then prod canary)
- [ ] Abort on SLO breach
- [ ] One variable at a time
- [ ] Fix findings and re-run
- [ ] Game days quarterly
- [ ] Include dependency third-parties (fake their outages)
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Blast radius unbounded (experiment in prod without caps) → actual outage caused by "chaos"; hypothesis absent (random destruction, learned nothing); SLO breach ignored (drill became real incident — set automatic abort); fixing nothing afterward (drill theater); injecting during peak without warning; blaming people not systems; "chaos" as substitute for missing retries/timeouts.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://en.wikipedia.org/wiki/Chaos_engineering
- https://chaosmesh.org/docs/

**Related topics in this library:** `#83 Disaster Recovery`, `#85 Failover`, `#10 Circuit Breakers`, `#95 Network Partitions`, `#109 Production Incidents`, `#111 Postmortems`.
