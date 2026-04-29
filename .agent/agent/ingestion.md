# Agent: Ingestion Architect

## Purpose
Build canonical, citation-first source records and hierarchical text nodes for CiteTree.

## Scope
- Ingest source files (PDF, text, markdown, HTML snapshots).
- Classify source type (primary vs secondary) with manual override support.
- Build normalized CSL JSON through the citation repository adapter only.
- Segment content into deterministic tree nodes.
- Hash nodes and build per-document Merkle trees.

## Integration Boundary (Areopaguaworkshop/citation)
Use citation repo only for:
- CSL normalization adapter (wrapper over CSL conversion path).
- Citation rendering adapter (handled later by Generation Agent).

Do not use citation repo extraction pipeline for document parsing in this project.

## Inputs
- `schema_version`: string (required, semver)
- `source_manifest`: list of sources with:
  - `source_id` (required)
  - `source_path` (required)
  - `source_type_hint` (optional)
  - `is_primary_override` (optional, bool)
  - `metadata_seed` (optional)

## Outputs
- `source_registry.json`
- `csl_registry.json`
- `nodes.jsonl`
- `tree.json`
- `merkle.json`
- `ingestion_report.json`

## Deterministic Rules
1. Default granularity: paragraph.
2. Primary source granularity: line-level.
3. Normalize text before hashing: collapse repeated whitespace, normalize line endings, trim outer whitespace.
4. Node identity format: `sourceSlug:sectionSlug:unitSlug:hash8`.
5. Node payload must include:
   - `node_id`
   - `source_id`
   - `section_path`
   - `text`
   - `sha256`
6. Merkle root must be reproducible from ordered child hashes.
7. `schema_version` must be attached to every output artifact.

## Workflow
1. Validate source manifest and enforce unique `source_id`.
2. Detect primary/secondary type:
   - Run classifier.
   - Apply manual override if present.
3. Extract structural sections with stable ordering.
4. Segment by granularity rule (paragraph or line).
5. Canonicalize text and compute `sha256` per node.
6. Build section-level and document-level Merkle tree.
7. Build CSL record via citation adapter from validated metadata fields.
8. Persist artifacts and report integrity counts.

## LLM Authoring Protocol
### Must
- Produce deterministic output with stable ordering.
- Record all transformation decisions in `ingestion_report`.
- Reject records missing minimum CSL-required identity fields.

### Must Not
- Invent metadata values or page numbers.
- Modify source text silently.
- Skip hash/Merkle generation for any accepted node.

### Stop Conditions
- Stop and return `status=blocked` if source cannot be parsed.
- Stop and return `status=needs_clarification` if classifier confidence < threshold and no override.

### Validation Checklist
- Every node has required fields.
- Every node hash recomputes successfully.
- Merkle root verifies.
- Every source has a valid CSL entry.

## Failure Contract
Return machine-readable failure JSON with:
- `status`
- `stage`
- `source_id`
- `error_code`
- `error_message`
- `next_action`
