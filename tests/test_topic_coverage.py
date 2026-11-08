"""Topic coverage tests: numbering 1..111, uniqueness, canonical titles."""

import re
from pathlib import Path

import pytest

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


def _topics():
    return list(TOPICS.glob("[0-9][0-9][0-9]-*.md"))


def test_exactly_111_topics():
    files = _topics()
    assert len(files) == 111


def test_numbering_1_to_111_no_gaps_no_dupes():
    nums = sorted(int(re.match(r"(\d+)-", f.name).group(1)) for f in _topics())
    assert nums == list(range(1, 112))


def test_slugs_are_unique():
    slugs = [f.name.split("-", 1)[1] for f in _topics()]
    assert len(slugs) == len(set(slugs))


@pytest.mark.parametrize("n", range(1, 112))
def test_topic_title_matches_canonical_scope(n):
    f = next(f for f in _topics() if int(re.match(r"(\d+)-", f.name).group(1)) == n)
    m = re.search(r"(?m)^title:\s*(.+)$", f.read_text(encoding="utf-8"))
    assert m, f"no title in {f.name}"
    assert m.group(1).strip() == CANONICAL[n]
