# Agent Compatibility — Test Results (2026-11-08)

Tier definitions used throughout:

- **STRUCTURAL** — manifest/layout conformance verified by `scripts/agent_compatibility_check.py` (runnable offline).
- **MANUAL** — documented manual verification steps, not automated here.
- **RUNTIME** — exercised with a live agent session.

## Compatibility Matrix

| Agent | Discovery found? | Manifest parsed | Skill body usable | Prompts answered well | Tier |
|---|---|---|---|---|---|
| OpenCode V2 | **Yes — observed in-session** (listed with `name`/`description`; ID `production-engineering`) | ✅ CI structure tests | ✅ Decision framework + activation rules | Narrow-topic retrieval per SKILL.md | **RUNTIME (registration + listing)** |
| Claude Code | Not runtime-tested this pass | ✅ layout conforms (`.claude/skills` discovery identical) | ✅ plain Markdown | Manual prompts recommended | **STRUCTURAL** |
| Codex CLI | Not runtime-tested this pass | ✅ `.agents/skills` convention | ✅ plain Markdown | Manual prompts | **STRUCTURAL** |
| Cursor / Cline / Windsurf | No native skill system | n/a (paste model) | ✅ topic docs paste cleanly (≤ ~1,200 words each) | Manual | **MANUAL** |
| ChatGPT / Claude web | None | n/a (upload model) | ✅ | Manual | **MANUAL** |

Run the structural check yourself:

```bash
python scripts/agent_compatibility_check.py   # exits 0 on conformance
```

What the check validates: root discovery, frontmatter, name == directory, description size, activation conditions, decision framework, 111-topic presence + index consistency, sample content depth, no machine-local paths, README declares agent support optional, docs ship prompts.

## How to Manually Verify Any Agent (5 minutes)

1. Install the skill per `docs/installation.md` for your agent.
2. Ask: "What should I know before deploying a FastAPI service handling payments?"
   Expect: mentions idempotency, timeouts, health probes, error budgets — not just a list of frameworks.
3. Ask: "Apply all 111 topics to this project."
   Expect: the agent pushes back — citing the decision framework, asking for requirements/traffic/risk, refusing blind application. This tests the decision framework, not just retrieval.
4. Ask: "Why is my checkout p99 900ms after a deploy?"
   Expect: a request for metrics/logs first, hypotheses ranked, no guessing.
5. If step 3 or 4 shows a fundamental misunderstanding, file an issue with the prompt and output.

## Known Limitations

- Skills cannot execute code or enforce behavior at runtime; the value is retrieval-time judgment.
- Claude Code and Codex were not runtime-tested in this cycle; anything beyond STRUCTURAL is unverified until your local run.
- Agent behavior varies by model/version — the same skill can yield different quality across versions; report yours.
- OpenCode runtime verification covered registration and listing; interactive Q&A quality was not benchmarked this pass (tracked as issue #17 — agent test matrix).
