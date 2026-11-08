# Supported Agents

The core knowledge in this library is agent-agnostic Markdown — usable by **no agent at all**. Agent integrations are **optional** conveniences. Here is exactly how each one has been verified, so you can judge confidence yourself.

## Requirements & Compatibility

| Agent | Version requirement | Install | Verification level | Notes |
|---|---|---|---|---|
| **OpenCode** | V2 (any current) | `.agents/skills/` (project) or `~/.config/opencode/skills` (user) | **Structure + manifest tests pass in CI** | Skill in this repo auto-activates from description; invoke with `@production-engineering` |
| **Claude Code** | Any current | copy skill dir to `~/.claude/skills/production-engineering/` | **Layout conformance** (SKILL.md + frontmatter + structure) | Not runtime-tested here; report issues |
| **Codex CLI / generic `.agents/skills` readers** | Agents honoring the convention | clone anywhere; agent finds the skill from cwd upward | **Layout conformance** | |
| **Cursor / Windsurf / Cline** | Any | paste topic docs into project rules/context | **Manual context only** — no native discovery | Use `docs/sites/`-style context injection |
| **ChatGPT / Claude web / custom GPTs** | Any | upload topic docs to project knowledge | **Manual** | Works; no auto-retrieval |
| **GitHub Copilot Chat** | Any | reference docs in issue/PR context | **Manual, best effort** | |

## What "Verified" Means

"CI structure tests pass" = filename conventions, frontmatter keys, 111 topics, 24-section presence, link resolution inside the repo. It is **not** a guarantee that your agent loads the skill at runtime — that depends on the agent's own skill loader.

## How Skills Are Structured Here (porting guide)

- `SKILL.md` at the skill root carries `name` + `description` — the discovery contract.
- Skill ID = directory name (`production-engineering`), stable forever.
- Topic docs are self-contained Markdown with YAML frontmatter — paste any one alone into a context.
- Relative links assume repo layout; if you flatten the tree, prefer pasting whole topic files over leaf references.

## Known Limitations

- Skills cannot execute code — value is retrieval-time judgment.
- No agent integration skips the repo's validation or the maintainer's judgment — agent output from this skill is a draft, not doctrine.
- Announcements for new agents: report your agent + the 3 prompts you tried in [Discussions](https://github.com/ghanendrasahu/production-engineering/discussions) — we'll add it here.

## Install Notes Per Agent

See [installation.md](installation.md) for commands. Nothing in this repo modifies your global agent configuration automatically — copying or registering is **your** step, deliberately.
