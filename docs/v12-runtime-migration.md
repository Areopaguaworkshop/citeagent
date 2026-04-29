# v12 Runtime Migration Status

## Summary

The live execution path has been migrated from legacy one-shot Python CLI subprocesses to the v12 NDJSON agent runtime.

The runtime source of truth is now the persistent v12 store under `corpus/.citeindex/`.

## Completed

- Rust core/TUI drives long-lived Python agents over the v12 NDJSON protocol.
- Chat, search, and ingest run through the runtime bridge instead of `python -m citeindex.cli` subprocess calls.
- Kernel-backed search uses Tantivy through the runtime tool loop.
- Chat retrieval and memory use kernel tools (`search_memory`, `tantivy_search`, `tree_load`, `tree_traverse`, `memory_save`).
- Structured `.citeindex.json` trees are persisted for newly ingested documents.
- Real source artifacts are persisted into `corpus/.citeindex/documents/sources/` for local-file ingests and remote snapshots.
- Transcript artifacts are persisted into `corpus/.citeindex/documents/transcripts/` when available.
- Session memory is persisted into `corpus/.citeindex/memory/sessions/`.

## Legacy Compatibility

Legacy compatibility is still present.

- On startup, CiteIndex prepares `corpus/.citeindex/` from legacy `corpus/*/csl.json`, `document.json`, `merkle.json`, and `corpus/.memory/*.jsonl` if the migration marker is not present yet.
- Core memory reads still merge the v12 session log directory with legacy `.memory` entries so old chat history remains visible.
- After startup preparation completes, live requests do not rescan legacy files during each tool call.

## What "Done" Means

The runtime migration is effectively done for day-to-day use:

- New ingests write the v12 store directly enough for chat/search/runtime execution.
- Existing legacy corpora are imported forward into the v12 store on startup.
- Live request handling now operates from `.citeindex` instead of rebuilding transient runtime state.

## Remaining Transitional Edges

- The startup compatibility import is still the bridge for old legacy corpora; it has not been replaced by a separate explicit migration command yet.
- If someone manually adds new files into the old legacy `corpus/{folder}/` layout after the migration marker already exists, those new legacy additions will not be picked up automatically.

## How To Use It

### Existing legacy corpus

1. Keep your existing `corpus/` directory in place.
2. Start the Rust app:

```bash
cd citeindex-rs
cargo run
```

3. On first startup, CiteIndex will create `corpus/.citeindex/` and import the legacy corpus and memory logs.
4. After that, use the TUI or normal ingest commands for new content.

### New content

Use ingest normally:

```bash
citeindex ingest "my-paper.pdf"
citeindex ingest "https://example.com/article"
```

New content will persist into the v12 store and be available to the runtime without depending on the old legacy folder layout.

## Recommended Practice

- Treat `corpus/.citeindex/` as the runtime source of truth.
- Treat the old legacy `corpus/{folder}/` layout as compatibility input, not the preferred place for new manual additions.
- For anything new, ingest through the application rather than copying files directly into legacy folders.
