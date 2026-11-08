---
topic: 80
title: SSRF
category: D
skill: production-engineering
status: stable
---

# 080 — SSRF

## 1. Topic name and metadata

- **Number:** 80 of 111
- **Title:** SSRF
- **Category:** D — Security Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [security-engineering.md](../references/security.md)
- **Topic file:** `.agents/skills/production-engineering/topics/080-ssrf.md`

## 2. What it is

Server-Side Request Forgery — tricking the server into making HTTP requests to destinations of the attacker's choosing: cloud metadata endpoints (169.254.169.254), internal services, or arbitrary external hosts.

## 3. Why it exists

Server-side fetches of user URLs reach networks users cannot.

## 4. The engineering problem it solves

The server is on the trusted side of the firewall; SSRF turns your app into an open proxy into your private network — the Capital One breach ($190M) was SSRF → metadata credentials → S3 exfiltration.

## 5. How it works internally

Any feature fetching a URL from user input: webhooks, image proxies, link previews, PDF renderers, "import from URL". Attacker supplies `http://169.254.169.254/latest/meta-data/iam/security-credentials/` or `http://localhost:6379/` or `gopher://…` to hit Redis. Defenses: **allowlist** of scheme (https) and host patterns; resolve DNS and check the resolved IP is routable public (not RFC1918/loopback/link-local) — including after redirects; block metadata IPs explicitly (cloud IRSa disables IMDSv1; use IMDSv2); network egress rules (app cannot reach 169.254.169.254); disable redirects or re-validate each hop; response size/time limits; don't return body contents to the attacker.

## 6. Architecture and design principles

App layer + egress proxy (allowlist enforced) + IMDSv2 + private DNS zoning. Webhook senders sit behind an egress allowlist.

**Design principles for this category:** Deny by default; least privilege; defense in depth — no single control carries the weight; shift security left into CI.

## 7. When to use it

Any server-side URL fetch from user input — always apply.

## 8. When NOT to use it

No user-controlled URLs exist (don't over-engineer).

**Alternatives:** fully client-side fetching (browser does it, server never sees URL), dedicated isolated fetch service with locked egress, HEAD-only pre-validation.

<!--END-->

## 9. Implementation strategies

```python
ALLOWED_SCHEMES = {"https"}
def safe_fetch(url: str):
    p = urlparse(url)
    assert p.scheme in ALLOWED_SCHEMES
    ips = getaddrinfo(p.hostname, None)   # resolve and check every IP
    for fam, _, _, _, (ip, *_) in ips:
        assert not ipaddress.ip_address(ip).is_private and ip != "169.254.169.254"
    return httpx.get(url, follow_redirects=False, timeout=5.0)  # validate each redirect too
```

Cloud: IMDSv2 required (token-based, defeats SSRF → metadata); security group on app tier denying egress to metadata ranges; egress via proxy with domain allowlist for webhooks.

## 10. Production-grade implementation

**Scenario:** Link-preview microservice: egress proxy with allowlist of http(s) to non-private ranges + IMDSv2 on EC2 + response-body cap 128KB; a researcher's `169.254.169.254` test fails at the proxy and at name resolution; disclosed privately, bounty paid, zero data exposure.

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

Webhook sender resolves + validates IP before POST, forbids redirects (or validates each hop), caps response read to 64KB, logs target host; "fetch preview" feature uses a headless browser in a locked-down sandbox with no network beyond allowlist.

## 13. Distributed-system considerations

Security is global: identity, secrets, and policy must be consistent everywhere the workload runs — one unpatched region or sidecar undoes the rest.

## 14. AI/ML/LLM application examples where relevant

Agents with fetch_url tools = SSRF — allowlist hosts; resolve-then-check IPs; block 169.254.169.254.

## 15. Security considerations

Scheme+host allowlist; resolve and verify IPs (not private); egress proxy + IMDSv2.

## 16. Performance considerations

TLS + auth cost ~1-10 ms per request — amortized by keepalive and token caching; never skip payment for security 'perf' reasons without measuring.

## 17. Common mistakes

Blacklist of bad hosts; validating hostname strings only; following redirects blindly; returning internal fetch errors/bodies to attacker; allowing any protocol (`file://`, `gopher://`, `dict://`); cloud instances with IMDSv1.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `ssrf_blocked_total`, egress-proxy denials

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Point SSRF test suite at app: `http://169.254.169.254/`, `http://127.0.0.1:22`, `http://[::1]/`, decimal/hex IP encodings, DNS-rebinding service (rebind.network) in staging; assert 400/403; webhook redrive drill; egress firewall rule tests in CI.

## 21. Deployment considerations

Treat every change to auth/secrets/TLS as security-sensitive: staged rollout, monitoring on rejection rates, and a documented rollback that also rotates anything exposed.

## 22. Production-readiness checklist

- [ ] Allowlist scheme+host
- [ ] Resolve and verify IP at connect time (not just validation time)
- [ ] Block link-local/loopback/RFC1918/metadata IPs always
- [ ] No user-controlled raw URLs without proxy
- [ ] IMDSv2
- [ ] Egress proxy for webhooks
- [ ] Cap response size/time
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Validating the URL string before DNS resolution (DNS rebinding TOCTOU — attacker DNS returns public IP first, private on re-resolve); following redirects without re-validation; IPv6 `::1`/`::ffff:127.0.0.1` bypass; `0.0.0.0` and `2130706433` (decimal encoding of 127.0.0.1) bypass; blocking list but not allowlist (unknown encodings slip); returning internal error pages/bodies to users; webhook to `file://`/`gopher://`; open redirect in target used as single-hop SSRF.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://owasp.org/www-community/attacks/Server_Side_Request_Forgery

**Related topics in this library:** `#71 TLS`, `#67 Secrets Management` (metadata creds are the prize), `#68 IAM` (role scoping limits blast radius), `#74 WAF`, `#80 SSRF` motivates `#5 API Gateways` egress controls.
