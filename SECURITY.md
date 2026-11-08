# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| latest (v1.x) | ✅ |

## Reporting a Vulnerability

Production Engineering Skills is a documentation and skill library — it contains no runtime service of its own. However, vulnerabilities can still exist in:

- Code examples that invite insecure usage (e.g., missing auth, unsafe defaults)
- Automation in `scripts/` and `.github/workflows/`
- Any dependency referenced by the project

If you find one, **do not open a public issue** that includes exploitable detail.

Instead:

1. Open a **private** report via [GitHub's private vulnerability reporting](https://github.com/ghanendrasahu/production-engineering/security/advisories/new) on this repository, or
2. Start a private [GitHub Discussion](https://github.com/ghanendrasahu/production-engineering/discussions) asking the maintainer to open a private channel.

Please include:

- A description of the issue and where it lives (file and line if possible)
- Steps to reproduce or a minimal example
- Your assessment of impact and severity
- Any suggested remediation

## Response Targets

- Acknowledgement: within 7 days
- Triage and severity assessment: within 14 days
- Fix or mitigation: as soon as reasonably possible, with credit to the reporter if desired

## In Scope

- Insecure or misleading guidance in any topic document
- Broken or dangerous automation/workflows
- Dependency vulnerabilities in scripts

## Out of Scope

- General quality/style issues (open a normal PR or issue)
- Vulnerabilities in third-party tools named in documentation (report upstream)

## Safe Harbor

Good-faith research conducted in line with this policy will not be treated as a violation of our terms. Do not access data that is not yours, including any data in public demo instances.

Thank you for helping keep this project and its users safe.
