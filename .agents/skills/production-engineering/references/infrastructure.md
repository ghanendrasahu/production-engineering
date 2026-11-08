# Infrastructure & Build Reference

Pipelines, containers, orchestration, infrastructure-as-code, and dependency sanity — the build and run machinery of production software.

| # | Concept | One-line use case |
|---|---|---|
| 6 | CI/CD | Automated test → build → deploy pipeline |
| 7 | Docker | Reproducible runtime packaging |
| 8 | Kubernetes | Declarative container orchestration |
| 104 | Infrastructure as Code | Declarative, reviewed infrastructure |
| 105 | Terraform | Executable, versioned infra plans |
| 106 | Helm Charts | Parameterized Kubernetes packages |
| 107 | Build Caching | Fast, correct incremental builds |
| 108 | Dependency Hell | Resolvable, reproducible dependencies |

### 6. CI/CD

**Definition:** Continuous Integration (every push is tested and merged hot) + Continuous Delivery/Deployment (every green build is a releasable, automatically deployed artifact).

**Problem:** Big-bang integration and manual deploys are error-prone, slow, and unrepeatable — the deploy itself shouldn't be a ceremony.

**Internal Working:** Pipeline stages: lint → unit tests → build (immutable artifact tagged with commit SHA) → integration/contract tests → security scan (deps, SAST, secrets) → publish (registry) → deploy to staging → smoke tests → deploy to prod (canary/rolling). GitHub Actions OIDC for cloud auth (no static keys). Branch protection: PR must pass checks; environment protection rules (required reviewers) for prod.

**Architecture:** Git push → Actions runner → registry → staging env → prod env; deploy pipeline declared in repo (`.github/workflows/`).

**Implementation:**

```yaml
# .github/workflows/deploy.yml (excerpt)
on:
  push: { branches: [main] }
permissions: { id-token: write, contents: read }
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pipx run uv sync && uv run pytest -x
      - run: uv run ruff check . && uv run mypy src
  deploy:
    needs: test
    environment: production          # requires reviewers/approval
    steps:
      - uses: aws-actions/configure-aws-credentials@v4
        with: { role-to-assume: arn:aws:iam::123:role/gha-deploy, aws-region: us-east-1 }
      - run: helm upgrade --install app ./charts/app --values values-prod.yaml --atomic --timeout 10m
```

**Production Example:** 3 commits/day → each deploys in ~8 min (test 3m, build 1m, deploy 4m); rollback rate 1.5%; PRs can't merge without green; prod deploys auto after staging smoke passes; incident correlation via SHA in every metric.

**Failure Scenarios:** CI too slow (30min → devs skip it locally → breakage); no branch protection; deploy without staging; secrets in workflow YAML (OIDC instead); flaky tests tolerated (`continue-on-error` → rot); building per-environment (config drift — build once, promote); no deployment rollback automation; pipeline that passes but artifact broken (build/test drift — same interpreter everywhere, use containers).

**Best Practices:** Build once, promote everywhere; OIDC not keys; lock deps (uv.lock/package-lock); fast pipeline (<10min target); smoke tests post-deploy; artifact retention; cache dependencies; required reviewers on prod; SLSA provenance attestations; canary gate.

**Anti-Patterns:** `continue-on-error`; manual "deploy Friday" runbooks; building twice (staging build ≠ prod build); secrets echoed to logs; no lint/format gate; 40-minute pipelines.

**Trade-offs:** Performance (pipeline time vs safety); complexity (YAML + environments + approvals); cost (runner minutes — cache well); consistency (hermetic builds win); maintainability (pipeline as code, reviewed like code).

**Testing:** Pipeline on every PR; deliberate failing test → merge blocked; secrets scan blocks; staging smoke blocks prod; rollback drill via redeploy of previous SHA.

**Related Concepts:** `#7 Docker`, `#8 Kubernetes`, `#104 Infrastructure as Code`, `#107 Build Caching`, `#102 API Versioning`, `#55 Rollbacks`, `#53 Canary Releases`.

**Decision Criteria:** Use when: always — no production software without CI. Do not use when: n/a. Alternatives: n/a — the only choice is self-hosted vs SaaS runners and how much automation in delivery stage.

### 7. Docker

**Definition:** A packaging format and runtime for applications + dependencies as immutable, layered images that run identically on laptop, CI, and production.

**Problem:** "Works on my machine"; snowflake servers; unreproducible builds; unmanaged dependencies; deployment drift.

**Internal Working:** Image = ordered layers (each Dockerfile instruction = read-only diff layer; content-addressed by hash; shared cache). Union filesystem (overlay2) merges layers; container = layered image + writable top layer + isolated namespaces (pid/net/mnt/uts) + cgroups limits. Build context sent to daemon; multi-stage builds separate build deps from runtime; copy lockfiles first for cache; .dockerignore excludes junk. Registry stores images; tags mutable (use digests for immutability).

**Architecture:** Base image layered filesystem -> registry -> node runtime -> orchestrator. The image is the unit CI builds and K8s schedules; multi-stage builds split build deps from the runtime artifact.

**Implementation:**

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev
COPY src ./src

FROM python:3.12-slim
WORKDIR /app
RUN useradd -r app && mkdir -p /app
COPY --from=builder /app /app
USER app
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Compose for dev: `services: api: build: ., depends_on: [db, redis]`; healthchecks in compose.

**Production Example:** API image 140MB (slim + uv + multi-stage, was 1.2GB); build 45s (cache hit); runs as non-root UID 10001; read-only rootfs in K8s; digest-pinned deploy (`image@sha256:…`); CVE scan gate in CI (trivy) blocks on critical.

**Failure Scenarios:** Root containers; secrets baked via `COPY .env` (history shows it forever); cache misses (copy src before deps) — rebuild everything; giant images (apt lists, docs); :latest tags (untraceable); no .dockerignore (node_modules 800MB context); rootfs writable + curl exfiltration; missing healthcheck → orchestrator blind; zombie reaping (no init/tini for signals in N+1 signal handling — use tini or K8s handles SIGTERM directly).

**Best Practices:** Multi-stage builds; non-root USER; slim/distroless bases; digest pinning; .dockerignore; scan images (trivy) in CI; lockfiles copied before source; healthcheck in image; resource limits at runtime; read-only rootfs where possible; never secrets in layers.

**Anti-Patterns:** Fat images; `docker run --privileged` in prod; `.env` baked; root user; `apt-get update && install` in one layer (cache-hostile); "latest" everywhere; building on laptop for prod; running DBs in the same container as app.

**Trade-offs:** Performance (near-native; small startup overhead); complexity (low-moderate); cost (image storage, registry); consistency (excellent — identical everywhere); maintainability (declarative, reviewable).

**Testing:** Build in CI; smoke-run the image then hit /healthz; trivy gate; digest deploy verification; non-root assertion; docker-compose integration for dev parity (testcontainers in pytest).

**Related Concepts:** `#8 Kubernetes`, `#6 CI/CD`, `#106 Helm Charts`, `#107 Build Caching`, `#67 Secrets Management` (never in images), `#104 Infrastructure as Code`.

**Decision Criteria:** Use when: always — every deployable. Do not use when: truly trivial single-binary scripts deployed via scp (rare now). Alternatives: VM images (AMI — coarser), Nix, buildpacks (heroku) for convenience.

### 8. Kubernetes

**Definition:** A declarative container-orchestration platform: you describe desired state (Deployments, Services, ConfigMaps) and controllers continuously reconcile reality toward it.

**Problem:** Managing dozens/hundreds of containers by hand — scheduling, health, scaling, rollouts, service discovery — is untenable; K8s automates the control loop.

**Internal Working:** Control plane (API server, etcd, scheduler, controller-manager) + nodes (kubelet, kube-proxy, container runtime). You apply YAML; controllers reconcile: ReplicaSet maintains replica count; readiness/liveness probes gate traffic; Services give stable virtual IPs (ClusterIP) with EndpointSlices; HPA scales; Jobs/CronJobs run batch; namespaces isolate; RBAC/PSA secure; admission webhooks intercept config. Desired-state reconciliation means partial failure self-heals (node dies → pods rescheduled).

**Architecture:** Control plane (API server/etcd/scheduler/controllers) + worker nodes; you apply desired-state YAML, controllers reconcile; Services/EndpointSlices handle discovery; HPA and probes close the feedback loop.

**Implementation:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata: { name: api }
spec:
  replicas: 4
  strategy: { type: RollingUpdate, rollingUpdate: { maxSurge: 1, maxUnavailable: 0 } }
  selector: { matchLabels: { app: api } }
  template:
    metadata: { labels: { app: api } }
    spec:
      containers:
        - name: api
          image: registry.example.com/api@sha256:abc
          ports: [{ containerPort: 8000 }]
          resources: { requests: { cpu: 250m, memory: 256Mi }, limits: { memory: 512Mi } }
          startupProbe: { httpGet: { path: /healthz, port: 8000 }, failureThreshold: 30, periodSeconds: 5 }
          readinessProbe: { httpGet: { path: /readyz, port: 8000 }, periodSeconds: 5 }
          livenessProbe:  { httpGet: { path: /healthz, port: 8000 }, periodSeconds: 10 }
---
apiVersion: v1
kind: Service
metadata: { name: api-svc }
spec: { selector: { app: api }, ports: [{ port: 80, targetPort: 8000 }] }
```

**Production Example:** 12-service SaaS on EKS: HPA (CPU+custom metric lag) 2→30 pods; zero-downtime rolls with preStop drain + readiness; pod disruption budgets (minAvailable 60%); namespace RBAC; external-dns; cert-manager; 2 years without a hand-touched node.

**Failure Scenarios:** Resource requests unset → scheduler blind → OOM kills/noisy neighbors; liveness with DB check → restart cascades (see `#57`); image `:latest` (no traceability); no resource limits → node pressure; ConfigMap updated but pods not restarted (checksum annotation pattern); etcd backup never tested; single control-plane cluster (control plane outage = no deploys/reschedules but workloads keep running — learn this distinction); HPA flapping at threshold (enable stabilization windows); kubectl apply from laptops in prod.

**Best Practices:** Requests+limits always (Guaranteed QoS for critical); probes trio; digests not tags; PDB; namespaces + RBAC + PSA restricted; GitOps (ArgoCD/Flux) — no ad-hoc applies; resource quotas; network policies; etcd backup drill; monitoring the control plane itself; KEDA for queues; external-secrets; never expose dashboard publicly.

**Anti-Patterns:** Pets-as-cattle failure (SSH into pods to fix); monolith in one giant pod; `kubectl exec` as deployment strategy; no PDB; `:latest`; skipping staging parity; single-node "K8s" sold as prod.

**Trade-offs:** Performance (excellent, small overhead); complexity (high — the biggest infra learning curve; managed control plane mandatory unless huge); cost (cluster + nodes; over-requesting kills budget); consistency (declarative wins); maintainability (YAML sprawl — Helm/Kustomize + GitOps mandatory).

**Testing:** Kindest/kind dry-run; staging cluster parity; rollout drill (`rollout undo`); chaos (node kill); quota enforcement test; policy tests (conftest/kyverno).

**Related Concepts:** `#7 Docker`, `#106 Helm Charts`, `#104 Infrastructure as Code`, `#57 Liveness & Readiness Probes`, `#9 Service Discovery`, `#45 Autoscaling`, `#58 Monitoring`.

**Decision Criteria:** Use when: multiple services, team size to operate, or managed K8s (EKS/GKE/AKS) with platform support. Do not use when: one small app, one VM — Docker Compose or FaaS is correct (`agent` anti-enterprise-complexity rule). Alternatives: Docker Compose, Nomad, ECS, FaaS, fly.io, PaaS (Render/Heroku).

### 104. Infrastructure as Code

**Definition:** Describing infrastructure (networks, clusters, DBs, DNS, IAM) in declarative version-controlled code, applied by automation — reproducible, reviewable, auditable.

**Problem:** Console-clicked infrastructure drifts invisibly; disaster means re-deriving a config from someone's memory; audits are impossible; environments diverge.

**Internal Working:** Tools: Terraform/Pulumi (multi-cloud, declarative HCL/TS), CloudFormation/CDK (AWS), config-in-K8s itself. State (who owns what exists) lives in a remote backend (S3+DynamoDB lock); plan → review diff → apply; GitOps (ArgoCD) reconciles cluster state continuously. IaC applies to data-plane (K8s) via Helm/Kustomize and cloud via TF. Key shift: humans propose, pipeline applies; no console writes (immutable infra principle).

**Architecture:** Git repo (IaC source) -> CI plan/apply -> cloud provider APIs; remote state with locks; GitOps layer (ArgoCD/Flux) reconciles cluster state continuously; console writes forbidden (break glass only).

**Implementation:**

```
terraform init → terraform plan (shows diff) → PR review → terraform apply (CI)
GitOps: git push → ArgoCD syncs cluster within minutes, drift-alert on out-of-band changes
```

**Production Example:** Full AWS environment (VPC, EKS, RDS, Route53, IAM) from one repo; new region rebuilt from scratch in 50 minutes for DR drill; security group rules reviewed in PRs; zero console changes in 18 months (detected via drift alerts; 2 attempted emergencies reverted).

**Failure Scenarios:** State file leaked/corrupted (no remote backend lock → concurrent applies destroy state); `terraform destroy` against the wrong workspace; plan not reviewed (surprise destroy); secrets in .tf (use vault provider/SSM); console drift outpacing IaC; applying prod before staging; no lockfile (TF version skew); module sprawl with no standards.

**Best Practices:** Remote state + locking; workspaces per env (or dirs); plan-in-PR; apply only from CI; minimal console access (break glass); modules with pinned versions; policy as code (conftest/opa) for guardrails; secrets via data providers; regular drift detection; IaC for DNS/IAM too — not just compute.

**Anti-Patterns:** ClickOps; state in laptop; mutable shared accounts; `apply -auto-approve` from dev machines; unpinned modules from internet; ignoring plan output; snowflake "temporary" fixes via console that become permanent.

**Trade-offs:** Performance (n/a); complexity (learning HCL + state ops); cost (state backend ~free); consistency (exact reproducibility); maintainability (the single best ops discipline after version control).

**Testing:** Apply in isolated sandbox; `terraform validate`/`tflint`; conftest policies (no 0.0.0.0/0 ingress); drift alert drill; full-destroy-and-rebuild DR test quarterly; plan-diff PR review gate.

**Related Concepts:** `#105 Terraform`, `#106 Helm Charts`, `#6 CI/CD`, `#7 Docker`, `#83 Disaster Recovery`, `#67 Secrets Management`.

**Decision Criteria:** Use when: any infrastructure beyond a single VM — always. Do not use when: throwaway experiments (but graduate quickly). Alternatives: ClickOps (never), config management only (Ansible — good for OS config, weak on cloud APIs), Pulumi (real language).

### 105. Terraform

**Definition:** The dominant multi-cloud IaC tool: HCL-declared resources, a state file reconciling desired vs actual, and a plan/apply workflow.

**Problem:** Same as `#104` — but Terraform specifically because it spans AWS/GCP/Azure/K8s with one workflow and a huge provider ecosystem.

**Internal Working:** Providers expose resources as schemas; TF builds a dependency graph → parallelizes → computes diffs against state; backends (S3+DynamoDB or TFCloud) store state and lock it; workspaces isolate envs; modules encapsulate reusable sets ("vpc", "eks"); `terraform plan -out=tfplan` freezes the apply; drift = state vs reality divergence (use refresh + orphan detection). Safety: never `apply` unreviewed plan; `prevent_destroy` lifecycle for critical resources (DBs, buckets); `-replace` for surgical recreation.

**Architecture:** HCL source -> dependency graph -> provider plugins -> cloud APIs; state (who owns what) lives in a remote backend with locking; workspaces/dirs per environment; CI is the only writer.

**Implementation:**

```hcl
terraform { backend "s3" { bucket = "tf-state"; dynamodb_table = "tf-lock"; key = "prod/app.tf"; }
  required_version = ">= 1.6" }
resource "aws_db_instance" "main" {
  identifier = "app-prod"; engine = "postgres"; instance_class = "db.m6g.large"
  allocated_storage = 100; storage_encrypted = true; multi_az = true
  lifecycle { prevent_destroy = true } }
output "db_endpoint" { value = aws_db_instance.main.endpoint }
```

**Production Example:** 6 TF workspaces (3 apps × staging/prod); PR shows "2 to add, 1 to change"; DB instance protected with prevent_destroy; weekly drift scan (`terraform plan -detailed-exitcode`) alerts on out-of-band changes; new dev env spun up in 25 minutes from module.

**Failure Scenarios:** State lock not used → two applies interleave, corrupt state (mitigate: backend lock, one pipeline per workspace); plan apply skew (built hours ago); provider version float (lock .terraform.lock.hcl — commit it); secret in state (state contains DB passwords! encrypt bucket, restrict access); module from registry compromised supply chain (pin version + checksum); `-target` abused to skip deps → inconsistent apply; destroy on wrong workspace (name workspaces carefully, use dirs).

**Best Practices:** Remote state+lock; commit lock file; pin providers/modules; plan-in-PR; prevent_destroy on data stores; workspace per env; CI-only apply; encrypt+restrict state (it has secrets); import existing infra carefully; use `-out` files; policy checks (tflint/conftest) in CI; regular refresh; small modules.

**Anti-Patterns:** Laptop state; `terraform destroy` in prod workflows; unpinned providers/modules; state bucket public; console + TF both managing same resource; one 2,000-line main.tf; no state backups; committing secrets (use SSM/Vault data sources).

**Trade-offs:** Performance (graph parallelizes applies; big plans slow); complexity (state model + HCL); cost (free; Cloud paid tier optional); consistency (exact); maintainability (excellent with modules; poor without discipline).

**Testing:** `terraform validate`+`fmt` in pre-commit; tflint; conftest policies (deny public buckets); applies in ephemeral sandbox accounts; destroy-test in sandbox quarterly; state backup test; drift monitoring.

**Related Concepts:** `#104 Infrastructure as Code`, `#106 Helm Charts`, `#6 CI/CD`, `#67 Secrets Management`, `#83 Disaster Recovery`, `#108 Dependency Hell` (modules pinning).

**Decision Criteria:** Use when: cloud infra with any complexity — the default. Do not use when: K8s-only config (Helm/Kustomize better fit for cluster apps); team prefers Pulumi/CDK deliberately. Alternatives: CDK/Pulumi (general languages), Ansible (OS config), Crossplane (K8s-native IaC for cloud).

### 106. Helm Charts

**Definition:** Parameterized Kubernetes YAML packages (charts) with templates, default values, and release history — `helm install/upgrade/rollback` manages versioned application deployments.

**Problem:** Raw K8s YAML copy-pasted per environment diverges and is error-prone; Helm gives templating, values injection, dependency packaging, and rollback.

**Internal Working:** Chart = `Chart.yaml` + `values.yaml` + `templates/*.yaml` (Go templates with sprig functions); `values.yaml` overridden by `-f prod-values.yaml` / `--set`; releases tracked in a K8s Secret (sh.helm.release.v1) with revision history; `helm rollback chart 3` restores prior manifests; `helm template` renders locally for review; `helm upgrade --install --atomic` auto-rolls back on failure; charts from repos (Artifact Hub) or OCI registries.

**Architecture:** Chart (templates + values) -> `helm template` renders final manifests -> K8s API; release revisions stored as Secrets for audit and rollback; charts vendored in repo or pulled from an OCI registry.

**Implementation:**

```bash
helm create app && helm upgrade --install api ./charts/app -f values-prod.yaml \
  --namespace payments --atomic --timeout 5m --wait
helm template api ./charts/app -f values-prod.yaml > /tmp/rendered.yaml   # review diff
helm rollback api 41 --namespace payments
```

values-prod.yaml: `replicas: 6`, `image.tag: v2.4.1`, `resources.*`, `envFrom: secretRef`.

**Production Example:** One chart (Python FastAPI + sidecar + HPA + Service + Ingress + PDB + NetworkPolicy) deployed for 14 environments; values files per env; chart versioned independently (v1.9.0); rollback in 20s during a bad deploy; chart testing in CI with `helm template` + `kubectl --dry-run=server` + integration cluster.

**Failure Scenarios:** Untested template change renders invalid YAML in prod (CI must run `helm template` + validation); `--set` typo silently creating new empty value; values sprawl (500-line values-prod with duplication — use hierarchy and `tpl`); secrets in values committed to git (externalSecrets/sealed-secrets instead); chart upgrades across major versions breaking CRDs (`--atomic` mandatory); installing internet charts without review (supply chain); no resource limits in chart defaults.

**Best Practices:** `--atomic --wait` always; chart versioning + CHANGELOG; values hierarchy per env; lint (helm lint) in CI; render-and-diff in PRs; externalSecrets for creds; chart tests (template snapshot); pin chart deps; keep template logic minimal; release notes; never `--reuse-values` blindly.

**Anti-Patterns:** Raw YAML forks; secrets in values.yaml; charts as god-objects with 1000 flags; unreviewed public charts; `--force` as habit; no rollback practice; editing live objects then "helm save" drift.

**Trade-offs:** Performance (n/a); complexity (Go templating learning curve — use sparingly); cost (free); consistency (release history is audit); maintainability (great for fleets of similar services; painful without charts-as-code discipline).

**Testing:** `helm lint`; `helm template` snapshot tests; `helm unittest` plugin; kind-cluster smoke install in CI; rollback test; schema validation (values.schema.json); policy check (kyverno).

**Related Concepts:** `#7 Docker`, `#8 Kubernetes`, `#104 Infrastructure as Code`, `#105 Terraform`, `#6 CI/CD`, `#55 Rollbacks`.

**Decision Criteria:** Use when: repeated K8s deploys across services/envs — the default packaging. Do not use when: single-cluster single-app (raw manifests acceptable); someone proposes templating everything (use Kustomize instead of Helm's complexity). Alternatives: Kustomize (overlays, simpler), CDK8s, timoni, raw manifests, ArgoCD App-of-Apps.

### 107. Build Caching

**Definition:** Reusing prior compilation artifacts, dependency downloads, and layer results so builds take seconds instead of minutes — correctness-preserving, keyed by inputs.

**Problem:** 20-minute CI builds kill flow, delay feedback, and double infra cost; missing/incoherent caches often cause flaky rebuilds with stale artifacts.

**Internal Working:** Layers: package-manager cache (uv/pip/npm downloads), layer caching (Docker layer per Dockerfile instruction — copy lockfiles before source), remote build cache (GHA cache/registry layer cache (type=gha, type=registry), BuildKit; Turbo/Nx/Bazel for polyglot monorepos (task-graph hashing)), compiler caches (ccache/sccache). Correctness: cache keys must include all inputs that change the output (lockfile, source hash); cache invalidation on wrong inputs serves stale artifacts silently — prefer cache misses (slow but correct) to stale correctness.

**Architecture:** Build graph spans three tiers — manager cache (uv/pip/npm), layer cache (Docker/BuildKit), and monorepo task cache (Turbo/Nx/Bazel via input hashing). CI hits registry/GHA caches to short-circuit work.

**Implementation:**

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

**Production Example:** Monorepo 40 packages: BuildKit registry cache + GHA cache: image build 18min→2min cold / 20s warm; CI cost −70%; correctness preserved via cache keys bound to lockfile hashes and `uv sync --locked`.

**Failure Scenarios:** Stale artifacts from wrong cache key (missing source hash → old code shipped!); `COPY . .` before dependency install (busts cache every change); package cache poisoning (a bad wheel cached forever); cache-miss storm after fleet upgrade; registry cache auth expiry breaking all builds; caching `node_modules` across platforms (binary mismatch → runtime crashes); `--cache-from` with no fallback.

**Best Practices:** Lockfile-first copies; cache keys from lockfile+source hashes; registry cache in CI (gha mode=max); BuildKit everywhere; prune cache policy; measure hit rate; immutable artifacts by digest after build; never cache credentialed downloads into shared layers; periodic cache bust test (verify fresh output by disabling cache on a canary).

**Anti-Patterns:** Cache-key on branch name; `--no-cache` as norm ("it's flaky"); caching secrets/keys in layers; copying everything first; ignoring cache size growth; "works on my machine" caches.

**Trade-offs:** Performance (10-100x build speedups); complexity (key design discipline); cost (registry storage); consistency (keys must be exact — staleness is the risk); maintainability (BuildKit/GHA cache standard patterns).

**Testing:** CI job with cache disabled on schedule (verify green); hash-key audit; artifact provenance (digest) check; clean-room build from empty cache weekly; cache-hit metric in pipeline dashboard.

**Related Concepts:** `#6 CI/CD`, `#7 Docker`, `#103 Semantic Versioning`, `#108 Dependency Hell`, `#107 Build Caching` pairs with `#104 Infrastructure as Code`.

**Decision Criteria:** Use when: any build > 30s. Do not use when: trivially fast builds (no cache to hit). Alternatives: remote execution (Bazel RBE), prebuilt base images, monorepo task runners (Turbo/Nx), artifact registry promotion.

### 108. Dependency Hell

**Definition:** The accumulated failure modes of third-party dependencies: version conflicts, transitive breakage, unmaintained packages, supply-chain attacks, license incompatibility, and "works in CI, fails in prod" from environment drift.

**Problem:** Your service is the sum of dependencies you didn't write and don't fully understand; one bad release or unpinned transitive can halt the fleet (`left-pad`, event-stream, colors.js) — and slow silent rot.

**Internal Working:** Resolution: SAT/backtracking solvers (pip/poetry/uv/npm) pick versions satisfying constraints; conflicts when two packages want incompatible ranges. Defenses: lockfiles pin the full resolved graph (never `pip install` without pinning), SBOM (syft) for inventory, osv-scanner/pip-audit/dependabot for CVEs, license scanning (FOSSA), minimal dependencies policy (stdlib-first), vendored copies for critical paths, `pip-tools`/`uv pip compile` for bound-exact pins, virtualenv/poetry/uv isolation, one Python version per project (`requires-python`).

**Architecture:** Resolution happens at install time (lockfile -> exact graph); SBOM inventory flows from build to scanner to policy gate; private registry proxies act as a controlled choke point for supply-chain trust.

**Implementation:**

```bash
uv lock && uv sync --frozen          # exact, reproducible
pip-audit                            # CVEs
osv-scanner scan --recursive .
uv run pip check                     # dependency conflicts
npx npm-check-updates                # see upgrade candidates
```

SBOM in CI: `syft packages . -o cyclonedx-json`; diff SBOM per release.

**Production Example:** A transitive dep introduced a segfault on glibc 2.36 via wheel mismatch; caught in staging because lockfile+reproducible env matched prod exactly; root-caused via SBOM in 20 minutes; fix: bump one top-level pin; lesson: reproducibility > speed.

**Failure Scenarios:** Unpinned transitive → next CI run breaks (colors.js-style); `pip install pkg` directly in Dockerfile with no lockfile → untraceable runtime drift; CVE in abandoned package with no fix (fork/replace or drop); license: AGPL dependency in proprietary service; `^0.x` floating semantics re-interpreted; two packages requiring conflicting protobuf versions → import-time crashes; dependency confusion (private package name published to public registry — npm/pip pick public by default).

**Best Practices:** Lock everything (apps); ranges only in libraries; uv/poetry/npm ci in CI; dependabot + automerge for patches with CI green; osv-scanner gate on critical; SBOM per release; dependency budget review quarterly; pin base images by digest; private registry scope protection; license policy; remove unused deps (depcheck).

**Anti-Patterns:** `pip install -r requirements.txt` without pins; editing lockfiles by hand; ignoring patch CVEs for 6 months; dependabot automerge without tests; giant frameworks for "maybe" needs; no SBOM; force-upgrading everything in one PR.

**Trade-offs:** Performance (n/a mostly); complexity (lock discipline; resolution conflicts debugging); cost (scanning tools ~free OSS); consistency (locks = env parity); maintainability (the single highest-leverage hygiene practice in Python/Node shops).

**Testing:** `uv sync --frozen` in CI (byte-identical env); osv gate; license scan; conflict `pip check`; quarterly dep-audit report; clean-env repro of prod in staging.

**Related Concepts:** `#103 Semantic Versioning`, `#107 Build Caching`, `#6 CI/CD`, `#104 Infrastructure as Code`, `#109 Production Incidents` (supply-chain incidents), `#68 IAM` (least-privilege for registries).

**Decision Criteria:** Use when: every project — dependency discipline is mandatory. Do not use when: n/a. Alternatives: vendored minimal deps, Rust/Go single-binary builds reducing runtime deps, monorepo shared pins.

<!--END-->
