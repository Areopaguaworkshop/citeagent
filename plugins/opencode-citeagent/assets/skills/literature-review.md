---
description: Systematic literature review across the academic corpus with verified citation chains
---

# Literature Review Skill

## When to Use
- User asks for a literature review on a topic
- User wants to compare multiple sources
- User needs a systematic survey of existing research

## Steps

1. **Scope definition**: Clarify the research question with the user. Define inclusion/exclusion criteria.
2. **Systematic search**: Run `cite_search` with 3-5 different query formulations to maximize recall
3. **Expand search**: Use `cite_argument_query` with `find_contradictions: true` to map disagreement
4. **Corpus exploration**: Delegate to `@explore-corpus` for browsing related document trees
5. **Evidence collection**: Gather all potential evidence items from search results
6. **Verification**: Delegate to `@verifier` to independently audit all evidence items
7. **Synthesis**: Write structured review with inline citations and evidence chains
8. **Gap analysis**: Identify topics with zero or sparse corpus coverage
9. **Report**: Produce final output with references section formatted via `cite_render`

## Output Structure
- Introduction (research question, scope, criteria)
- Methodology (search strategy, queries used, inclusion criteria)
- Findings (organized thematically with [Author Year] citations)
- Contradictions (mapped across sources with evidence)
- Gaps (identified with search evidence showing absence)
- References (formatted via cite_render, Chicago author-date)
