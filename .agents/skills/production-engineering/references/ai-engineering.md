# AI Engineering Reference — Production LLM & Agent Systems

How the 111 concepts apply to LLM applications: RAG, inference APIs, streaming, agents, vector infrastructure, embeddings, GPU capacity, cost control, reliability, and observability — with concrete FastAPI + Redis + PostgreSQL patterns.

**Rule zero:** an LLM is a slow, expensive, nondeterministic, rate-limited, occasionally wrong dependency — every pattern below applies the same reliability thinking you'd apply to a third-party payment API.

---

## 1. Production RAG Systems

**Pipeline:** ingest (parse → chunk → embed → index) → retrieve (hybrid: dense ANN + BM25) → rerank (cross-encoder) → generate (grounded prompt with citations) → evaluate.

**Failure modes to engineer for:** retrieval miss (answer absent → should say "I don't know"), stale indexes (re-embed on document change, not on a schedule), chunk-boundary truncation (overlap + parent-child retrieval), embedding drift (model version change requires full re-index — version the embedding model in the index name: `docs_e5mistral_v3`), prompt injection from retrieved docs (never give the model tools on raw retrieved content without sandboxing; treat retrieved text as data, never as instruction), citation hallucination (validate each cited chunk exists in the retrieved set).

**Architecture blueprint:** API (FastAPI) → query service → embedding client (batch, cached) → vector DB (pgvector for ≤10M vectors; Qdrant/Weaviate beyond) → reranker (cross-encoder, e.g. bge-reranker) → LLM provider (with fallback) → response with `sources: [{doc_id, chunk_id, score}]`. Index updates via outbox/CDC from the source-of-truth DB.

**Minimal FastAPI sketch:**

```python
@app.post("/rag/query")
async def rag_query(q: Query):
    key = hashlib.sha256(q.text.encode()).hexdigest()
    if hit := redis.get(f"rag:{key}"): return json.loads(hit)   # exact cache
    vec = await embedder.embed(q.text)                          # cached client
    hits = await vectordb.search(vec, top_k=20)
    hits = rerank(q.text, hits)[:5]
    ans = await llm.complete(build_prompt(q.text, hits), idempotency_key=key)
    redis.setex(f"rag:{key}", 3600, json.dumps(ans))
    return ans
```

**Control list:** rate limit per tenant (`#1`), idempotency keys for billable calls (`#14`), timeouts on embedder and LLM (`#11`), retries with jitter only on 5xx/429 (`#12 #13`), DLQ for failed index jobs (`#20`), PII redaction before embedding (`#67`), eval harness gating deploys (Section 17).

**Decision criteria:** RAG when answers must be grounded in private/changing docs. NOT when a fine-tuned model + parametric knowledge suffices (closed-domain, stable), or when the question demands exact computation (use tools/SQL, not vectors).

## 2. LLM Inference APIs (sync)

Treat `POST /v1/chat/completions`-style workloads as a distinct service class:

- **Token-budgeted timeouts** (`#11`): timeout = f(max_tokens, expected tok/s + overhead), not a fixed 30s. An 8k-token generation at 60 tok/s needs ≥140s or streamed.
- **Concurrency limits** (`#44`): cap in-flight requests per model replica with a semaphore; excess waits or 429s — never queue unboundedly. Sizing: `replicas × max_seqs_per_replica` (vLLM `--max-num-seqs`).
- **Connection reuse**: keep-alive pools to the inference server (httpx/aiohttp); new connections per request waste TLS handshakes and inflate tail latency.
- **Backpressure**: admission control — reject with 429 + `Retry-After` before the GPU queues, rather than after queue wait of 30s. Expose queue depth metric.
- **Fallback chain** (`#10`): primary model → secondary provider/model → cached answer → static response. Circuit breaker on the provider; fallback must be a deliberate product decision (quality tradeoff documented).
- **Caching** (`#2`): prompt+model+temperature-normalized hash; 20-40% hit rates typical for support workloads; TTL + invalidation on knowledge change; never cache across tenants without tenant in key.

## 3. Streaming LLM Responses

SSE is the right default (`#24`); WebSockets for bidirectional voice/agent sessions (`#22`):

```python
@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    async def gen():
        yield ":ok\n\n"
        async for chunk in llm.astream(req.messages):          # token deltas
            yield f"id: {chunk.id}\ndata: {json.dumps(chunk.delta)}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
```

**Non-negotiables:** `proxy_buffering off` at Nginx; heartbeat comments every 10-15s so LB idle timeouts don't sever streams; `id:` per chunk for resume; client cancels upstream when user navigates away (asyncio cancellation → close provider connection → stop burning tokens — verify provider honors disconnect); server-side max stream duration (close at 5min with retry hint); token usage reported on stream end regardless of disconnect.

**Failure modes:** proxies buffering the whole stream (client hangs till completion); manual buffering in middlewares; assuming the provider stops billing on disconnect (it often doesn't — cancel explicitly); unbounded concurrent streams (memory per connection + GPU batch pressure — semaphore again); reconnect storms (client backoff + jitter).

## 4. Agent Orchestration Systems

**Shape:** an agent = planner loop calling tools; orchestration = state machine over steps. Production requirements:

- **Durable execution**: long-running agents (minutes-hours) must survive process restarts — use Temporal/DBOS or a persisted step journal; in-process loops lose everything on deploy.
- **Idempotent tools** (`#14`): every tool call keyed by `(agent_run_id, step)`; retrying a booked-flight tool must not book twice.
- **Tool timeouts + breakers** (`#10 #11`): a hung web scraper or API must not pin the whole run.
- **Verification before action**: for irreversible tools (send email, charge card), require human approval or a policy gate (`#Human-in-the-loop`, Section 20).
- **Deterministic spine, probabilistic core**: the loop structure, budgets, and tool schemas are code; the LLM only fills decisions. Hard caps: max_steps (e.g. 25), max_wall_time, max_tokens per run, max_cost per run — enforced in the orchestrator, not requested from the model.

**Minimal pattern:**

```python
state = await load_or_create(run_id)
while state.steps < MAX_STEPS and not state.done and cost(state) < MAX_COST:
    action = await llm.decide(state)                      # structured output (Pydantic)
    result = await tools.execute(action, idempotency_key=f"{run_id}:{state.steps}")
    state = state.advance(action, result)
await persist(state)
```

## 5. Multi-Agent Architectures

Router pattern (supervisor dispatches to specialist workers) vs pipeline pattern (fixed stages) vs blackboard (shared state, agents pick up tasks). Production rules:

- **Budget propagation**: token/cost/time budgets flow from the parent supervisor into child agents; children may not exceed their allocation — enforce in code.
- **Message contracts**: agents exchange typed Pydantic objects, not free text; validate at every boundary (`extra="forbid"`).
- **Shared state externalized**: blackboard in Postgres/Redis (transactional updates), never in process memory.
- **Failure isolation**: one agent crashing must not kill the run — supervisor retries with backoff, circuit-breaks the failing specialist, degrades (omit its contribution) if possible.
- **Determinism for testing**: mock the LLM layer; test the orchestration logic exhaustively (transitions, budget exhaustion, compensation) without any model in the loop.
- **Observability** (`#60`): every agent hop is a span (`gen_ai.agent.name`, `gen_ai.request.tokens` — use the emerging `gen_ai.*` semantic conventions); one trace per agent run.

## 6. Vector Database Infrastructure

**Options:** pgvector (Postgres extension; ≤ ~10-50M vectors; ACID alongside your relational data — best default, no new infra), Qdrant/Weaviate/Milvus (10M+; dedicated ANN indices HNSW/IVF-PQ), managed (Pinecone — zero ops, cost at scale), Redis vector search (small sets, in-memory). HNSW parameters (m, ef_construction, ef_search) trade build time/memory/recall; measure **recall@k against exact search** on a sample, not defaults.

**Engineering rules:** distance metric must match embedding model (cosine vs dot vs L2 — check provider docs; normalize vectors for cosine=dot); version the index by embedding model+preprocessing (`chunks_v3_e5m3`); deletes are tombstoned — periodic reindex; replication + backup apply to vector DBs too; PII in payloads = encrypted at rest; index build cost on bulk load: build with low ef then optimize, or use IVF-PQ for huge sets; keep metadata filters pre-filter-capable (avoid post-filter recall collapse); pgvector gotcha: HNSW index build on empty table is fine, but recall can collapse with heavy deletes — schedule REINDEX.

## 7. Embedding Pipelines

**Batch, don't stream**: documents → queue → workers (`#15`) → embed in batches of 32-128 → upsert. Dramatically higher throughput and provider throughput-limit compatibility than one-off calls.

**Requirements:** idempotency key per (doc_id, version_hash) so re-runs are safe; DLQ for parse failures; embedding model pinned by digest/name; rate limit awareness (provider TPM limits — token bucket locally at 80% of quota); cost metric per document; backfill strategy when switching models (dual-write then atomic cutover); freshness SLO (e.g. "new doc searchable ≤ 60s") with consumer-lag alerting; drift detection (embedding distribution monitoring — sudden centroid shifts signal model mismatch).

**FastAPI for ingest triggers:**

```python
@app.post("/documents")
async def ingest(doc: Document, background: BackgroundTasks):
    row = await save_pending(doc)                      # status=PENDING (durable)
    background.add_task(enqueue_embed_job, row.id)     # or outbox relay
    return {"id": row.id, "status": "PENDING"}, 202
```

## 8. Background Document Processing

Celery (battle-tested, Redis/RabbitMQ broker) or Arq/Dramatiq (async-native). Rules: idempotent tasks keyed by doc version; `acks_late=True` + prefetch 1 for long jobs (worker crash → redelivery, not loss); time limits hard (`task_time_limit`); retries only on transient errors with exponential backoff+jitter; DLQ with triage UI; per-queue concurrency for OCR vs embedding vs indexing (resource classes); progress rows in Postgres (`status: PENDING→PARSING→EMBEDDING→INDEXED→FAILED`); operator redrive tool; alert on queue age > SLO (`#20`); backpressure via broker max-length + API 503 when saturated (`#44`).

## 9. Asynchronous Inference

For >10s generations: submit-and-poll or submit-and-callback. Pattern: `POST /jobs` → 202 + `job_id` (row in Postgres: status, result, tokens_used); worker processes (queue), writes result; client polls `GET /jobs/{id}` or registers a webhook (`#101`) for completion; results TTL'd in Redis. Long-running agents (minutes): mandatory — sync HTTP would hit every timeout in the chain. Include cancel (`DELETE /jobs/{id}` → signal task/abort provider call), retry with same idempotency key, and partial-result streaming via SSE for jobs the user watches.

## 10. Model Serving

- **vLLM** (PagedAttention, continuous batching) — default for open models on GPUs; highest throughput.
- **TGI** (Hugging Face) — solid, ops-friendly.
- **SGLang / TensorRT-LLM** — maximum speed, more tuning effort.
- **Ollama / llama.cpp** — dev machines and edge; not for multi-tenant prod.
- **Triton** — multi-framework multi-model GPU serving with ensemble pipelines (preprocess→infer→postprocess) — use when you serve several models per node.
- **Managed**: OpenAI/Anthropic/Bedrock/Vertex — fastest to prod; cost and data-residency tradeoffs; still needs your timeout/retry/observability layer.

Sizing: GPU VRAM ≥ weights (+ KV cache growth); throughput tokens/s scales with batch; watch **TTFT** (time-to-first-token) and **ITL** (inter-token latency) separately, not just total; tensor parallelism across GPUs for >1 model-instance; keep model warm (load once at boot, readiness probe on model-loaded); A/B behind flags (`#51`).

## 11. GPU Resource Management

GPU is the scarce resource — treat it like the DB primary:

- One model per GPU shard; KV-cache pressure is the hidden OOMugulator — bound `--max-num-seqs` and max context.
- K8s: `nvidia.com/gpu` resource requests; device plugin; node selectors/taints so only GPU pods land there; MIG to split A100s into smaller slices for small models.
- Autoscaling GPU nodes is slow (driver + image pull + model load = minutes) — keep warm floor ≥1 replica during business hours; burst requests queue in Redis with admission control, not infinitely in GPU wait.
- Spot instances for batch embedding only, never for latency-serving (preemption mid-generation).
- Utilization metrics: GPU %, memory used, batch occupancy, queue depth — alert on sustained <20% (waste) and >90% (saturation); cost per 1M tokens dashboard per model.

## 12. LLM Rate Limiting

Two distinct budgets: **your API** (per-tenant RPM/TPM — the gateway/Redis token bucket from the `#1` pattern) and **provider quota** (TPM/RPM per model). Track provider quota locally with a Redis counter at 80% watermark, queue or shed above it (better 503 now than 429 storm later). Token-aware limiting: charge prompt_tokens+max_tokens against the bucket before dispatch (an LLM call is not one unit — it's thousands). Per-tenant fairness: weighted fair queue so one tenant's embedding backfill doesn't starve interactive chat. Audit token usage per request for billing reconciliation.

## 13. Token Usage Tracking & Inference Cost Optimization

Per-call record (Postgres/ClickHouse): `request_id, tenant, model, prompt_tokens, completion_tokens, cost_usd, latency_ms, cache_hit, feature`. Cost levers in order of payback:

1. **Cache** exact + semantic (embedding-similarity cache — threshold ~0.95 cosine; big wins on repetitive support flows).
2. **Smaller models** for classification/extraction/routing; reserve frontier models for synthesis/reasoning. Route by task class in code, measure quality per route.
3. **Prompt trimming**: strip boilerplate, cap retrieved context (rerank top-5, not top-20), shorten system prompts — measure output quality delta per token removed.
4. **max_tokens discipline**: hard caps far below "8k just because"; stop sequences; JSON mode to avoid prose overrun.
5. **Batching** offline work; provider batch APIs (50% cheaper, async).
6. **Fine-tune** small models on your corpus for narrow tasks — often beats long prompts on both cost and quality.
7. **Budget alerts**: per-feature daily budget with kill-switch flag (`#51`) — one runaway agent loop must not cost $8k overnight.

## 14. Retry & Fallback Strategies for LLMs

Retry only 429/500/timeout (transient) with exponential backoff + full jitter (`#12 #13`); NEVER retry 400 (prompt/schema rejected — retrying burns money). Honor `Retry-After`. **Idempotency** (`#14`) on any billable call: key = hash(tenant, feature, normalized messages, model, params) — cached response returned for duplicates. Fallback chain: primary model → same-provider secondary → cross-provider (Anthropic↔OpenAI↔local) → cached banner "service degraded". Circuit breaker on consecutive provider failures (`#10`) flips the chain for a cooldown, half-open probe confirms recovery. Budget: global retry amplification cap (≤20% of traffic). For agent steps, retries resume from the journaled step, not from step zero.

## 15. AI Observability

Standard three pillars, AI-flavored attributes (`#58 #59 #60 #61`):

- **Traces**: one span per LLM call inside agent traces; attributes `gen_ai.system`, `gen_ai.request.model`, `gen_ai.usage.input_tokens/output_tokens`, `gen_ai.response.finish_reasons`, plus TTFT/ITL for streams. Retain failing traces 30d, OK traces 7d.
- **Metrics**: TTFT, ITL, tokens/s per model, GPU util, queue depth, cache hit rate, 429 rate, fallback rate, cost/1k tokens, per-tenant burn rate.
- **Logs**: redacted prompt/response (PII scrubber at collector — mandatory; logs are discoverable subpoenas otherwise), structured with trace_id.
- **Eval gates**: offline eval suites (Section 17) run on every prompt/model change in CI — quality regression = build failure.
- **Dashboards**: per feature: quality score, cost, latency, 429s, fallback activations; one executive cost/quality panel.

## 16. Model Evaluation Pipelines

Prompt/model changes ship through a gate, like schema migrations:

- **Golden dataset**: 200-2000 labeled cases (input, expected properties/criteria); store versioned in Git or a DB; stratified by difficulty/tenant.
- **Metrics**: exact-match/F1 for extraction; LLM-as-judge (with rubric, different judge model than the tested one) for summarization/chat; retrieval recall@k/MRR for RAG; faithfulness (answer supported by context) and groundedness; format validity (Pydantic parse rate).
- **Thresholds**: block deploy if any metric drops >2-3 points with statistical confidence (n≥200) — same release discipline as canary (`#53`).
- **Online eval**: sample 1-5% of prod traffic for async scoring; thumbs-up/down wired to prompt versions; drift dashboard (score by week) — quality silently degrades as inputs drift.
- **A/B**: flagged cohorts with eval metrics, not just engagement.

## 17. API Security for AI Services

The LLM is a privileged interpreter of untrusted text — security review accordingly:

- **AuthN/Z**: OAuth2 + short-lived JWT (`#69 #70`) on every inference route; scope per feature; tenant isolation on **every** query — filter by tenant at retrieval, at cache key, and at tool execution (never trust model-chosen IDs to be in-tenant).
- **Rate limiting & quotas** per tenant (`#1`) + global spend cap with alert ($/hour) and hard kill flag.
- **Input validation**: length caps (`max_input_tokens`) — reject or truncate; file type/size for multimodal; Pydantic schemas everywhere; strip/escape before logging; SSRF-style guard on any URL fetching tools (`#80`).
- **Output handling**: never `eval`/exec model output; render as text/sanitized HTML (`#79`); SQL/code from model runs in sandboxed, read-only, time-boxed runtimes (`#Agent isolation`).
- **Prompt injection**: instruction/data separation in system prompt; retrieved content wrapped in delimiters + "this is data"; tools require least privilege (read-only DB roles, no shell by default); human approval gate for irreversible/egress actions; red-team suite with injection payloads in CI.
- **Secrets** (`#67`): provider keys in a manager, rotated; per-tenant routing keys never in logs; KMS envelope for per-tenant data keys.
- **Exfil paths**: model can be coaxed to leak system prompt or other tenants' data — output filters (PII regex) on responses; cache keys tenant-scoped; no cross-tenant retrieval without explicit shared-knowledge markers.

## 18. Agent Execution Isolation

Untrusted or semi-trusted tool execution deserves real isolation:

- **Sandboxed sandboxes**: gVisor/Firecracker microVMs, or containers with `--read-only`, no network (or allowlist egress proxy), dropped caps, CPU/memory limits, wall-clock timeout; k8s `RuntimeClass: gvisor` / kata.
- **Least privilege creds**: each tool gets only the scopes it needs (read-only SQL role, Stripe restricted key, mail-send-only account) — the model cannot escalate beyond its tools (`#68`).
- **Network egress allowlist**: agent tools reach only declared domains (an LLM with unrestricted `fetch_url` = SSRF with intent).
- **Budget enforcement**: per-run caps on tool calls, tokens, cost, wall time — enforced by orchestrator, killed hard at limit.
- **Kill switch**: global flag (`#51`) to halt all new agent runs; per-tenant disable; manual abort endpoint for ops.
- **Audit**: every tool invocation logged with run_id + input/output hash for post-hoc forensics.

## 19. Long-Running Agent Tasks

Hours-long research/deprovisioning/filing agents need: durable journal (Temporal/DBOS or Postgres step rows with idempotent tool calls), resumability (re-drive from last completed step), progress streaming via SSE/websocket to UI, checkpoints the user can inspect/approve, budgets, cancellation, and a dead-man's switch for runs stuck > 2× expected duration. Human approvals pause the workflow (`asyncio.Event` persisted as workflow signal; resume on approval — don't hold a process open).

## 20. Human-in-the-Loop Workflows

For irreversible actions (payments, email blast, prod config change, medical advice): agent proposes → human reviews diff/impact in UI → approve/reject → orchestrator resumes. Design: approval request = typed object (action, args, impact summary, rollback plan); timeout → auto-abort (never auto-approve); audit log of approvals (who, when, what — compliance); batch approvals for high-volume low-risk; escalation policy (approval SLA vs abort); "four-eyes" for the most critical class via two approvers. This is the same control as four-eyes deploys — treat agent actions as deploys.

---

## FastAPI Reference Skeleton (production shape)

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.llm = LLMClient(timeout=Timeout(connect=2, read=90), max_retries=0)   # we own retry
    app.state.embedder = Embedder(batch=64)
    app.state.semaphore = asyncio.Semaphore(int(os.environ.get("MAX_INFLIGHT", "8")))
    app.state.redis = redis_pool()
    yield
    await app.state.llm.aclose(); await app.state.redis.aclose()

app = FastAPI(lifespan=lifespan, default_response_class=ORJSONResponse)
app.add_middleware(RequestIdMiddleware)         # trace_id on every request
app.add_middleware(PrometheusMiddleware)        # RED metrics + exemplars
```

## Concept Map (AI → skill references)

Rate limits `#1` / caching `#2` / queues & DLQ `#15 #20` / idempotency `#14` / timeouts `#11` /
retries+jitter `#12 #13` / breakers `#10` / SSE `#24` / health & probes `#56 #57` / metrics-traces-logs
`#58-66` / secrets `#67` / OAuth+JWT `#69 #70` / SSRF `#80` / GPU autoscaling `#45 #46` / backups of
vector/Postgres state `#84` / canary of prompts `#53` / SLOs on TTFT `#63` / chaos on provider failure
`#87` / postmortems on AI incidents `#111`.
