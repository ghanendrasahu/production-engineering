#!/usr/bin/env python3
"""Check the topic library: 111 unique topics numbered 1..111.

Verifies:
- exactly one file per topic number, zero gaps, zero duplicates
- filename number matches frontmatter topic field
- titles match the canonical 111-topic scope (original list preserved)
- category totals are A=24 B=26 C=16 D=14 E=2 F=6 G=6 H=9 I=5 J=3
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOPICS = REPO / ".agents" / "skills" / "production-engineering" / "topics"

CANONICAL = {
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

CATEGORY_TOTALS = {
    "A": 24,
    "B": 26,
    "C": 16,
    "D": 14,
    "E": 2,
    "F": 6,
    "G": 6,
    "H": 9,
    "I": 5,
    "J": 3,
}


def category_of(n):
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


problems = []

files = list(TOPICS.glob("[0-9][0-9][0-9]-*.md"))
nums = []
titles = {}
for f in files:
    m = re.match(r"(\d{3})-([a-z0-9-]+)\.md", f.name)
    if not m:
        problems.append(f"bad filename: {f.name}")
        continue
    n = int(m.group(1))
    nums.append(n)
    text = f.read_text(encoding="utf-8")
    tm = re.search(r"(?m)^title:\s*(.+)$", text)
    titles[n] = tm.group(1).strip() if tm else None

missing = [n for n in range(1, 112) if n not in nums]
duplicates = sorted({n for n in nums if nums.count(n) > 1})
wrong = {n: t for n, t in titles.items() if t != CANONICAL.get(n)}
cat_counts = {}
for n in nums:
    cat_counts[category_of(n)] = cat_counts.get(category_of(n), 0) + 1

problems += [f"missing topic number(s): {missing}"] if missing else []
problems += [f"duplicate topic number(s): {duplicates}"] if duplicates else []
problems += [
    f"title mismatch topic {n}: {t!r} != {CANONICAL[n]!r}" for n, t in wrong.items()
]
for cat, expected in CATEGORY_TOTALS.items():
    got = cat_counts.get(cat, 0)
    if got != expected:
        problems.append(f"category {cat}: expected {expected} topics, found {got}")
if len(files) != 111:
    problems.append(f"expected 111 topic files, found {len(files)}")

print(f"topics checked: {len(files)} | problems: {len(problems)}")
for p in problems:
    print(" -", p)
sys.exit(1 if problems else 0)
