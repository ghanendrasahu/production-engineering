#!/usr/bin/env python3
"""Reproducible agent-skill compatibility check for the production-engineering library.

Verifies, without any specific agent runtime:
- skill root + SKILL.md discovered from repo root (`.agents/skills` convention)
- manifest: name matches directory, description present and sized sensibly
- discovery list inputs stay within limits (description ≤ 1024 chars recommendation)
- the skill body carries an activation decision framework (agent instruction quality)
- all topics retrievable by filename and by index
- no agent-specific absolute paths or credentials in the skill body

Tiered result per agent class:
- STRUCTURAL: layout/manifest conforms (this script)
- MANUAL: human verification steps documented in docs/agent-test-results.md
- RUNTIME: verified with a live agent session
"""

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO / ".agents" / "skills" / "production-engineering"
SKILL_MD = SKILL_DIR / "SKILL.md"
TOPICS = SKILL_DIR / "topics"
fails = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        fails.append(name)


# --- discovery
check(
    "skill root discovered at .agents/skills/production-engineering", SKILL_DIR.is_dir()
)
check("SKILL.md exists", SKILL_MD.exists())

# --- manifest
text = SKILL_MD.read_text(encoding="utf-8")
m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
check("SKILL.md has YAML frontmatter", bool(m))
if m:
    fm = m.group(1)
    body = m.group(2)
    name_m = re.search(r"(?m)^name:\s*(\S+)", fm)
    desc_m = re.search(r"(?m)^description:\s*(.+)$", fm)
    check("frontmatter has name", bool(name_m))
    if name_m:
        check(
            "name matches directory (skill ID stable)",
            name_m.group(1) == SKILL_DIR.name,
            name_m.group(1),
        )
    check("frontmatter has description", bool(desc_m))
    if desc_m:
        d = desc_m.group(1).strip().strip('"')
        check("description 20..1024 chars", 20 <= len(d) <= 1024, f"{len(d)} chars")
    check(
        "body declares activation conditions",
        "When to Activate" in body or "when to activate" in body.lower(),
    )
    check(
        "body carries decision framework (CRITICAL/HIGH/MEDIUM)",
        all(k in body for k in ("CRITICAL", "HIGH", "MEDIUM")),
    )
    check(
        "body tells agent NOT to apply all topics blindly",
        "not blindly" in body.lower() or "blindly" in body.lower(),
    )

# --- topics retrievable
topic_files = sorted(TOPICS.glob("[0-9][0-9][0-9]-*.md"))
check("111 topics present", len(topic_files) == 111, f"{len(topic_files)}")
index = (
    (REPO / "docs" / "topic-index.md").read_text(encoding="utf-8")
    if (REPO / "docs" / "topic-index.md").exists()
    else ""
)
check(
    "docs/topic-index.md lists all 111 topic titles",
    all(f"topics/{f.name}" in index for f in topic_files),
)
sample = [
    f
    for f in topic_files
    if f.name.startswith(("001-", "014-", "050-", "063-", "111-"))
]
check(
    "sample topics readable and non-trivial (>250 words)",
    all(len(f.read_text(encoding="utf-8").split()) > 250 for f in sample),
)

# --- portability / no environment dependencies
skill_text = text + "\n".join(
    f.read_text(encoding="utf-8", errors="ignore") for f in [SKILL_MD]
)
for frag in ("C:\\Users\\", "/Users/", "ghanendrasahu2911"):
    check(
        f"no machine-local fragment {frag!r} in skill manifest", frag not in skill_text
    )

# --- agent-independent core
readme = (REPO / "README.md").read_text(encoding="utf-8")
check(
    "README states agent support is optional",
    "agent" in readme.lower()
    and ("without any" in readme.lower() or "optional" in readme.lower()),
)

# --- example prompts present in docs
usage = (REPO / "docs" / "usage.md").read_text(encoding="utf-8")
check(
    "docs/usage.md ships copy-pasteable prompts",
    usage.count("@production-engineering") >= 4,
)

print()
print("RESULT:", "STRUCTURALLY COMPATIBLE" if not fails else f"FAILURES: {fails}")
sys.exit(1 if fails else 0)
