# Agent: Deterministic Retrieval and Search

## Purpose
Retrieve auditable evidence nodes without embeddings.

## Scope
- Execute hybrid deterministic retrieval policy.
- Return ranked evidence with complete trace metadata.
- Build optional cross-source link candidates with richer relation labels.

## Inputs
- `schema_version`
- `resolved_query_plan`
- `source_registry`
- `csl_registry`
- `inverted_index`
- `tree_index`
- `nodes`

## Outputs
- `retrieval_result.json`:
  - `query_id`
  - `ranked_nodes`
  - `candidate_relations`
  - `retrieval_debug`

## Deterministic Rules
1. Retrieval policy is fixed:
   - Stage 1: CSL metadata filters.
   - Stage 2: BM25 over indexed node text.
   - Stage 3: strict trace filter (drop nodes with incomplete provenance).
2. Tie-break order:
   - exact phrase hits
   - section-title match
   - depth priority
   - node_id lexical order
3. Never use embeddings or semantic vector stores.
4. Each returned node must include:
   - `node_id`, `source_id`, `section_path`, `sha256`, `score_breakdown`
5. Candidate cross-source relations allowed in v1:
   - `supports`, `contradicts`, `extends`, `parallels`

## Workflow
1. Apply must/should filters from query plan.
2. Run BM25 on candidate nodes.
3. Apply phrase and section boosts.
4. Enforce trace filter and deduplicate by `node_id`.
5. Build relation candidates across high-overlap nodes.
6. Emit top-k evidence package.

## LLM Authoring Protocol
### Must
- Return score components transparently.
- Emit deterministic ordering.
- Mark relation confidence and rationale for each candidate link.

### Must Not
- Use non-indexed text.
- Return nodes missing hash or source linkage.

### Stop Conditions
- `retrieval_complete`
- `insufficient_evidence`

### Validation Checklist
- All evidence node_ids exist in index.
- All hashes verify against node payload.
- Relation candidates include source and target node IDs.
