#!/usr/bin/env python3
"""Generate (or verify) docs/topic-index.md from the topic files.

Usage:
    python scripts/generate_topic_index.py           # write docs/topic-index.md
    python scripts/generate_topic_index.py --check   # fail if docs/topic-index.md is out of date
"""

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOP = REPO / ".agents" / "skills" / "production-engineering" / "topics"
DOC = REPO / "docs" / "topic-index.md"

NAMES = {
    1: "Rate Limiting",
    2: "Caching",
    3: "Load Balancing",
    4: "Reverse Proxies",
    5: "API Gateways",
    6: "CI/CD",
    7: "Docker",
    8: "Kubernetes",
    9: "Service Discovery",
    10: "Circuit Breakers",
    11: "Timeouts",
    12: "Retries",
    13: "Exponential Backoff",
    14: "Idempotency",
    15: "Message Queues",
    16: "Pub/Sub",
    17: "Event-Driven Architecture",
    18: "Distributed Transactions",
    19: "Saga Pattern",
    20: "Dead Letter Queues",
    21: "Cron Jobs",
    22: "WebSockets",
    23: "Long Polling",
    24: "Server-Sent Events",
    25: "Database Indexing",
    26: "Query Optimization",
    27: "N+1 Queries",
    28: "Connection Pooling",
    29: "Read Replicas",
    30: "Sharding",
    31: "Partitioning",
    32: "Replication",
    33: "Leader Election",
    34: "CAP Theorem",
    35: "Eventual Consistency",
    36: "Optimistic Locking",
    37: "Pessimistic Locking",
    38: "Distributed Locks",
    39: "Race Conditions",
    40: "Deadlocks",
    41: "Memory Leaks",
    42: "Garbage Collection",
    43: "Thread Safety",
    44: "Backpressure",
    45: "Autoscaling",
    46: "Horizontal Scaling",
    47: "Vertical Scaling",
    48: "CDN",
    49: "Edge Caching",
    50: "Cache Invalidation",
    51: "Feature Flags",
    52: "Blue-Green Deployment",
    53: "Canary Releases",
    54: "Rolling Deployments",
    55: "Rollbacks",
    56: "Health Checks",
    57: "Liveness & Readiness Probes",
    58: "Monitoring",
    59: "Logging",
    60: "Distributed Tracing",
    61: "Metrics",
    62: "Alerts",
    63: "SLOs",
    64: "SLIs",
    65: "Error Budgets",
    66: "Observability",
    67: "Secrets Management",
    68: "IAM",
    69: "OAuth",
    70: "JWT Rotation",
    71: "TLS",
    72: "Encryption at Rest",
    73: "Encryption in Transit",
    74: "WAF",
    75: "DDoS Protection",
    76: "CORS",
    77: "CSRF",
    78: "SQL Injection",
    79: "XSS",
    80: "SSRF",
    81: "Database Migrations",
    82: "Schema Versioning",
    83: "Disaster Recovery",
    84: "Backups",
    85: "Failover",
    86: "Multi-Region Deployment",
    87: "Chaos Engineering",
    88: "Cost Optimization",
    89: "Cold Starts",
    90: "Serverless Limits",
    91: "Latency",
    92: "Throughput",
    93: "P99 Latency",
    94: "Tail Latency",
    95: "Network Partitions",
    96: "Clock Skew",
    97: "DNS",
    98: "TCP vs UDP",
    99: "HTTP/2 & HTTP/3",
    100: "gRPC",
    101: "Webhooks",
    102: "API Versioning",
    103: "Semantic Versioning",
    104: "Infrastructure as Code",
    105: "Terraform",
    106: "Helm Charts",
    107: "Build Caching",
    108: "Dependency Hell",
    109: "Production Incidents",
    110: "On-Call",
    111: "Postmortems",
}

CATEGORY_NAMES = {
    "A": "Backend Architecture & API Engineering",
    "B": "Database Engineering & Distributed Systems",
    "C": "Deployment & Production Operations",
    "D": "Security Engineering",
    "E": "Database Lifecycle",
    "F": "Disaster Recovery & Reliability",
    "G": "Performance Engineering",
    "H": "Networking & Communication",
    "I": "Infrastructure & Build Engineering",
    "J": "Production Incident Management",
}


def category_of(n: int) -> str:
    if n <= 24:
        return "A"
    if n <= 50:
        return "B"
    if n <= 66:
        return "C"
    if n <= 80:
        return "D"
    if n <= 82:
        return "E"
    if n <= 88:
        return "F"
    if n <= 94:
        return "G"
    if n <= 103:
        return "H"
    if n <= 108:
        return "I"
    return "J"


def topic_files() -> dict[int, str]:
    mapping = {}
    for path in TOP.glob("[0-9][0-9][0-9]-*.md"):
        m = re.match(r"(\d{3})-(.+)\.md$", path.name)
        if m:
            mapping[int(m.group(1))] = path.name
    return mapping


def render() -> str:
    files = topic_files()
    missing = [n for n in range(1, 112) if n not in files]
    if missing:
        raise SystemExit(f"missing topic files: {missing}")
    rows = [
        f"| {n} | [{NAMES[n]}](../.agents/skills/production-engineering/topics/{files[n]}) | {category_of(n)} |"
        for n in range(1, 112)
    ]
    by_cat = {}
    for n in range(1, 112):
        by_cat.setdefault(category_of(n), []).append(n)
    out = [
        "# Topic Index",
        "",
        "All 111 topics, numbered 1–111, grouped by category. Topic IDs are stable forever — docs are never renumbered.",
        "",
        "| # | Topic (path) | Category |",
        "|---|---|---|",
        *rows,
        "",
        "## By Category",
        "",
    ]
    for cat in ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]:
        names = ", ".join(f"{n} {NAMES[n]}" for n in by_cat[cat])
        out.append(
            f"### Category {cat} — {CATEGORY_NAMES[cat]} ({len(by_cat[cat])} topics)\n\n{names}\n"
        )
    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check", action="store_true", help="fail if the doc is out of date"
    )
    args = parser.parse_args()
    content = render()
    if args.check:
        if not DOC.exists() or DOC.read_text(encoding="utf-8") != content:
            print(
                "docs/topic-index.md is out of date — run: python scripts/generate_topic_index.py"
            )
            return 1
        print("docs/topic-index.md is up to date")
        return 0
    DOC.write_text(content, encoding="utf-8")
    print(f"wrote {DOC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
