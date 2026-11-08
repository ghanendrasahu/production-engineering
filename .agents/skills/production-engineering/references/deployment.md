# Deployment Reference (Rollouts, Health, Release Strategies)

Covers topics 51-57: feature flags, blue-green, canary, rolling, rollbacks, health checks, liveness/readiness probes.

### 51. Feature Flags

**Definition:** A runtime switch (evaluated per user/context) that turns a code path on or off without redeploying; decouples *deploying* code from *releasing* behavior.

**Problem:** Releasing features means reverting code when something breaks; long-lived branches and big-bang releases are risky and slow. Flags let you ship continuously and control exposure separately.

**Internal Working:** Flag service/SDK evaluates rules (percentage rollout, allowlist, segment, env) at runtime; decisions stream to SDKs with low-latency evaluation (in-memory + poller or SSE/stream); flag state is config, not code. Types: release flags (deploy dark, enable gradually), ops flags (kill switch), experiment flags (A/B), permission flags (rollout by plan). Flag debt: each flag needs an owner, a removal date, and cleanup tickets — unmanaged flags rot into unmaintainable branching.

**Architecture:** App → flag SDK → flag service (Unleash/LaunchDarkly/config-in-DB) with fallback to cached defaults if the flag service is down (never fail the request path).

**Implementation:**

```python
import os, unleashclient  # or simple DB-backed table
def is_enabled(name: str, user_id: str) -> bool:
    bucket = int(hashlib.sha256(f"{name}:{user_id}".encode()).hexdigest(), 16) % 100
    row = cache.get(f"flag:{name}") or fetch_flag(name)   # default safe if missing
    if row["rollout_pct"] >= 100: return True
    if user_id in row["allowlist"]: return True
    return bucket < row["rollout_pct"]
```

**FastAPI Example:** Dependency `flags: FlagClient = Depends(get_flags)`; routes check `flags.enabled("new-checkout", user_id=user.id)`; flag changes stream in via polling every 10s; fall back to `False` (old path) on error.

**Production Example:** Checkout v2 shipped dark; enabled for 1% for 2 days (no anomaly), 25% for a week, 100%; at 80% a payment-error spike appeared; ops flag flipped to 0% in 20 seconds — zero deploy, zero rollback, incident avoided; code stayed deployed until fixed.

**Failure Scenarios:** Flag service down → all evaluations must have cached defaults (degraded, not dead); flag leak in error messages (incident reports say "flag new-checkout broke X" — fine internally, never to users); permission flags as security boundary used without server-side re-check; thousands of permanent flags making every code path branch — cleanup SLA essential; percentage rollout flapping (user sees feature then loses it) without sticky bucketing by user_id; flag + migration ordering mistakes (code expects schema rev N; flag on but migration not applied).

**Best Practices:** Sticky bucketing by user/tenant; server-side only for authz decisions; every flag has owner + expiry; flag audit log; kill switches for risky dependencies; default-off on missing config; flag-removal week each quarter; metrics split by flag cohort.

**Anti-Patterns:** Flags in client-side code for security decisions; permanent flags; branching every function on 6 flags; flags without metrics (no way to tell if rollout is healthy); using flags to paper over missing rollback capability; no flag hygiene policy.

**Trade-offs:** Performance (evaluation ~µs; streaming updates cheap); complexity (flag management + debt); cost (service licensing or modest infra); consistency (flag decision differs across instances during propagation — accept, or pin via user hashing); maintainability (worse with debt — enforce lifecycle).

**Testing:** pytest with flag override fixture (evaluate both paths); bucket distribution test (no skew); kill-switch drill (flip off mid-load, assert recovery); default-off test with flag service absent; E2E with flag on/off matrix.

**Related Concepts:** `#52 Blue-Green Deployment`, `#53 Canary Releases`, `#51 Feature Flags` pairs with `#55 Rollbacks`, `#63 SLOs` (rollout health), `#82 Schema Versioning` (expand/contract before flag flip).

**Decision Criteria:** Use when: continuous delivery, risky features, gradual migration, experimentation, kill switches. Do not use when: tiny one-off deploy (env var suffices). Alternatives: env config for static toggles, blue-green/canary for infrastructure-level switches.


### 52. Blue-Green Deployment

**Definition:** Two full production environments (blue = current, green = new); deploy to green, validate, then switch all traffic over; rollback = flip back.

**Problem:** Zero-downtime cutover with instant revert — the safest high-ceremony rollout for stateful or big changes where rolling can't validate before traffic shift.

**Internal Working:** Router (LB/DNS/service selector) points 100% of traffic at one environment; new build boots green behind the router with smoke tests; switch flips a selector (K8s Service selector change, weighted LB target switch, or blue/green ALB target groups) — DNS switching is slow (TTL) so prefer LB/selector flip; data-plane compatibility required: green code must run on the shared DB (expand/contract migrations). After bake time, old environment is kept warm for fast flip-back, then torn down.

**Architecture:** Two identical stacks behind one router; shared database; router holds the flip switch; deployment tooling (ArgoCD, pipeline, or manual) performs flip + verification.

**Implementation:**

```yaml
# K8s: two Deployments + one Service selector flipped atomically
kind: Service
spec: { selector: { version: blue } }   # flip to green: kubectl patch svc/app -p '{"spec":{"selector":{"version":"green"}}}'
```

```bash
aws elbv2 modify-listener --listener-arn $ARN --default-actions Type=forward,TargetGroupArn=$GREEN_TG
```

**Production Example:** Payment monolith v2.4 rebuilt; green boots, smoke suite passes (cert, DB rev, queue consumers), LB flips in 2 seconds; p95 identical; one anomalous error-budget burn 8 minutes later → flip back to blue instantly; zero user-facing downtime; postmortem: unknown env var in green — caught by smoke assertions added after.

**Failure Scenarios:** Green works in smoke but breaks under 100% load (soak gap); DB migration not compatible with blue (rollback impossible — expand/contract needed); DNS flip too slow (TTL 300s of half-and-half traffic); shared cache/session poisoning between colors (cache version keys); warm-but-forgotten blue drifting (config rot if not redeployed); double capacity cost surprises; stateful connections reset on flip (drain via preStop).

**Best Practices:** Automated smoke gate before flip; flip via LB/selector not DNS; database expand/contract; bake window with auto-flip-back on alert; verify no config drift between colors (same image, same env shape); keep blue during bake; connection draining; color-agnostic cache keys with version.

**Anti-Patterns:** DNS cutover with default TTL; incompatible migrations; flip without smoke; blue torn down immediately; sessions lost (sticky to color); one-off snowflake green.

**Trade-offs:** Performance (no degradation; double capacity during bake ~2x infra); complexity (true duplicate stacks); cost (double infra briefly); consistency (DB must serve both code versions); maintainability (pipeline-managed flip beats manual console).

**Testing:** Full E2E + load against green before flip; flip drill on staging; rollback drill timed; migration compatibility test (blue code on new schema); synthetic probes post-flip.

**Related Concepts:** `#53 Canary Releases`, `#55 Rollbacks`, `#81 Database Migrations`, `#54 Rolling Deployments`, `#51 Feature Flags`.

**Decision Criteria:** Use when: big/stateful releases needing rehearsed instant rollback; databases tolerate dual-version; capacity available. Do not use when: infra cost doubles unacceptably; frequent small deploys (rolling or canary cheaper); schema changes are destructive. Alternatives: rolling with surge, canary, flags + rolling.


### 53. Canary Releases

**Definition:** Route a small percentage of real traffic to the new version; watch metrics; ramp gradually; auto-rollback if SLIs degrade.

**Problem:** Blue-green shifts 100% at once — a subtle bug hits everyone; canary limits blast radius to 1-5% and catches what tests can't (load, data skew, provider behavior).

**Internal Working:** Traffic splitting at LB/service mesh (weighted targets: 95/5), progressive rollout (Flagger/Argo Rollouts: steps 10%→25%→50%→100% with analysis runs querying Prometheus for error rate/latency), analysis template with success criteria (e.g., `p99 < 300ms`, `5xx ratio < 0.1%`), automatic rollback on failure, automatic advance on success. Cohorts sticky by consistent hash on user-id/tenant.

**Architecture:** Deploy new ReplicaSet alongside old → mesh/LB splits by weight → analysis controller reads metrics → decides promote/abort.

**Implementation:**

```yaml
# Argo Rollouts canary step (excerpt)
strategy:
  canary:
    steps:
      - setWeight: 5
      - pause: { duration: 10m }
      - setWeight: 25
      - analysis:
          templates: [{ templateName: error-rate }]
      - setWeight: 50
      - pause: { duration: 10m }
```

Success criteria: `sum(rate(http_requests_total{status=~"5..",version="canary"}[5m])) / sum(rate(http_requests_total{version="canary"}[5m])) < 0.01`.

**FastAPI Example:** Version header `X-Release: canary` via middleware; metrics labeled `version="canary"`; dashboards comparing cohorts instantly; rollback = scale canary to zero / weight 0.

**Production Example:** Recommendation model v3: 2% traffic for 6h, p99 inference latency and click-through compared; canary error rate normal → ramped 10/25/50/100 over 2 days; bug in embed cache never reached >25% users; auto-analysis would have aborted otherwise.

**Failure Scenarios:** Metrics window too short to catch slow leaks (bake ≥ 10-15min per step); canary without representative users/traffic mix (only internal employees on canary → no signal); rollback not automated → human lag in incident; sticky sessions missing → user bounces between versions mid-flow (state mismatch); error budget burn by canary without auto-abort; flag/canary cache poisoning across cohorts; analysis query wrong (compares wrong denominators) → false abort or false promote.

**Best Practices:** Automated analysis + auto-rollback (never manual gates alone); sticky cohorts; 5-10min bake minimum; compare cohorts on latency/errors/business KPI; flags for behavior + canary for infra (belt and braces); metric labels with version everywhere; alert only if canary aborts.

**Anti-Patterns:** Manual-only ramp with no metrics gate; 1% for 1 minute "looks fine"; canary on non-representative path; no auto-rollback; cohorts unsticky; two canaries at once (attribution impossible).

**Trade-offs:** Performance (analysis adds orchestration complexity); complexity (mesh/rollouts + metrics quality — needs good SLIs first); cost (small extra replica pods); consistency (dual code paths must both tolerate schema — expand/contract again); maintainability (Argo/Flagger manageable; hand-rolled weight edits error-prone).

**Testing:** Analysis-abort drill (inject 5xx in canary pod → auto-rollback fires); sticky-bucket distribution test; promote-on-healthy E2E in staging; comparison dashboard sanity; rollback timing measurement.

**Related Concepts:** `#52 Blue-Green Deployment`, `#55 Rollbacks`, `#63 SLOs`, `#64 SLIs`, `#61 Metrics`, `#53 Canary Releases` needs `#66 Observability`.

**Decision Criteria:** Use when: production services with metrics maturity — most stateless services. Do not use when: no meaningful SLIs (build those first); single-instance systems; stateful migrations without expand/contract. Alternatives: blue-green, flags + rolling, dark launch (mirror traffic, no user impact).


### 54. Rolling Deployments

**Definition:** Gradually replace instances of the old version with the new, maintaining service availability throughout (maxSurge/maxUnavailable budgets).

**Problem:** The default, cheap zero-downtime rollout — but without limits, updates can exceed capacity headroom and cause outage during the roll itself.

**Internal Working:** K8s Deployment strategy ` RollingUpdate{maxSurge: 25%, maxUnavailable: 0}` (or 1): creates new pod, waits Ready (readiness probe), terminates old (preStop hook → SIGTERM → grace period), repeats. Readiness gates "ready to serve"; termination drains connections. Database compatibility required during the roll (both versions live). Rollouts paused on probe failure; `kubectl rollout undo` reverts to previous ReplicaSet.

**Architecture:** Deployment controller + ReplicaSets; LB health checks deregister unready/terminating pods.

**Implementation:**

```yaml
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate: { maxSurge: 1, maxUnavailable: 0 }
  template:
    spec:
      terminationGracePeriodSeconds: 45
      containers:
      - name: app
        lifecycle: { preStop: { exec: { command: ["sh","-c","sleep 10"] } } }   # stop endpoints, drain LB
```

**Production Example:** 8-replica API: maxSurge 2, maxUnavailable 0; deploy < 3 minutes; readiness = /readyz checks DB+Redis; preStop sleep 15s before SIGTERM; zero 5xx during roll; one bad pod failed readiness → roll paused, 4 pods still old but healthy; roll back with `rollout undo`.

**Failure Scenarios:** maxUnavailable too high → fleet capacity drops below demand → 503s; readiness too shallow (TCP check) → traffic hits not-yet-ready pods → errors; preStop missing → LB still routes to dying pods (connection refused); rollout of breaking migration mid-roll (old code on new schema) → exceptions; termination grace < in-flight request time → dropped requests; waiting for all pods to be old+new simultaneously impossible for stateful singletons.

**Best Practices:** maxUnavailable 0 when possible; readiness probes real (dependencies checked); preStop drain sleep; terminationGrace ≥ longest request; resource requests/limits set so surge pods fit the cluster; monitor rollout duration and post-roll error rate; `kubectl rollout undo` runbook; never skip probes for speed.

**Anti-Patterns:** 100% surge then kill-all (that's not rolling); readiness = liveness; no grace period; rolling with pending migration ordering; deploy without watching rollout; image tag `:latest`.

**Trade-offs:** Performance (zero capacity loss with surge; slower than blue-green); complexity (native K8s, minimal); cost (surge headroom); consistency (two versions transiently — expand/contract migrations); maintainability (built-in, no extra tooling).

**Testing:** Rollout dry-run (`--dry-run=server`); staging roll under load asserting zero errors; kill-a-pod-mid-roll drill; migration-compatibility smoke; rollback drill timing.

**Related Concepts:** `#57 Liveness & Readiness Probes`, `#55 Rollbacks`, `#52 Blue-Green Deployment`, `#53 Canary Releases`, `#81 Database Migrations`, `#54 Rolling Deployments`.

**Decision Criteria:** Use when: default for stateless services with capacity headroom. Do not use when: stateful/singleton workloads (use leader election + graceful handoff); breaking schema changes (expand/contract first); when you need instant full-switch semantics. Alternatives: canary, blue-green, recreate (some dev workloads).

### 55. Rollbacks

**Definition:** Reverting a deploy to the last known-good state promptly — the most important and most neglected production capability; a rollback you haven't rehearsed doesn't exist.

**Problem:** When production is on fire, the fastest fix is usually a revert; if rollback is manual archaeology, outages stretch for hours.

**Internal Working:** Artifact immutability (same image tag, same build — never rebuild for rollback) + fast traffic switch (`kubectl rollout undo`, ReplicaSet scale swap, LB target restore) + data compatibility (expand/contract means old code on new schema works). Database rollbacks: forward-fix usually beats down-migration; destructive contract migrations must ship days after code stops reading the column. Feature flags give a faster "rollback" of behavior without deploying anything.

**Architecture:** Deployment system + immutable artifact registry + database migration ledger + flag service; runbooks reference exact commands.

**Implementation:**

```bash
git tag v1.4.3 && git push --tags                    # immutable artifacts
kubectl rollout undo deploy/api --to-revision=12
kubectl rollout status deploy/api --timeout=180s
python -c "import urllib.request; print(urllib.request.urlopen('https://app/healthz').status)"
```

Flags: set rollout flag to 0% → done in seconds, no deploy.

**Production Example:** v2.6.1 checkout deploy error rate 4%; 5 minutes post-deploy canary auto-rollback already flipped traffic to v2.6.0; team confirmed p99 back to 150ms; RCA found bad cache-key change; fix deployed next morning behind canary.

**Failure Scenarios:** Rebuild-on-rollback (new bits, new bugs — always redeploy the exact prior artifact); stateful rollback forgetting migrations (old code vs new schema); config drift between environments making "revert" lossy; partial rollback (API rolled back, worker not); rollback untested → fails mid-incident (permissions, image GC'd from registry); DNS-based rollback at default TTL; rollback without monitoring confirmation ("reverted" but still degraded — verify!).

**Best Practices:** Immutable artifacts + registry retention ≥ 90 days; one-command rollback documented; rehearse monthly; canary/flags for behavior-level undo; verify post-rollback (health + business KPI), not just deploy success; keep previous ReplicaSet warm; never delete the last two image tags; rollback decision criteria pre-agreed (error budget burn).

**Anti-Patterns:** "Roll forward only" as ideology (sometimes right! but only with cheap deploys and great tests); rebuilding the artifact; down-migrations destructive in same release; no retention of old images; rollback runbooks owned by interns; confirming rollback by deploy logs alone.

**Trade-offs:** Performance (instant); complexity (pipeline maturity); cost (registry storage); consistency (needs schema compat); maintainability (discipline around immutable releases).

**Testing:** Monthly rollback drill: deploy vN, then `rollout undo`, time it, verify health; restore-from-backup drill as last resort; flag kill-switch drill; mid-incident simulation.

**Related Concepts:** `#53 Canary Releases`, `#51 Feature Flags`, `#52 Blue-Green Deployment`, `#81 Database Migrations`, `#63 SLOs`.

**Decision Criteria:** Use when: always designed-in. Do not use when: it doesn't fit (data-destructive release) — then expand/contract to make it fit. Alternatives: flags (fastest), canary auto-abort, blue-green flip, roll-forward fix.


### 56. Health Checks

**Definition:** An endpoint (`/healthz`) reporting whether the process can serve requests; consumed by load balancers, orchestrators, and monitoring to route traffic and restart unhealthy instances.

**Problem:** Without an honest health signal, traffic goes to dead or degraded instances; without a separable liveness/readiness split, orchestrators either restart healthy-but-busy pods or keep broken ones in rotation.

**Internal Working:** Cheap check by design: process is up, event loop responsive, optionally critical dependencies (DB, Redis) within a fast deadline. Liveness (is the process broken → restart it) vs readiness (can it serve → route or not). Deep checks (all dependencies) in liveness cause restart storms when the DB blips — dependencies belong in readiness or a separate status page. Health responses include version and uptime for debugging.

**Architecture:** Service exposes `/healthz` (+ `/readyz`); LB/K8s probe it; monitoring scrapes it; responses must be cheap (< 50ms, no heavy queries).

**Implementation:**

```python
@app.get("/healthz")
def healthz():
    return {"status": "ok", "version": __version__, "uptime": int(time.monotonic() - START)}

@app.get("/readyz")
def readyz():
    try:
        engine.connect().execute(text("SELECT 1")).close()
    except Exception:
        raise HTTPException(503, "database not reachable")
    return {"status": "ready"}
```

K8s: `startupProbe` for slow boot (model loading), then liveness/readiness.

**Production Example:** K8s API pods: startupProbe 60s allowance for model load; readiness hits DB+Redis with 1s timeout; liveness = process-only; an DB failover removed all pods from rotation cleanly (503 at gateway, zero phantom traffic to dead-backends); recovered when DB returned.

**Failure Scenarios:** Liveness checking DB → DB outage triggers every pod restart simultaneously → total outage minutes after DB recovers (connection storm); readiness always-200 → traffic to broken pods; healthcheck too expensive (full query) → probe itself overloads DB; no startup probe → slow-boot pods killed in restart loop; healthcheck exposed publicly leaking version/internal state; health endpoint = only route not behind LB (bypasses auth but leaks info — keep it minimal).

**Best Practices:** Liveness = process-only; readiness = real dependencies with short deadline; startupProbe for slow init; `/healthz` excluded from auth but minimal; cheap payload; include build version; alert on readyz flap; separate deep diagnostics endpoint for ops (auth'd).

**Anti-Patterns:** Deep checks in liveness; readiness always OK; expensive health queries; health info leak; probe intervals too tight (CPU noise).

**Trade-offs:** Performance (negligible if cheap); complexity (trivial); cost (free); consistency (n/a); maintainability (one tiny endpoint, mandatory).

**Testing:** Kill DB → readyz 503 → pod out of rotation → traffic zero 5xx (from LB); pod SIGSTOP → liveness fails → restart; startupProbe test with artificial boot delay; verify no DB queries in liveness path.

**Related Concepts:** `#57 Liveness & Readiness Probes`, `#3 Load Balancing`, `#45 Autoscaling`, `#55 Rollbacks`, `#58 Monitoring`.

**Decision Criteria:** Use when: always — mandatory for any deployable service. Do not use when: n/a. Alternatives: n/a (it's the contract with the platform).


### 57. Liveness & Readiness Probes

**Definition:** Kubernetes (or LB) mechanisms distinguishing **liveness** — is the process dead/hung (restart it) — from **readiness** — can it serve traffic right now (include/exclude from endpoints).

**Problem:** Without probes, orchestrators send traffic to unready pods and keep zombie pods in rotation; with misdesigned probes, they restart healthy-but-busy pods and cascade outages.

**Internal Working:** kubelet probes: `httpGet`, `tcpSocket`, `exec` with `periodSeconds`, `timeoutSeconds`, `failureThreshold`, `initialDelaySeconds` (legacy) or `startupProbe` (preferred for slow boots — liveness suppressed until startup succeeds). Readiness failure → pod removed from EndpointSlice (no restart). Liveness failure → container restarted (with backoff via restartPolicy). Combination yields: startup → readiness gates traffic → liveness restarts hung apps.

**Architecture:** kubelet → probe endpoint; endpoints controller updates Service EndpointSlices; LB/ingress chase those.

**Implementation:**

```yaml
startupProbe:
  httpGet: { path: /healthz, port: 8000 }
  periodSeconds: 5; failureThreshold: 30      # up to 150s to boot (LLM models)
livenessProbe:
  httpGet: { path: /healthz, port: 8000 }
  periodSeconds: 10; timeoutSeconds: 2; failureThreshold: 3   # restart after 30s hung
readinessProbe:
  httpGet: { path: /readyz, port: 8000 }
  periodSeconds: 5; timeoutSeconds: 1; failureThreshold: 2    # 10s out of rotation
```

**Production Example:** Embedding API (4GB model load): startupProbe failureThreshold 40 (200s budget); before this, liveness killed pods every 60s mid-load → crash loop; after, clean rollout in 4 minutes.

**Failure Scenarios:** Same endpoint for both probes with deep checks → liveness death spiral during DB blip; initialDelay too short for JVM/model load; timeout > period (overlap); failureThreshold 1 (one slow probe restarts healthy pod); exec probes spawning shells too heavy; probe logs filling disk (period 1s logging).

**Best Practices:** startupProbe absorbs slow boot; liveness = cheap process check only (never dependencies); readiness = real readiness with 1s deadline; thresholds ≥ 3 failures; probes cheap enough to run every 5-10s; probe endpoints logged at debug level; align LB idle timeout with readiness.

**Anti-Patterns:** Liveness = readiness = `/healthz` with DB check; no startupProbe; period 1s; exec probes with heavy scripts; probes behind auth.

**Trade-offs:** Performance (probe overhead if not cheap); complexity (3 probes to tune); cost (free); consistency (n/a); maintainability (declarative YAML, reviewed like code).

**Testing:** SIGSTOP a pod → liveness restarts it; DB down → readyz out-of-rotation (not restart); artificial slow boot → startupProbe protects; rollout drill verifying traffic never hits unready pods (load test during deploy).

**Related Concepts:** `#56 Health Checks`, `#54 Rolling Deployments`, `#45 Autoscaling`, `#85 Failover`, `#11 Timeouts`.

**Decision Criteria:** Use when: always in K8s (and analogs in LB-based deploys). Do not use when: trivial one-shot containers (jobs). Alternatives: `exec` probes, gRPC health checking protocol, LB target group health checks.

