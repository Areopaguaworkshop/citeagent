<!-- Canonical summary for the current repository state. -->

# CiteAgent Summary

## Canonical Source Of Truth

This repository contains the CiteAgent research agent runtime and the v12
contract set.

Use this precedence order when there is a conflict:

1. `instruction/contracts/*.md` and `instruction/contracts/*.yaml`
2. This file: `instruction/Summary.md`
3. The current implementation under `citeagent/`

The following paths are **legacy reference material**, not current source of
truth:

- `instruction/backup/`
- `.agent/`
- `citeindex-rs/` (deleted — Rust kernel is a future goal, not current code)

Those files are still useful for historical context and for understanding the
older design, but they should not override the v12 contracts.

## Current Architecture

CiteAgent is a Python research agent runtime that connects to AI coding tools
(OpenCode, Claude Code, Codex) via the Model Context Protocol (MCP).

- **CiteAgent** (`citeagent/`): The research agent — search, RAG chat, integrity
  verification, memory, Tantivy indexes, MCP server. Depends on `citeindex` for
  ingestion.
- **CiteIndex** (separate PyPI package): The ingestion engine — PDF, URL, media
  ingestion with GROBID, MinerU, DSPy, Merkle verification. Installed as a
  dependency.
- **OpenCode plugin** (`plugins/opencode-citeagent/`): TypeScript/Bun plugin
  that spawns the Python MCP server, adds SafeHarness security hooks and
  verification ladders. Also provides Claude Code and Codex MCP configs.

## Current Repository Reality

The repository is no longer in transition.

- `citeindex-rs/` has been **removed** — the Rust kernel is a future goal, not
  current code.
- `citeagent/` (formerly `citeindex/`) is the **full agent runtime** — it
  contains the 7-stage search/chat pipeline, v12 NDJSON agent runtime, MCP
  server (27 tools), Tantivy full-text indexes, and all agent definitions.
- Ingestion has been **delegated** to the separate `citeindex` PyPI package
  (v0.12.0+). CiteAgent imports `citeindex.CiteIndexIngestionOrchestrator` and
  `citeindex.IngestionConfig` for document ingestion.
- The MCP server runs as `python3 -m citeagent.mcp_server`.

## Package Layout

```
citeagent/
├── __init__.py          # Public API: SearchPipeline, ChatPipeline, IntegrityVerifier
├── cli.py               # CLI: citeagent ingest/search/chat/memory
├── mcp_server.py        # MCP server (27 tools)
├── tantivy_index.py     # Tantivy full-text indexes (document, claim, memory)
└── agents/
    ├── chat.py          # ChatPipeline + SearchPipeline
    ├── corpus_loader.py # Corpus loading
    ├── indexing.py       # BM25 inverted index
    ├── query_planner.py # Intent detection + query planning
    ├── retrieval.py     # 3-stage BM25 retrieval
    ├── clarification.py # Ambiguity handling
    ├── generation.py    # Extractive + LLM answer generation
    ├── integrity.py     # 4-check fail-closed integrity verification
    ├── memory.py        # JSONL-backed memory store
    ├── models.py         # Dataclass definitions
    ├── pageindex_retrieval.py # LLM-driven tree search
    ├── v12_runtime.py   # NDJSON protocol adapter (9 agents)
    └── ...               # Agent entry-point stubs
```

## Major Design Decisions

- Retrieval is deterministic and BM25-based at runtime, with Tantivy as a
  complementary full-text index layer.
- The ArgumentGraph contract specifies **SQLite** (not JSON files) — `ag_write_edge`
  is deferred to future Rust kernel implementation.
- ACE Scholar Adaptation remains part of the v12 direction.
- Skill packs replace the older plugin-centric direction as the main extension
  model.
- Ingestion is handled by the **separate `citeindex` package**, not in-repo.
- SafeHarness retains layers 1 (Inform/sanitize) and 2 (Verify/tiered check) and
  3 (Constrain/permission). Layer 4 (Correct/rollback) is deferred.

## Removed Components

The following were removed as part of the v0.4.0 refactor:

- `ag_write_edge` MCP tool (stub → deferred to Rust kernel)
- `safeharness_checkpoint`, `safeharness_rollback`, `safeharness_status` (no
  real rollback implementation)
- `memory_summarize` (was concatenation-only, no LLM summarization)
- `StructureAgent` (no real argument structure analysis)
- All ingestion code (delegated to `citeindex` package)
- Shared utility modules (citation_style, llm, model, utils, etc.)

## Near-Term Implementation Direction

1. Keep the v12 contracts canonical.
2. Align contract docs with actual architectural decisions.
3. Implement remaining v12 agents with real LLM logic (claim extraction,
   contradiction detection, gap identification, hierarchy classification).
4. Build out Tantivy index population at ingest time.
5. Consider SQLite-backed argument graph when `ag_write_edge` is needed.