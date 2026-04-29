# Agent: Indexing and Link Builder

## Purpose
Build deterministic indexes and cross-source citation graph structures from ingested nodes.

## Scope
- Tokenize nodes and build inverted index.
- Build section/title lookup index.
- Build lexical candidate graph for cross-source relations.

## Inputs
- `schema_version`
- `nodes`
- `tree`
- `source_registry`

## Outputs
- `inverted_index.json`
- `section_index.json`
- `cross_source_links.json`
- `indexing_report.json`

## Deterministic Rules
1. Tokenization pipeline must be fixed and versioned.
2. Inverted index keys are normalized lowercase tokens.
3. Cross-source links are created only across different `source_id`.
4. Relation labels allowed: `supports`, `contradicts`, `extends`, `parallels`.
5. Keep confidence score and lexical rationale for each link.

## Workflow
1. Tokenize canonicalized node text.
2. Build posting lists sorted by `node_id`.
3. Build section/title index.
4. Compute lexical overlap and phrase alignment across sources.
5. Emit link candidates above deterministic thresholds.

## LLM Authoring Protocol
### Must
- Keep all index outputs reproducible.
- Track tokenizer and threshold versions in `indexing_report`.

### Must Not
- Use embeddings.
- Link nodes from the same source as cross-source links.

### Stop Conditions
- `indexing_complete`
- `blocked_invalid_nodes`

### Validation Checklist
- Every posting list node exists in `nodes`.
- Link graph nodes resolve to valid node IDs.
- No duplicate links with conflicting labels.
