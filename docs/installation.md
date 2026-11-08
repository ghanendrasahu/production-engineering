# Installation

Three supported install paths. Pick one — they are not alternatives to install all three, only to try the skill wherever you work it.

## Option A — OpenCode (recommended for this project)

**As a project-local skill** (repo checkout; OpenCode discovers `.agents/skills` from the repo root):

```bash
git clone https://github.com/ghanendrasahu/production-engineering.git
cd production-engineering
# OpenCode sees .agents/skills/production-engineering/ automatically
```

**As a user-global skill** (available in every project — back up any existing `~/.config/opencode/skills/production-engineering` first; the commands below replace it):

```bash
git clone https://github.com/ghanendrasahu/production-engineering.git "$HOME/source/production-engineering"
# Option 1: register as a source root (no copying):
#   add to opencode.jsonc → "skills": ["~/source/production-engineering/.agents/skills"]
# Option 2: copy (overwrites any existing global production-engineering skill):
mkdir -p "$HOME/.config/opencode/skills"
rm -rf "$HOME/.config/opencode/skills/production-engineering"   # only if you intend to replace it
cp -r "$HOME/source/production-engineering/.agents/skills/production-engineering" "$HOME/.config/opencode/skills/"
```

Or register it explicitly in `opencode.jsonc`:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "skills": ["~/source/production-engineering/.agents/skills"]
}
```

The skill ID is `production-engineering`. Invoke with `@production-engineering` or let it auto-activate from its description.

## Option B — Claude Code

Claude Code reads skills from `~/.claude/skills` (user) or `.claude/skills` (project):

```bash
git clone https://github.com/ghanendrasahu/production-engineering.git
mkdir -p ~/.claude/skills/production-engineering
cp -r production-engineering/.agents/skills/production-engineering/. ~/.claude/skills/production-engineering/
```

Then `@production-engineering` in a session, or let auto-activation match on "production", "deploy", "reliability", etc.

## Option C — Codex CLI / other `.agents`-compatible agents

Agents honoring the emerging `.agents/skills/` convention discover the skill directly from a checkout:

```bash
git clone https://github.com/ghanendrasahu/production-engineering.git ~/source/production-engineering
```

or symlink/copy `.agents/skills/production-engineering` into the agent's global skills directory.

## No-clone, read-only usage

Every topic doc is also directly readable at:

```
https://github.com/ghanendrasahu/production-engineering/tree/main/.agents/skills/production-engineering/topics
```

Paste the specific topic into your agent context when you cannot install the skill — but prefer installing: the whole point is agent-driven retrieval.
