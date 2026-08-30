---
description: Reproducible structured literature review across the local corpus with verified citation chains
---

# Structured Corpus Review Skill

## When to Use
- User asks for a literature review on a topic
- User wants to compare multiple sources
- User needs a reproducible survey of the indexed local corpus

## Steps

1. **Scope definition**: Record the research question, corpus scope/snapshot, and inclusion/exclusion criteria.
2. **Reproducible search**: Run `cite_search` with 3-5 recorded query formulations and retain result node/source IDs
3. **Expand search**: Use `cite_argument_query` with `find_contradictions: true` to map disagreement
4. **Corpus exploration**: Delegate to `@explore-corpus` for browsing related document trees
5. **Screening ledger**: Record every included source/node and every excluded source/node with one reason
6. **Verification**: Delegate to `@verifier` to audit integrity and claim-to-passage alignment; optionally run `cite_bibliographic_verify` only with approval for network access
7. **Synthesis**: Write structured review with inline citations and evidence chains
8. **Gap analysis**: Identify topics with zero or sparse corpus coverage
9. **Report**: Produce final output with references section formatted via `cite_render`

Call the work a **systematic review** only when it has a complete protocol, screening counts, and exclusion log. Otherwise call it a **structured corpus review**.

## Output Structure
- Introduction (research question, scope, criteria)
- Methodology (search strategy, queries used, inclusion criteria)
- Findings (organized thematically with [Author Year] citations)
- Contradictions (mapped across sources with evidence)
- Gaps (identified with search evidence showing absence)
- References (formatted via cite_render, Chicago author-date)
- Reproducibility ledger (machine-readable JSON)

## Reproducibility Ledger

```json
{
  "review_type": "structured_corpus_review",
  "research_question": "",
  "scope": { "corpus": "local", "snapshot": "", "limitations": [] },
  "queries": [],
  "criteria": { "include": [], "exclude": [] },
  "included": [{ "source_id": "", "node_ids": [], "reason": "" }],
  "excluded": [{ "source_id": "", "node_ids": [], "reason": "" }],
  "contradictions": [],
  "gaps": [],
  "verification_summary": {
    "integrity": { "approved": 0, "rejected": 0 },
    "semantic": { "supported": 0, "unsupported": 0, "ambiguous": 0, "retrieval_failed": 0 },
    "bibliographic": { "verified": 0, "not_found": 0, "unresolvable": 0, "unavailable": 0 }
  }
}
```
