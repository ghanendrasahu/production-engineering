---
topic: 75
title: DDoS Protection
category: D
skill: production-engineering
status: stable
---

# 075 — DDoS Protection

## 1. Topic name and metadata

- **Number:** 75 of 111
- **Title:** DDoS Protection
- **Category:** D — Security Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [security-engineering.md](../references/security.md)
- **Topic file:** `.agents/skills/production-engineering/topics/075-ddos-protection.md`

## 2. What it is

Defenses against denial-of-service attacks — volumetric (flood bandwidth), protocol (SYN floods), and application-layer (expensive query floods) — absorbing or filtering hostile traffic before it exhausts capacity.

## 3. Why it exists

Volumetric attacks exhaust everything before your code runs.

## 4. The engineering problem it solves

A saturated origin serves zero legitimate users; bandwidth exhaustion costs money and reputation; app-layer floods can take down expensive endpoints (search, LLM) cheaply.

## 5. How it works internally

CDN anycast absorption (huge network capacity, spread globally), L3/L4 scrubbing (SYN cookies, rate limiting by source ASN), L7 WAF rules (per-IP rate, bot detection, challenge pages/CAPTCHA), SYN cookies mitigate SYN floods (stateless handshake), connection limits, caching absorbs hot endpoints, origin shielded by CDN (only CDN IPs allowed in security group). Cost of the attack to the attacker raised (anycast = flood hits globally distributed points) — this is why cloud CDNs dominate DDoS mitigation.

## 6. Architecture and design principles

CDN → WAF → LB → origin (deny direct origin access); scrubbing centers; provider on-call with runbooks.

**Design principles for this category:** Deny by default; least privilege; defense in depth — no single control carries the weight; shift security left into CI.

## 7. When to use it

Always behind a CDN with L3/L4 protection — baseline.

## 8. When NOT to use it

N/a (it comes with the CDN).

**Alternatives:** provider-managed (Cloudflare/Akamai/AWS Shield) — never hand-rolled for volumetric.

## 9. Implementation strategies

```nginx
# last-mile defense at Nginx (in addition to CDN)
limit_req_zone $binary_remote_addr zone=one:10m rate=10r/s;
limit_conn_zone $binary_remote_addr zone=addr:10m;
limit_req zone=one burst=20 nodelay; limit_conn addr 20;
```

AWS Shield Standard (free, L3/L4) + Shield Advanced (DDoS response team + cost protection); Cloudflare Magic Transit for L3.

## 10. Production-grade implementation

**Scenario:** 50 Gbps UDP flood + app-layer 30k req/s to `/search?q=random`; anycast absorbed UDP invisibly; L7 rule challenged with JS bot detection; origin load unchanged; cost spike only in WAF request fees; 2 hours, no downtime.

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

Security is global: identity, secrets, and policy must be consistent everywhere the workload runs — one unpatched region or sidecar undoes the rest.

## 14. AI/ML/LLM application examples where relevant

LLM endpoints are expensive-request DDoS magnets — strict global + per-tenant rate limits and cost budgets.

## 15. Security considerations

Edge absorb, L7 challenge, cache hot paths; origin reachable only via CDN IPs.

## 16. Performance considerations

TLS + auth cost ~1-10 ms per request — amortized by keepalive and token caching; never skip payment for security 'perf' reasons without measuring.

## 17. Common mistakes

nginx limit_req as the only "DDoS protection" (per-IP useless vs botnet); no caching for public hot content; origin IP exposed in DNS history; scaling up to absorb (pay attacker's bill); blocking by country as general policy (collateral damage).

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `ddos_bytes_absorbed`, L7 challenge rate, origin bandwidth saved

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Origin-bypass scan (nmap direct IP — must not serve); cache hit-rate assertions on expensive routes; WAF challenge synthetic test; monthly provider status review; runbook tabletop exercise.

## 21. Deployment considerations

Treat every change to auth/secrets/TLS as security-sensitive: staged rollout, monitoring on rejection rates, and a documented rollback that also rotates anything exposed.

## 22. Production-readiness checklist

- [ ] CDN in front always
- [ ] Origin SG locked to CDN IPs
- [ ] Cache expensive public endpoints
- [ ] Challenge/CAPTCHA for bot patterns
- [ ] Anycast provider with proven capacity
- [ ] Runbook + provider hotline
- [ ] Cost guardrails
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Direct-IP origin reachable (bypass of entire CDN defense — the #1 DDoS failure); WAF rules per-IP useless vs botnets (10k IPs) without ASN/fingerprint signals; cache stampede because TTL expired during attack; TLS negotiation floods (compute at edge? CDN does crypto offloading); failover site unsecured (DDoS follows to disaster site); alerting drowned by attack noise (tune thresholds).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://developers.cloudflare.com/ddos-protection/
- https://aws.amazon.com/shield/

**Related topics in this library:** `#74 WAF`, `#48 CDN`, `#4 Reverse Proxies`, `#1 Rate Limiting`, `#49 Edge Caching`, `#75 DDoS Protection` layers on `#3 Load Balancing`.
