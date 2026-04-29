# Citation Format Rules

## Default Style
Chicago author-date format via `cite_render` tool. Other styles (APA, MLA, Vancouver) available on request.

## Inline Citation Format
> Quoted text from source
> — [Author Year] (node: `s5.1.p5`, hash: `abc123...`)

## Evidence Chain Format
Every answer with citations must include a machine-readable evidence section:

```json
{
  "evidence": [
    {
      "node_id": "s5.1.p5",
      "source_id": "Author2023Title",
      "sha256": "abc123...",
      "merkle_proof": ["leaf_hash", "...", "root_hash"],
      "citation_key": "Author2023Title",
      "citation_rendered": "Author, A. (2023). Title. Journal, 1(2), 3–4.",
      "verification": "approved"
    }
  ]
}
```

## Rules
- Always use `cite_render` tool for formatting — never format citations manually
- Include SHA-256 hash truncated to first 12 characters in inline citations
- Node IDs follow format: s{section}.{subsection}.p{paragraph}
- Merkle proofs are arrays of sibling hashes from leaf to root
- If verification status is "rejected", the evidence item MUST be excluded from the final answer
