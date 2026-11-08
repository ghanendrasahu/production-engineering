# Example: Production AI Agent Systems

Minimal agent loop demonstrating the guardrails from `references/ai-engineering.md`: hard budgets, idempotent tool calls, structured decisions, kill switch, and full observability hooks.

Not runnable against a real LLM out of the box (you provide `LLM_API_KEY`); the loop, budgets, and policy gates run against any provider — see `agent.py`.

## The pattern in 30 seconds

```
user task → orchestrator → [ LLM decides next action (Pydantic-structured) ]
                        ──▶ [ policy gate: allowlist tools, budgets, approvals ]
                        ──▶ [ tool executes idempotently with key (run_id, step) ]
                        ──▶ [ result appended to journal; budgets decremented ]
                        ──▶ loop until done / max_steps / max_cost / cancel
```

## File layout

- `agent.py` — the orchestrator skeleton (budgets, idempotency, approval hooks, kill switch)
- `README.md` — this file

## Map to topics

`#44 Backpressure` (admission control) · `#14 Idempotency` (tools) · `#11 Timeouts` (per-step deadlines) · `#10 Circuit Breakers` (provider) · `#60 Distributed Tracing` (one trace per run) · `#51 Feature Flags` (kill switch per agent/tool) · `#111 Postmortems` (agent incidents are incidents)

## Production checklist for agents (from the skill)

1. Budgets in code, not prompts: `max_steps`, `max_wall_time_s`, `max_tokens`, `max_cost_usd` — enforced before dispatch.
2. Every tool call carries `idempotency_key = (run_id, step_seq)`.
3. Irreversible actions (payments, sends, deletes) require a structured approval (human-in-the-loop) — never autonomous.
4. Retrieved/tool content is data, not instruction — wrap in delimiters; system prompt says so; tools read-only by default.
5. Kill switch: one flag flip halts all new runs and cancels in-flight provider calls.
6. Every run emits: trace, token/cost meter, eval score hook, and a `run_log` row for audit.
