<!-- Canonical summary for the current repository state. -->

# CiteAgent Summary

## Canonical Source Of Truth

This repository contains the CiteAgent research agent runtime — a
TypeScript-native MCP server and the v12 contract set.

Use this precedence order when there is a conflict:

1. `instruction/contracts/*.md` and `instruction/contracts/*.yaml`
2. This file: `instruction/Summary.md`
3. The current implementation under `plugins/opencode-citeagent/`

The following paths are **legacy reference material**, not current source of
truth:

- `instruction/backup/`
- `.agent/`
- `citeindex-rs/` (deleted — Rust kernel is a future goal, not current code)

Those files are still useful for historical context and for understanding the
older design, but they should not override the v12 contracts.

## Current Architecture

CiteAgent is a TypeScript-native research agent runtime that connects to AI
coding tools (OpenCode, Claude Code, Codex, Cursor, Cline, Windsurf) via the
Model Context Protocol (MCP). No Python runtime is required.

- **CiteAgentEngine** (`plugins/opencode-citeagent/src/engine/`): The research
  agent — BM25 search (MiniSearch), RAG chat, Merkle integrity verification,
  JSONL memory store, audit trail, CSL citation rendering. Implements all 25 MCP
  tools in pure TypeScript.
- **CiteIndex CLI** (separate PyPI package, optional sidecar): The ingestion
  engine — PDF, URL, media ingestion with GROBID, MinerU, DSPy, Merkle
  verification. Only needed for `cite_ingest` document ingestion; not required
  at runtime.
- **OpenCode plugin** (`plugins/opencode-citeagent/`): TypeScript/Bun plugin
  that hosts the CiteAgentEngine, provides SafeHarness security hooks, and
  verification ladders. Also provides MCP configs for Claude Code, Codex,
  Cursor, Cline, and Windsurf.

### MCP Server

Start a standalone stdio MCP server with:

```bash
bunx @ephremyuan/citeagent mcp-server
```

This works with every MCP-compatible client.

## Current Repository Reality

The repository is no longer in transition. The Python `citeagent/` package has
been **completely removed**. All runtime code is TypeScript-native.

- `plugins/opencode-citeagent/` is the **entire runtime** — it contains the
  CiteAgentEngine, the 7-stage deterministic agent pipeline, the MCP server
  (25 tools), MiniSearch BM25 indexes, and all agent definitions.
- Ingestion is handled by the **separate `citeindex` PyPI package** (v0.12.0+),
  invoked as an optional CLI sidecar for `cite_ingest` only. It is not a
  runtime dependency.
- There is no `citeagent/` Python directory, no `pyproject.toml`,
  no `v12_runtime.py`, and no `tantivy_index.py`.

## Package Layout

```
plugins/opencode-citeagent/
├── src/
│   ├── engine/
│   │   ├── index.ts           # CiteAgentEngine — public API entry point
│   │   ├── agents/
│   │   │   ├── corpus_loader.ts   # Corpus loading
│   │   │   ├── query_planner.ts   # Intent detection + query planning
│   │   │   ├── retrieval.ts       # 3-stage BM25 retrieval (MiniSearch)
│   │   │   ├── clarification.ts   # Ambiguity handling
│   │   │   ├── generation.ts      # Extractive + LLM answer generation
│   │   │   ├── integrity.ts       # 4-check fail-closed Merkle verification
│   │   │   ├── memory.ts         # JSONL-backed memory store
│   │   │   └── models.ts         # Type definitions
│   │   ├── mcp/
│   │   │   └── server.ts         # MCP server (25 tools)
│   │   ├── search.ts             # SearchPipeline
│   │   ├── chat.ts               # ChatPipeline
│   │   └── ...                   # Supporting modules
│   └── plugin.ts                 # OpenCode plugin registration
├── bin/
│   └── mcp-server.ts             # Standalone MCP server binary
├── package.json
└── tsconfig.json
```

## Agent Pipeline

Seven deterministic agents run in sequence:

1. **corpus_loader** — loads and validates the document corpus
2. **query_planner** — detects intent and plans retrieval queries
3. **retrieval** — 3-stage BM25 search via MiniSearch
4. **clarification** — handles ambiguous or under-specified queries
5. **generation** — extractive and LLM-based answer generation
6. **integrity** — 4-check fail-closed Merkle verification
7. **memory** — JSONL-backed persistent memory with audit trail

## Major Design Decisions

- Retrieval is deterministic and BM25-based at runtime, powered by MiniSearch
  (pure TypeScript). No Tantivy or native index dependency.
- The ArgumentGraph contract specifies **SQLite** (not JSON files) —
  `ag_write_edge` is deferred to future Rust kernel implementation.
- ACE Scholar Adaptation remains part of the v12 direction.
- Skill packs replace the older plugin-centric direction as the main extension
  model.
- Ingestion is handled by the **separate `citeindex` package** (Python sidecar),
  invoked only for `cite_ingest`. Not a runtime dependency.
- SafeHarness retains layers 1 (Inform/sanitize) and 2 (Verify/tiered check) and
  3 (Constrain/permission). Layer 4 (Correct/rollback) is deferred.
- CSL citation rendering is done natively in TypeScript — no Python
  `citeproc-py` dependency.

## Removed Components

The following were removed as part of the v0.4.0 refactor:

- `ag_write_edge` MCP tool (stub → deferred to Rust kernel)
- `safeharness_checkpoint`, `safeharness_rollback`, `safeharness_status` (no
  real rollback implementation)
- `memory_summarize` (was concatenation-only, no LLM summarization)
- `StructureAgent` (no real argument structure analysis)
- All ingestion code (delegated to `citeindex` package as optional sidecar)
- **Entire Python `citeagent/` package** — replaced by TypeScript-native
  CiteAgentEngine
- `pyproject.toml`, `v12_runtime.py`, `tantivy_index.py`, and all Python sources
- Shared Python utility modules (citation_style, llm, model, utils, etc.)

## Near-Term Implementation Direction

1. Keep the v12 contracts canonical.
2. Align contract docs with actual architectural decisions.
3. Implement remaining v12 agents with real LLM logic (claim extraction,
   contradiction detection, gap identification, hierarchy classification).
4. Build out MiniSearch index population at ingest time.
5. Consider SQLite-backed argument graph when `ag_write_edge` is needed.