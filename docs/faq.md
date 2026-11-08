# FAQ

**Q: Is this affiliated with Anthropic/OpenCode/any vendor?**
No. Community project under the MIT license, maintainer Ghanendra Sahu. It is compatible with Anthropic-style skill conventions and OpenCode's `.agents/skills` discovery.

**Q: Do I need all 111 topics for my project?**
No — almost nothing needs all 111. The skill helps agents pick. A CRUD monolith might critically need topics 1, 25, 28, 56, 67, 71 — that's fine.

**Q: Topic doc X is wrong / outdated.**
Thank you — that's exactly the feedback we need. File an issue with the topic number, the claim, and authoritative source. See [SUPPORT.md](../SUPPORT.md).

**Q: Will you accept a 112th topic (e.g., "LLM Evals")?**
Proposals go through the new-skill template. Current scope stays 111 for v1.x; extensions land as 112+ with the same quality bar.

**Q: Can I use this at work / in a commercial product?**
Yes — MIT. Attribution appreciated but not required. Don't ship topic docs as your company's internal runbooks without reviewing them against your actual environment.

**Q: How is this better than a blog post / than ChatGPT's memory?**
Blogs don't load into your agent. General LLMs remember concepts but apply them unprompted, inconsistently, and without your stack's constraints. This is versioned, testable, human-reviewed knowledge the agent retrieves on demand.

**Q: The topic says "Use when NOT" — can the agent ignore it and apply anyway?**
That's the failure mode the structure exists to prevent. If an agent applies a pattern outside its stated conditions without flagging it, treat the output as a draft, not a design.

**Q: Where do I report a security issue?**
[SECURITY.md](../SECURITY.md) — private advisory, not a public issue.

**Q: Why are examples mostly Python/FastAPI?**
That is the library's center of gravity. The patterns are stack-agnostic (HTTP is HTTP; queues are queues) — port freely, and consider contributing your port.

**Q: How do I contribute without deep expertise?**
Review topics against official docs (find and cite discrepancies), run the validation scripts, fix broken links, add FastAPI/Postgres examples. Every one of those compounds. See [CONTRIBUTING.md](../CONTRIBUTING.md).
