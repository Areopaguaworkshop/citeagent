# Academic Integrity Rules

These rules are enforced by the CiteAgent verification system. They apply to all agents that produce academic output.

## Mandatory
- Every factual claim must have a `cite_search` result backing it
- Every evidence item must pass verification ladder (L0-L4) before inclusion in output
- If a Merkle proof fails, the evidence is REJECTED — no exceptions
- Citation keys that don't resolve to CSL records are invalid
- Never cite a source you haven't verified exists in the corpus

## Prohibited
- Fabricating citation details (authors, titles, years, DOIs)
- Using evidence items with missing SHA-256 hashes
- Skipping Merkle verification for "trusted" sources
- Including unverified external search results as primary evidence
- Modifying evidence items after retrieval

## On Uncertainty
- If no evidence exists in corpus, state: "No corpus evidence found for [claim]."
- If evidence is ambiguous, state the ambiguity explicitly
- If verification fails, explain which check failed and why
- Never fill gaps with speculation — flag them as gaps instead
