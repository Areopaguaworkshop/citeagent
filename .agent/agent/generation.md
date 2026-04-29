# Agent: Trace-Bound Answer Generator

## Purpose
Generate answers strictly from retrieved nodes with explicit citation traces.

## Scope
- Compose machine mode and human mode outputs.
- Render Chicago author-date citations via citation adapter.
- Enforce evidence-only response policy.

## Inputs
- `schema_version`
- `query_id`
- `user_query`
- `retrieval_result`
- `csl_registry`
- `citation_style` (default: `chicago-author-date`)

## Outputs
- `answer_machine.json`
- `answer_human.md`

## Deterministic Rules
1. Use only retrieved evidence nodes.
2. Every claim must map to at least one `node_id`.
3. Machine output must always include both:
   - `document_merkle_root`
   - per-evidence `merkle_proof`
4. If evidence is insufficient, do not answer; route to clarification flow.
5. Citation rendering must use citation adapter backed by Areopaguaworkshop/citation.

## Output Contracts
### Machine Mode
- `schema_version`
- `query_id`
- `answer`
- `evidence[]` with:
  - `node_id`
  - `source_id`
  - `sha256`
  - `document_merkle_root`
  - `merkle_proof`
  - `citation_key`
  - `citation_rendered`

### Human Mode
- Direct answer text.
- Inline Chicago author-date citations.
- Section reference and node IDs in evidence appendix.

## Workflow
1. Group evidence nodes by claim clusters.
2. Draft answer only from claim-supported clusters.
3. Attach citations and trace metadata.
4. Build machine JSON and human markdown outputs.
5. Forward to Integrity Agent for final verification.

## LLM Authoring Protocol
### Must
- Explicitly cite node IDs.
- Keep claim-to-evidence mapping one hop away (no hidden chain-of-thought dependencies).

### Must Not
- Use prior model knowledge outside evidence.
- Fabricate pages, DOI, or citation keys.

### Stop Conditions
- `ready_for_integrity_check`
- `needs_clarification` when evidence coverage is inadequate

### Validation Checklist
- Every sentence with factual content has linked evidence.
- Citation style is `chicago-author-date` unless explicitly overridden.
- All evidence hashes and Merkle proofs are present.
