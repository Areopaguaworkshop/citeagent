# CiteAgent Project Report

> **Version**: 0.5.0 (npm plugin, TS-native engine) | **Updated**: 2026-08-30
> **Status**: Active development — TypeScript-native primary runtime with document ingestion delegated to the optional Python `citeindex` CLI.

---

## 1. What CiteAgent Is

CiteAgent is an **AI research agent for academic scholars** that enforces a strict contract: **no claim without evidence, no evidence without a hash, no hash without a Merkle proof.** It ingests research documents, indexes them into a Merkle-verified knowledge base, and answers queries with deterministic, trace-bound citations mapped to specific text passages verified by cryptographic hash.

Think of it as "Claude Code for academic scholarship" — instead of writing code, it reads your research materials and provides citation-grounded answers.

**Runs entirely in TypeScript.** No Python required. The `bunx @ephremyuan/citeagent mcp-server` command starts an MCP stdio server that works with any MCP-compatible tool (Claude Code, Codex, Cursor, Cline, Windsurf, OpenCode). Only document ingestion (`cite_ingest`) shells out to the `citeindex` CLI as an optional sidecar.

### Key Value Propositions

| Promise | Mechanism |
|---------|-----------|
| **Unsupported-claim reduction** | BM25 deterministic retrieval (no embeddings), evidence-to-claim mapping, fail-closed integrity checks |
| **Verifiable citations** | Every claim maps to a SHA-256 hashed text node with a full Merkle proof from leaf → document root |
| **CJK-first** | Vertical text detection, CJK phrase preservation in search, pinyin indexing, auto-OCR language detection |
| **Multi-format ingestion** | PDF (digital/scanned), URL, DJVU, EPUB, DOCX, video/audio — via separate `citeindex` package |

---

## 2. Architecture

### 2.1 Layered Design

```
┌──────────────────────────────────────────────────────────────────┐
│  MCP Clients (Claude Code, Codex, Cursor, Cline, Windsurf)     │
│  ↳ bunx @ephremyuan/citeagent mcp-server (TypeScript-native)   │
├──────────────────────────────────────────────────────────────────┤
│  OpenCode Plugin Layer (TypeScript / npm)                        │
│  @ephremyuan/citeagent v0.5.0                                    │
│  CiteAgentEngine (native TS; ingestion uses a CLI subprocess),  │
│  SafeHarness hooks, skill/rule deployment, 5 agent configs      │
├──────────────────────────────────────────────────────────────────┤
│  AI Engine (TypeScript CiteAgentEngine only)                      │
│  41 tools: scoped search, workflows, integrity checks, passage   │
│  lookup, memory, crypto, audit, argument graph, PageIndex, etc.  │
│  All run natively in TS. Only cite_ingest shells out to CLI.    │
├──────────────────────────────────────────────────────────────────┤
│  Ingestion Engine (Python / citeindex CLI — sidecar only)         │
│  PDF, URL, media ingestion with GROBID, MinerU, DSPy,           │
│  Merkle verification, CSL normalization, schema validation       │
│  Called via `citeindex` CLI subprocess from TS engine             │
├──────────────────────────────────────────────────────────────────┤
│  Storage (Files + MiniSearch index)                              │
│  corpus/.citeindex/ with document_index, claim_index,          │
│  memory_index (MiniSearch BM25) + JSONL memory + JSON artifacts  │
└──────────────────────────────────────────────────────────────────┘
```

| Layer | Language | Package | Role |
|-------|----------|---------|------|
| **MCP Server** | TypeScript | `@ephremyuan/citeagent` (npm) | stdio MCP server via `bunx @ephremyuan/citeagent mcp-server` |
| **CiteAgentEngine** | TypeScript | Built into npm package | Native TS implementation of 41 tools; ingestion remains an optional `citeindex` CLI integration |
| **Ingestion** | Python | `citeindex` CLI (sidecar, optional) | PDF/URL/media ingestion — called as subprocess from TS engine |
| **Storage** | Files + MiniSearch | — | `corpus/.citeindex/` with MiniSearch full-text search + JSONL memory |

### 2.2 The 7-Agent Search Pipeline

```
Query → CorpusLoader → IndexingAgent → QueryPlanner → RetrievalAgent
                                                          ↓
                                               ClarificationAgent (if ambiguous)
                                                          ↓
                                               GenerationAgent → IntegrityVerifier
                                                          ↓
                                               Answer + Chicago citations + Merkle proofs
```

| Agent | Mechanism | Status |
|-------|-----------|--------|
| **CorpusLoader** | Walks corpus, loads csl.json/document.json/merkle.json | ✅ Real |
| **IndexingAgent** | `simple_v1` tokenizer (CJK-aware), BM25 postings | ✅ Real |
| **QueryPlanner** | Heuristic intent detection, CJK phrase preservation | ✅ Real |
| **RetrievalAgent** | 3-stage: metadata filter → BM25 (k1=1.2, b=0.75) → trace filter | ✅ Real |
| **ClarificationAgent** | LLM-generated questions when query ambiguous | ✅ Real |
| **GenerationAgent** | Extractive (default) or LLM-based; Chicago citations | ✅ Real |
| **IntegrityVerifier** | 4-check fail-closed: node exists, hash match, Merkle proof, citation resolved | ✅ Real |

### 2.3 Paper-scoped workflow and local state

Each research paper gets a metadata-only workspace with approved source IDs,
source roles, and an audit record. Retrieval and exact-passage lookup are
scoped to the active paper. The checkpointed workflow (`research` → `outline`
→ `draft` → `review`) fails closed without verified evidence and stores only
local session metadata under `.citeagent/` (ignored by git). No corpus text,
private paths, credentials, or source-derived outputs are packaged or logged.

### 2.4 v12 NDJSON Agent Runtime (Removed)

> **Note:** The `v12_runtime.py` module was a Python-only component that bridged 9 agent adapters over a stdin/stdout JSONL protocol with crash recovery. It has been **removed** along with the entire Python package. The TypeScript `CiteAgentEngine` does **not** use a v12 runtime; it implements the 7 deterministic search-pipeline agents directly in TypeScript (see §2.2 above).

---

## 3. Package Layout

> **Note:** The Python `citeagent/` package has been removed. All functionality now runs natively in TypeScript via the `CiteAgentEngine`.

### 3.1 TypeScript Plugin (`plugins/opencode-citeagent/`)

```
plugins/opencode-citeagent/
├── package.json             # @ephremyuan/citeagent v0.5.0
├── bin/install.ts           # Plugin installer
├── src/
│   ├── index.ts             # Plugin entry point
│   ├── mcp-bridge.ts        # MCP stdio bridge for external MCP clients
│   ├── safeharness.ts       # SafeHarness security hooks
│   ├── verification.ts      # Verification ladder (L0-L4)
│   ├── ltl-monitor.ts       # Linear temporal logic monitor
│   ├── crypto.ts            # Crypto operations
│   ├── memory.ts            # Memory store
│   ├── types.ts             # TypeScript type definitions
│   ├── tools/index.ts       # Tool definitions
│   ├── hooks/index.ts       # Hook system
│   └── engine/
│       ├── index.ts         # CiteAgentEngine (native TS BM25 via MiniSearch)
│       ├── merkle.ts        # Merkle tree (TS implementation)
│       ├── search.ts        # Search engine
│       ├── pageindex.ts     # PageIndex tree
│       ├── corpus-loader.ts # Corpus loader
│       ├── crypto-engine.ts # Crypto engine
│       ├── audit-store.ts   # Audit storage
│       ├── workspaces.ts     # Paper workspaces and approved source scope
│       ├── workflow.ts       # Checkpointed research workflow
│       ├── research-state.ts # Local session metadata
│       ├── argument-graph.ts # Argument graph
│       ├── csl.ts           # CSL processing
│       └── memory-store.ts  # Memory store
├── assets/
│   ├── agents/              # 5 agent configs (researcher, verifier, explore-corpus, ingestor, reviewer)
│   ├── skills/              # 3 skills (ingest-document, literature-review, verify-evidence)
│   └── rules/               # 2 rules (academic-integrity, citation-format)
└── dist/                    # Built output
```

### 3.3 Docs & Configuration

```
docs/
├── project-report.md        # This report
├── citeagent-audit-report.md # Detailed stub/partial implementation audit
└── plans/
    ├── 2026-04-30-citeagent-refactor.md
    └── 2026-05-01-citeagent-ts-native.md

.agent/                      # Legacy agent definitions (YAML schemas, pipelines)
.opencode/                    # OpenCode agent/skill/rule configs
instruction/Summary.md        # Canonical project summary
mcp-setup.md                 # MCP client setup for Claude Code, Codex, Cursor, Cline, Windsurf
install.md                   # Installation guide (human + LLM agent)
Agent.md                     # Behavioral guidelines (Karpathy-inspired)
```

---

## 4. MCP Server — Tool Inventory

The MCP server (`bunx @ephremyuan/citeagent mcp-server`) exposes **29 tools** via the TypeScript-native `CiteAgentEngine`:

### Fully Implemented

| Tool | Handler | Mechanism |
|------|---------|-----------|
| `search_documents` | `_handle_search_documents` | BM25 via `SearchPipeline` |
| `search_claims` | `_handle_search_claims` | v12 `ClaimExtractionAgent` adapter (regex) |
| `search_memory` | `_handle_search_memory` | `MemoryStore.search()` |
| `index_document` | `_handle_index_document` | `CiteIndexIngestionOrchestrator.ingest()` |
| `delete_document` | `_handle_delete_document` | `shutil.rmtree` + cache reset |
| `regex_search` | `_handle_regex_search` | `re.compile` over corpus nodes |
| `merkle_compute` | `_handle_merkle_compute` | `citeindex.ingestion.deterministic` |
| `merkle_verify` | `_handle_merkle_verify` | SHA-256 proof walk + corpus cross-check |
| `csl_render` | `_handle_csl_render` | `citeproc-py` formatting |
| `bibliographic_verify` | `verifyBibliographicRecord` | Opt-in Crossref DOI/title existence check |
| `node_lookup` | `CiteAgentEngine.callTool` | Exact corpus passage and provenance lookup |
| `tree_load` | `_handle_tree_load` | `PageIndexRetrievalAgent._load_trees()` |
| `tree_traverse` | `_handle_tree_traverse` | `PageIndexRetrievalAgent._find_node_in_tree()` |
| `memory_save` | `_handle_memory_save` | `MemoryStore.save()` |
| `tantivy_search` | `_handle_tantivy_search` | `TantivyManager.search_documents()` |
| `tantivy_index` | `_handle_tantivy_index` | Ingest via `CiteIndexIngestionOrchestrator` + `TantivyManager.index_document()` |
| `audit_save` | `_handle_audit_save` | JSON file in `corpus/.audits/` |
| `audit_retrieve` | `_handle_audit_retrieve` | JSON file read |
| `memory_store_tier` | `_handle_memory_store_tier` | JSONL per tier (working/episodic/long_term) |
| `memory_retrieve_tier` | `_handle_memory_retrieve_tier` | Substring search over tier JSONL |
| `memory_consolidate` | `_handle_memory_consolidate` | Move episodic → long-term, dedupe by hash |
| `crypto_sign` | `_handle_crypto_sign` | HMAC-SHA256 per session |
| `crypto_verify` | `_handle_crypto_verify` | HMAC-SHA256 verification |
| `crypto_audit_trail` | `_handle_crypto_audit_trail` | Hash chain integrity check |
| `safeharness_check` | `_handle_safeharness_check` | 3-layer: sanitize → verify → constrain |
| `safeharness_sanitize` | `_handle_safeharness_sanitize` | Input sanitization (trim + redact) |
| `index_claim` | `_handle_index_claim` | v12 `ClaimExtractionAgent` adapter |
| `ag_query_claims` | `_handle_ag_query_claims` | Corpus node lookup |  ⚠️ Partial |
| `ag_query_contradictions` | `_handle_ag_query_contradictions` | v12 `ContradictionAgent` (duplicate-only) | ⚠️ Partial |

### Removed (v0.4.0 refactor)

| Tool | Reason |
|------|--------|
| `ag_write_edge` | No persistent argument graph — deferred to Rust kernel |
| `safeharness_checkpoint` | No real rollback implementation |
| `safeharness_rollback` | No real rollback implementation |
| `safeharness_status` | No real rollback implementation |
| `memory_summarize` | Was concatenation-only, no LLM summarization |

---

## 5. Implementation Status Matrix

### Fully Real & Working

| System | Evidence |
|--------|----------|
| 7-agent chat pipeline (`ChatPipeline`) | 8-step pipeline: load→index→plan→clarify→retrieve→generate→verify→save memory |
| BM25 search (`SearchPipeline`) | Full BM25(k1=1.2, b=0.75) with metadata filtering, phrase boosts, section boosts |
| Tantivy full-text search | `TantivyManager` with 3 indexes (document, claim, memory) via `tantivy-py` |
| Corpus loading / indexing | `CorpusLoader` walks corpus, loads nodes; `IndexingAgent` builds inverted index |
| Regex search | Real `re.compile` search over corpus nodes |
| Document deletion | `shutil.rmtree` + cache reset |
| Integrity verification | 4-check fail-closed: node exists, hash match, Merkle proof, citation resolved |
| Memory persistence (JSONL) | 4-tier model (working/episodic/long_term/corpus), keyword search |
| PageIndex tree building | Vendored PageIndex + Ollama. Full TOC detection, tree construction |
| PageIndex retrieval | LLM-driven tree navigation as alternative to BM25 |
| CSL citation rendering | `citeproc-py` with bundled styles |
| Crypto (HMAC) | HMAC-SHA256 signing, verification, audit trail chain |
| SafeHarness | Input sanitization, tier classification, result checks; OpenCode owns user approvals |
| ~~v12 runtime protocol~~ | Removed — TS engine implements 7 agents directly (no JSONL bridge) |
| Ingestion (all 4 pipelines) | Real end-to-end — via `citeindex` CLI sidecar (optional) |
| MCP server | 29 handlers; release check runs typecheck, tests, and builds |

### Partial / Needs LLM Logic

| System | Current | Missing |
|--------|---------|---------|
| Claim Extraction | Regex sentence splitting | LLM-based semantic claim decomposition, polarity classification, NER |
| Contradiction Detection | Exact duplicate text match | Semantic contradiction detection, LLM reasoning, edge weights |
| Gap Identification | Threshold comparison (`coverage_score < threshold`) | Semantic gap analysis, cross-source comparison, actionable suggestions |
| Hierarchy Classification | 3 hardcoded keyword sets → 3 paths | LLM-based LCC/DDC classification, multi-label, domain-aware |

### Deferred / Removed

| System | Status | Reason |
|--------|--------|--------|
| Argument graph persistence (SQLite) | `ag_write_edge` removed | No persistent store without Rust kernel |
| SafeHarness L4 (rollback) | Handlers removed | No real rollback implementation |
| Memory summarization | Handler removed | Was concatenation-only |
| StructureAgent | Deleted | No real argument structure analysis |
| Embeddings / Vector search | Not present | Design decision (deterministic-only) |
| PostgreSQL memory | JSONL only | Acceptable for MVP |
| Rust kernel (`citeindex-rs/`) | Deleted from repo | Future goal, not current code |

---

## 6. Corpus Layout

```
corpus/
├── .citeindex/
│   ├── indexes/
│   │   ├── document_index/      # Tantivy: doc_id, title, author, abstract, body, source_type, language, merkle_root, citation_key, doi
│   │   ├── claim_index/         # Tantivy: claim_id, doc_id, claim_text, polarity_tag, hierarchy_path
│   │   └── memory_index/        # Tantivy: memory_id, content, thread_id, tier, sha256
│   ├── documents/
│   │   ├── sources/             # Original PDFs (immutable)
│   │   ├── structured/          # PageIndex trees (.citeindex.json)
│   │   └── transcripts/         # Media transcripts (.transcript.json)
│   ├── memory/
│   │   ├── episodic/            # Per-thread JSONL
│   │   └── long_term/           # Consolidated JSONL
│   └── .audits/                 # Audit results (JSON)
├── .crypto/                     # HMAC session keys + audit trails
├── .memory/                     # Legacy memory (JSONL)
└── {source-folder}/             # Legacy per-document folders
    ├── csl.json
    ├── document.json
    ├── merkle.json
    └── ingestion_output.json
```

The `.citeindex/` tree is the **runtime source of truth**. Legacy folders remain for migration and compatibility.

---

## 7. Dependencies

> **Note:** The Python `citeagent` package has been removed. All runtime dependencies are now TypeScript-only.

### TypeScript Plugin (`@ephremyuan/citeagent` v0.5.0)

| Dependency | Version | Purpose |
|------------|---------|---------|
| `@opencode-ai/plugin` | 1.14.30 | OpenCode plugin SDK |
| `@modelcontextprotocol/sdk` | ^1.29.0 | MCP server + client SDK |
| `zod` | ^3.23.0 | Schema validation |
| `minisearch` | ^7.1.0 | Client-side BM25 search engine |

### Python Sidecar (optional — for `cite_ingest` only)

| Dependency | Version | Purpose |
|------------|---------|---------|
| `citeindex` | ≥ 0.12.0 | Ingestion engine (PDF, URL, media, Merkle) |

### External Services (Optional)

| Service | URL | Purpose | Fallback? |
|---------|-----|---------|-----------|
| **Ollama** | localhost:11434 | LLM for DSPy extraction, PageIndex, generation | Yes → extractive mode |
| **GROBID** | localhost:8070 | Deterministic PDF metadata + references | Yes → LLM extraction |
| **MinerU CLI** | `magic-pdf` on PATH | PDF layout analysis | Yes → fitz layout |
| **Zotero translator** | localhost:1969 | Rich URL metadata | Yes → trafilatura |
| **Playwright** | citeindex sidecar only | JS-rendered URL fetching (citeindex dependency, not CiteAgent) | Yes → requests |
| **yt-dlp** | on PATH | Media download | No → fails |
| **ffmpeg** | on PATH | Audio extraction | No → no transcript |

---

## 8. CLI Commands

```bash
# Ingest documents (delegates to citeindex)
citeagent ingest "paper.pdf"
citeagent ingest "scanned.pdf" --lang auto
citeagent ingest "chinese.pdf" --text-direction vertical
citeagent ingest "https://example.com/article" --all-url-article

# Search corpus (BM25 or PageIndex reasoning)
citeagent search "Kantian categorical imperative"
citeagent search "fairness" --top-k 50 --retrieval pageindex

# Chat with trace-bound citations
citeagent chat --prompt "What does the author argue about social contract theory?"
citeagent chat --llm ollama/qwen3

# Memory management
citeagent memory search "social contract"
citeagent memory list

# Plugin management
citeagent plugin install /path/to/plugin
citeagent plugin list
```

---

## 9. MCP Client Integration

CiteAgent's MCP server works with any MCP-compatible tool:

| Client | Config Location | Config Format |
|--------|----------------|---------------|
| **Claude Code** | `.mcp.json` (project) or `claude mcp add` | JSON |
| **Codex CLI** | `~/.codex/config.toml` | TOML |
| **Cursor** | `.cursor/mcp.json` | JSON |
| **Cline** | `cline_mcp_settings.json` | JSON |
| **Windsurf** | `~/.codeium/windsurf/mcp_config.json` | JSON |
| **OpenCode** | `bunx @ephremyuan/citeagent@latest install` | Auto-configured |

See `mcp-setup.md` for exact file paths and configurations.

---

## 10. Design Principles

1. **No embeddings** — All retrieval is BM25 keyword search, deterministic and reproducible
2. **Merkle-verified** — Every text node has SHA-256; document integrity is a Merkle tree: `line → paragraph → column → page → document`
3. **Fail-closed integrity** — Any hash/Merkle/citation check failure → reject the entire answer
4. **Citation cascade** — GROBID (deterministic) → DSPy+LLM (fallback) → PDF metadata (last resort)
5. **7 deterministic agents** — Fixed pipeline, no dynamic agent chaining
6. **CJK-first** — Vertical text detection, CJK phrase preservation in search, pinyin indexing
7. **Source-of-truth hierarchy** — Contracts → Summary → Implementation → Legacy
8. **Graceful degradation** — Every external service has a fallback path

---

## 11. Test Coverage

| Area | Tests | Location |
|------|-------|----------|
| ~~Bibliography formatting~~ ~~Citation extraction~~ ~~LLM extraction~~ ~~CJK phrase search~~ ~~v12 runtime~~ | Removed with Python package | ~~`citeagent/tests/`~~ (deleted) |
| Plugin engine (TS) | merkle, search, crypto-engine, csl, corpus-loader, memory-store (jest) | `plugins/opencode-citeagent/src/engine/` |
| Integration | 27 MCP handler smoke test | Manual |

> **Note:** All Python test files (`test_style.py`, `test_citation.py`, `test_llm_extraction.py`, `test_search_cjk_phrase.py`, `test_v12_runtime.py`) were removed along with the `citeagent/` Python package. TypeScript unit/integration tests for the `CiteAgentEngine` should be written to cover equivalent functionality.

**Gap**: No formal CI/CD pipeline detected. Tests must be run manually.

---

## 12. Known Gaps & Priority

| Priority | Item | Status |
|---------|------|--------|
| **P1 — High** | Claim extraction (LLM-based) | Regex-only |
| **P1 — High** | Argument graph persistence (SQLite) | `ag_write_edge` removed; deferred to Rust kernel |
| **P2 — Medium** | Contradiction detection (LLM-based) | Duplicate detection only |
| **P2 — Medium** | CI/CD pipeline | None |
| **P3 — Low** | Hierarchy classification (LLM-based) | 3-keyword classifier |
| **P3 — Low** | Gap identification (LLM-based) | Threshold comparison |
| **P3 — Low** | SafeHarness L4 (rollback) | Removed |
| **P3 — Low** | Memory summarization | Removed |
| **P4 — Deferred** | Embeddings/vector search | Design decision (deterministic-only) |
| **P4 — Deferred** | PostgreSQL memory | JSONL fine for MVP |
| **P4 — Deferred** | Rust kernel | Future goal |

---

## 13. Near-Term Direction

Per `instruction/Summary.md`:

1. Keep the v12 contracts canonical
2. Implement remaining v12 agents with real LLM logic (claim extraction, contradiction detection, gap identification, hierarchy classification)
3. Build out Tantivy index population at ingest time
4. Consider SQLite-backed argument graph when `ag_write_edge` is needed
5. Additional citation styles beyond Chicago
6. Language-specific OCR improvements
7. New ingestion pipelines (e.g., EPUB, LaTeX)

---

*Report generated from project source analysis. Last updated: 2026-08-29.*
