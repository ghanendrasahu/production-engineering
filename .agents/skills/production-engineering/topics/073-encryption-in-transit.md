---
topic: 73
title: Encryption in Transit
category: D
skill: production-engineering
status: stable
---

# 073 — Encryption in Transit

## 1. Topic name and metadata

- **Number:** 73 of 111
- **Title:** Encryption in Transit
- **Category:** D — Security Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [security-engineering.md](../references/security.md)
- **Topic file:** `.agents/skills/production-engineering/topics/073-encryption-in-transit.md`

## 2. What it is

Encrypting data while it moves between systems (TLS, SSH, VPN, mTLS) so network observers and on-path attackers see ciphertext.

## 3. Why it exists

Networks between services are hostile by default.

## 4. The engineering problem it solves

Unencrypted east-west traffic inside a "trusted" network is readable by anyone who gains a foothold or misconfigured route — internal networks are compromised constantly; zero-trust demands encryption everywhere.

## 5. How it works internally

TLS (`#71`) between clients, LB, and origins; mTLS (both parties present certs — SPIFFE/SPIRE, service mesh Envoy/Istio) inside the cluster; SSH tunnels for admin; WireGuard/VPN between sites; private links (AWS PrivateLink) to keep traffic off the public internet; cert-manager issues/rotates internal certs. Encryption ≠ authorization — still authenticate each peer.

## 6. Architecture and design principles

External TLS at edge; internal mTLS via mesh or per-service cert-manager; DB connections with `sslmode=verify-full`; never trust VPC = safe.

**Design principles for this category:** Deny by default; least privilege; defense in depth — no single control carries the weight; shift security left into CI.

## 7. When to use it

Always — including inside the cluster.

## 8. When NOT to use it

N/a.

**Alternatives:** n/a (this is the transport baseline); for special cases, HPKE for end-to-end payload encryption beyond TLS hops.

## 9. Implementation strategies

```ini
# Postgres: require TLS from all clients
require_secure_transport = on   # or pg_hba.conf: hostssl all all 0.0.0.0/0 scram-sha-256
```

```python
ssl_ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile="ca.pem")
ssl_ctx.check_hostname = True; ssl_ctx.verify_mode = ssl.CERT_REQUIRED
async with httpx.AsyncClient(verify=ssl_ctx, timeout=5.0) as c: ...
```

Istio PeerAuthentication STRICT → plaintext refused cluster-wide.

## 10. Production-grade implementation

**Scenario:** Payment service mesh: ingress → API (edge TLS); all service-to-service calls mTLS; DB with `sslmode=verify-full`; cert-manager auto-rotates every 30 days; an internal sniffing test captures only ciphertext.

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

Internal inference RPC over mTLS — model outputs are internal secrets until filtered.

## 15. Security considerations

mTLS with identity per peer — not just encryption: SPIFFE/SPIRE or mesh strict mode.

## 16. Performance considerations

TLS + auth cost ~1-10 ms per request — amortized by keepalive and token caching; never skip payment for security 'perf' reasons without measuring.

## 17. Common mistakes

Plaintext internal DB links; verify-none in clients; long-lived internal certs; optional encryption ("PERMISSIVE") everywhere; secrets in URLs over "internal" HTTP.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `mtls_handshake_failures_total`, plaintext-egress probes

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Sniffer test in staging; sslmode verification test to DB (attempt without CA → refuse); cert-expiry alerts internal; mesh strict-mode rollout canary; plaintext port probe (nc) fails.

## 21. Deployment considerations

Treat every change to auth/secrets/TLS as security-sensitive: staged rollout, monitoring on rejection rates, and a documented rollback that also rotates anything exposed.

## 22. Production-readiness checklist

- [ ] TLS 1.2+ everywhere
- [ ] MTLS east-west
- [ ] `verify-full` for DBs
- [ ] Rotate internal certs automatically
- [ ] Mesh strict mode
- [ ] Encrypt backups too
- [ ] Monitor cert expiry internally
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Internal plaintext "because VPC"; `sslmode=require` without CA verification (MITM possible); cert rotation breaks a service not reloaded; mesh in PERMISSIVE mode (half-unencrypted forever); internal CA compromised — rotate all; app bug logging full URLs with tokens to stdout captured by log shippers.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://www.rfc-editor.org/rfc/rfc8446
- https://spiffe.io/docs/

**Related topics in this library:** `#71 TLS`, `#72 Encryption at Rest`, `#69 OAuth`, `#74 WAF`, `#67 Secrets Management`.
