# Supported Agents

| Agent | Status | Install | Notes |
| --- | --- | --- | --- |
| **OpenCode** (TUI/CLI/desktop) | ✅ First-class | `.agents/skills/` (project) or `~/.config/opencode/skills` (global) | Auto-activates from description; invoke with `@production-engineering` |
| **Claude Code** (Anthropic CLI) | ✅ Tested layout | `.claude/skills/production-engineering/` or global | Same SKILL.md format; copy the skill directory; `@production-engineering` |
| **Codex CLI / agents reading `.agents/skills`** | ✅ Compatible | repo root or user skills dir | Follows the emerging `.agents/skills` convention |
| **Cursor / Windsurf / Cline** | 🟡 Via rules/context | paste relevant topic docs into project rules/context | No native skill system; use reference files + topic docs as context |
| **ChatGPT / Claude web** | 🟡 Via paste/projects | upload topic files to Projects/GPTs knowledge | No auto-activation; retrieve by hand |
| **GitHub Copilot** | 🟡 Via context | reference docs in issue/PR context | Best-effort |

Status meanings: ✅ first-class convention, installed and discoverable · 🟡 usable as knowledge; agent has no native skill loading.

## How Skills Are Structured Here (for anyone porting)

- `.agents/skills/production-engineering/SKILL.md` — manifest: `name`, `description`, instructions, decision framework. ID = directory name (`production-engineering`).
- `topics/` — one self-contained document per topic. Safe to paste individually into any LLM context.
- `references/`, `workflows/`, `templates/` — supporting knowledge the agent opens on demand.

**Gotchas when porting:** keep the directory name stable (it is the skill ID); keep `SKILL.md` at the root; keep relative links working (`../docs/` etc. assume repo layout; link targets degrade gracefully if flattened).

Known limitations: skills cannot execute code by themselves — the value is expert context applied at design/review time. If your agent supports tool use (OpenCode/Claude Code do), the agent will run tests and commands per the skill's verification sections.
