#!/usr/bin/env python3
"""Validate the production-engineering skill library.

Checks: file naming, frontmatter, required sections, code-fence balance,
relative link resolution, secret-like patterns, and placeholder text.

Exit code 0 = all checks pass; 1 = failures (printed to stdout).
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL = REPO / ".agents" / "skills" / "production-engineering"
TOPICS = SKILL / "topics"
NAME = re.compile(r"^(\d{3})-([a-z0-9-]+)\.md$")

REQUIRED_SECTIONS = [
    "## 1. Topic name and metadata",
    "## 2. What it is",
    "## 3. Why it exists",
    "## 4. The engineering problem it solves",
    "## 5. How it works internally",
    "## 6. Architecture and design principles",
    "## 7. When to use it",
    "## 8. When NOT to use it",
    "## 9. Implementation strategies",
    "## 10. Production-grade implementation",
    "## 11.",
    "## 12. FastAPI integration where relevant",
    "## 13. Distributed-system considerations",
    "## 14. AI/ML/LLM application examples where relevant",
    "## 15. Security considerations",
    "## 16. Performance considerations",
    "## 17. Common mistakes",
    "## 18. Anti-patterns",
    "## 19. Monitoring and observability",
    "## 20. Testing strategies",
    "## 21. Deployment considerations",
    "## 22. Production-readiness checklist",
    "## 23. Troubleshooting guide",
    "## 24. Further reading and authoritative references",
]

SECRET_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "OpenAI-style key"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key id"),
    (re.compile(r"ghp_[A-Za-z0-9]{30,}"), "GitHub personal access token"),
    (re.compile(r"gho_[A-Za-z0-9]{30,}"), "GitHub OAuth token"),
    (
        re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        "private key block",
    ),
    (
        re.compile(r"(?<![\w.])password\s*[:=]\s*['\"][^'\"]{8,}", re.I),
        "hardcoded password",
    ),
]

PLACEHOLDER = re.compile(r"\b(TODO|TBD|FIXME|XXX\b|lorem ipsum)", re.I)
LINK = re.compile(r"\]\(([^)]+)\)")

problems = []


def check(cond, msg):
    if not cond:
        problems.append(msg)


def md_files():
    for p in SKILL.rglob("*.md"):
        yield p
    for p in [REPO / "README.md", REPO / "CONTRIBUTING.md"]:
        if p.exists():
            yield p


# --- 1. topic file naming and content
topic_files = sorted(TOPICS.glob("*.md"))
check(len(topic_files) == 111, f"expected 111 topic files, found {len(topic_files)}")
for p in topic_files:
    m = NAME.match(p.name)
    check(bool(m), f"bad topic filename: {p.name}")
    text = p.read_text(encoding="utf-8")
    check(text.startswith("---\n"), f"missing frontmatter: {p.name}")
    fm = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if fm:
        for key in ["topic:", "title:", "category:", "skill:"]:
            check(key in fm.group(1), f"frontmatter missing {key} in {p.name}")
        num = int(re.search(r"topic:\s*(\d+)", fm.group(1)).group(1))
        check(
            num == int(m.group(1)),
            f"frontmatter topic {num} != filename number in {p.name}",
        )
    for section in REQUIRED_SECTIONS:
        check(section in text, f"{p.name}: missing section '{section}'")
    check(text.count("```") % 2 == 0, f"{p.name}: unbalanced code fences")
    check(not PLACEHOLDER.search(text), f"{p.name}: placeholder text found")

# --- 2. SKILL.md exists and is well-formed
skillmd = SKILL / "SKILL.md"
check(skillmd.exists(), "SKILL.md missing")
front = re.match(r"^---\n(.*?)\n---\n", skillmd.read_text(encoding="utf-8"), re.S)
check(bool(front), "SKILL.md: bad frontmatter")
if front:
    check(
        "name:" in front.group(1) and "description:" in front.group(1),
        "SKILL.md: name/description missing",
    )

# --- 3. relative links resolve inside the skill
for p in md_files():
    base = p.parent
    for target in LINK.findall(p.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        path = (base / target.split("#")[0]).resolve()
        if target and not path.exists():
            problems.append(f"{p.name}: broken link -> {target}")

# --- 4. secret scan (whole repo minus .git)
for p in REPO.rglob("*"):
    if (
        not p.is_file()
        or ".git" in p.parts
        or p.suffix.lower()
        not in {".md", ".py", ".yml", ".yaml", ".txt", ".toml", ".json"}
    ):
        continue
    text = p.read_text(encoding="utf-8", errors="ignore")
    for pattern, label in SECRET_PATTERNS:
        check(not pattern.search(text), f"{p.relative_to(REPO)}: possible {label}")

print(f"files scanned; problems: {len(problems)}")
for p in problems:
    print(" -", p)
sys.exit(1 if problems else 0)
