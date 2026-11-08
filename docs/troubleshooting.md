# Troubleshooting

Practical failures you may hit — and their fixes.

## Installation & Setup

**OpenCode doesn't show the skill.**
- Confirm the skill is at `.agents/skills/production-engineering/SKILL.md` relative to your project root (Project compatibility source), or `~/.config/opencode/skills/production-engineering/SKILL.md` (user-global).
- `SKILL.md` must contain `name:` and `description:` in frontmatter; `description` must be non-empty. No `autoinvoke: false` set.
- Skills are watched — no restart needed; if it still doesn't appear, run `opencode /reload` and re-check.

**Claude Code doesn't load it.**
- Path must be `~/.claude/skills/production-engineering/SKILL.md` (user) or `.claude/skills/production-engineering/SKILL.md` (project). Directory name == skill ID.

## Validation Failures

**`check_topic_coverage.py` reports missing topics.**
A topic file was renamed, deleted, or renumbered. Restore from git: `git checkout -- .agents/skills/production-engineering/topics/`. Numbering is forever — never renumber; fix the file, not the script.

**`validate_skills.py`: broken link.**
A relative link in any doc points at a moved file. Run `python scripts/generate_topic_index.py` if topic files changed, then re-run validator; fix the specific path reported.

**`test_all_topics_have_frontmatter` fails with BOM/CRLF.**
Your editor wrote CRLF/BOM. Fix:
```bash
python - <<'EOF'
from pathlib import Path
for p in Path('.').rglob('*.md'): raw = p.read_bytes().lstrip(b'\xef\xbb\xbf').replace(b'\r\n', b'\n'); p.write_bytes(raw)
EOF
```
(or `git add --renormalize .`).

**`generate_topic_index.py --check` fails.**
`python scripts/generate_topic_index.py` to regenerate, then commit the result.

## Docker & Examples

**`docker compose up` fails with "port is already allocated".**
Another Postgres on 5432 or RabbitMQ on 5672 is in the way. The examples use uncommon ports (55432/8000/15672) for a reason; check `docker ps`; edit the compose file's host port mapping — don't stop unrelated services you don't own.

**RabbitMQ producer/workers crash-loop.**
Broker starts slower than apps. Compose depends_on uses healthcheck + in-code retry; if you removed either, apps die on first connect. Restore both (see `examples/distributed-systems/`).

**AI agent harness fails with tool-not-registered.**
`ToolExecutor` got a tool name with no registered callable. Check the tool registry matches your LLM's generated tool calls — or let it raise: silent skips hide bugs.

## CI Failures on Forks

- Fork PRs get no secrets — fine, none are required.
- First run on a fork: permissions read-only; our workflow only needs `contents: read` — it will pass.
- Flaky network in external link checks? CI doesn't check external links by design (see issue #13).

## Asking for Help

Search [Discussions](https://github.com/ghanendrasahu/production-engineering/discussions) first. If it's a bug, file it with the exact command and full output.
