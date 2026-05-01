<p align="center">
  <img src="./Citation-Extractor-logo.PNG" alt="CiteAgent Logo" width="150">
</p>

<h1 align="center">CiteAgent</h1>

<p align="center">
  <strong>An AI research agent that never hallucinates — every claim is traced, verified, and cited.</strong>
</p>

<p align="center">
  <a href="#why-this-exists">Why</a> •
  <a href="#current-status">Current Status</a> •
  <a href="#how-it-works">How It Works</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#usage">Usage</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#contributing">Contributing</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.12+-blue.svg" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT">
  <img src="https://img.shields.io/pypi/v/citeindex.svg" alt="PyPI version">
  <img src="https://img.shields.io/npm/v/@ephremyuan/citeagent.svg" alt="npm version">
</p>

---

## Why This Exists

Large Language Models write fluently but **cannot cite their sources**. When an LLM tells you about a study, a historical event, or a legal precedent, there is no way to verify the claim, trace it back to a page, or reproduce the evidence chain. For scholars, this makes LLM output fundamentally unusable in serious work.

**CiteAgent is an AI research agent — like Claude Code, but for academic scholarship.** Instead of writing code, it reads your research materials, indexes them into a Merkle-verified knowledge base, and answers your questions with deterministic, trace-bound citations. Every claim maps to a specific text passage, verified by cryptographic hash, with a full Merkle proof from leaf node to document root.

### What CiteAgent does for researchers

- **Ingests any source** — PDFs (digital or scanned), URLs, DJVU, EPUB, DOCX, video/audio — into a structured, hash-verified corpus.
- **Answers questions** with Chicago author-date citations, where every inline reference traces to a specific passage in your documents.
- **Eliminates hallucination** by design: BM25 deterministic retrieval (no embeddings), mandatory evidence-to-claim mapping, and fail-closed integrity verification.
- **Handles CJK vertical text**, multi-column layouts, footnote isolation, and scanned documents with automatic OCR language detection.

---

## Current Status

The live execution path runs on the v12 NDJSON agent runtime, powered by the `citeagent` Python package and `citeindex` ingestion engine.

- **`citeagent`** (v0.4.0) — the research agent runtime: 7-stage search/chat pipeline, MCP server with 27 tools, Tantivy full-text indexes, integrity verification, memory, and agent orchestration.
- **`citeindex`** (v0.12.0+) — the ingestion engine (separate PyPI package): PDF, URL, media, DJVU, Office document ingestion with GROBID, MinerU, DSPy, and Merkle verification.
- The OpenCode plugin (`@ephremyuan/citeagent` v0.3.8 on npm) provides 5 specialized agents, skills, rules, and SafeHarness security hooks.
- MCP server runs as `python3 -m citeagent.mcp_server` and works with Claude Code, Codex, Cursor, Cline, and Windsurf.

---

## How It Works

CiteAgent enforces a strict contract: **no claim without evidence, no evidence without a hash, no hash without a Merkle proof.**

```
Document → Ingest → Nodes (paragraph/line) → SHA-256 hashes → Merkle tree
                                                    ↓
Query → BM25 Retrieval → Ranked Evidence → Generation (LLM or extractive)
                                                    ↓
                                          Integrity Verifier (fail-closed)
                                                    ↓
                                          Answer + Chicago citations + Merkle proofs
```

**7 deterministic agents** form the pipeline:

1. **Ingestion** — Parse documents into structural nodes with hierarchical Merkle trees
2. **Indexing** — Build inverted index, section index, and cross-source links
3. **Query Planning** — Classify intent, detect ambiguity, emit search plan
4. **Retrieval** — Three-stage BM25: metadata filter → keyword search → trace filter
5. **Clarification** — Ask up to 3 questions when the query is ambiguous
6. **Generation** — Produce answers strictly from evidence, with Chicago citations
7. **Integrity** — Recompute hashes, verify Merkle proofs, resolve citation keys. Reject if any check fails.

---

## Quick Start

See [**install.md**](./install.md) for the full installation guide (human + LLM agent instructions, model selection, and troubleshooting).

### Installation

```bash
# CiteAgent — research agent runtime + MCP server
uv tool install citeagent

# CiteIndex — ingestion engine (required for cite_ingest)
uv tool install citeindex

# OpenCode plugin — agents, skills, hooks (recommended for OpenCode users)
bunx @ephremyuan/citeagent@latest install
```

> **`uv tool install`** provides isolated, globally-available CLI tools without polluting your system Python. No venv needed — `uv` manages its own environments under `~/.local/share/uv/tools/`. The OpenCode plugin auto-detects this path.

> **See [plugins/opencode-citeagent/README.md](./plugins/opencode-citeagent/README.md)** for full plugin details — agents, tools, architecture, and uninstall steps.

### Use with Claude Code, Codex, Cursor, and other MCP clients

CiteAgent's Python backend (`citeagent.mcp_server`) is a **standard MCP server** that works with any MCP-compatible tool — not just OpenCode.

> **Full setup guide for all tools:** [mcp-setup.md](./mcp-setup.md)

Quick configs:

**Claude Code** (`.mcp.json` at repo root, or `claude mcp add`):
```json
{
  "mcpServers": {
    "citeagent": {
      "command": "python3",
      "args": ["-m", "citeagent.mcp_server"],
      "env": { "CITEAGENT_CORPUS_ROOT": "${PWD}/corpus" }
    }
  }
}
```

**Codex CLI** (`~/.codex/config.toml`):
```toml
[mcp_servers.citeagent]
command = "python3"
args = ["-m", "citeagent.mcp_server"]
env = { CITEAGENT_CORPUS_ROOT = "./corpus" }
enabled = true
```

**Cursor** (`.cursor/mcp.json`), **Cline**, **Windsurf** — same `python3 -m citeagent.mcp_server` pattern. See [mcp-setup.md](./mcp-setup.md) for exact file paths and formats.

### System Dependencies

```bash
# Ubuntu/Debian
sudo apt-get install tesseract-ocr mediainfo ffmpeg

# macOS
brew install tesseract mediainfo ffmpeg

# LLM backend (required for chat/generation)
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull qwen3
```

### Optional Services

```bash
# GROBID — primary citation extraction (recommended)
docker run -d -p 8070:8070 lfoppiano/grobid:0.8.1

# Playwright browsers — for JS-rendered URL fetching
playwright install chromium

# Zotero translation-server — rich URL metadata
docker run -d -p 1969:1969 zotero/translation-server
```

---

## Usage

### Ingest documents

```bash
# Ingest a PDF into the corpus (uses citeindex CLI)
citeindex ingest "research-paper.pdf"

# Scanned PDF with auto-detected OCR language
citeindex ingest "scanned-book.pdf" --lang auto

# Vertical CJK text
citeindex ingest "chinese-manuscript.pdf" --text-direction vertical

# Primary source (line-level granularity)
citeindex ingest "ancient-text.pdf" --is-primary

# URL article
citeindex ingest "https://www.nature.com/articles/s41586-023-06627-7"
```

### Search your corpus

```bash
# BM25 deterministic search
citeagent search "Kantian categorical imperative"

# Return more results
citeagent search "machine learning fairness" --top-k 50
```

### Chat with trace-bound citations

```bash
# Single-shot question
citeagent chat --prompt "What does the author argue about social contract theory?"

# Interactive chat session
citeagent chat

# Specify LLM backend
citeagent chat --llm ollama/qwen3 --prompt "Compare the two authors' positions on free will"
```

### Memory

```bash
# Search past conversations
citeagent memory search "social contract"

# List memory threads
citeagent memory list
```

### First run and migration behavior

On first run against an existing legacy `corpus/`, CiteAgent will:

1. Create `corpus/.citeindex/`.
2. Import legacy corpus artifacts and legacy memory logs into the v12 store.
3. Mark that bootstrap as complete so later requests run directly from `.citeindex`.

For new work, use normal ingest commands or the CLI. Do not add new documents manually into the old legacy `corpus/{folder}/` layout if you expect them to appear automatically after migration.

---

## OpenCode Plugin

The `@ephremyuan/citeagent` npm package is an **OpenCode-specific plugin** that adds:

- **5 specialized agents** — researcher, verifier, explore-corpus, ingestor, reviewer
- **27 MCP tools** — `cite_search`, `cite_verify`, `cite_ingest`, `cite_render`, `cite_tree`, `cite_regex_search`, `cite_delete_document`, `cite_tantivy_search`, `cite_tantivy_index`, `cite_memory_*`, and more
- **3 built-in MCP servers** — websearch (Exa), context7 (docs), grep_app (code search) — auto-connected
- **Skill & rule assets** auto-deployed on install
- **Hooks** — SafeHarness (sanitize + permission tiers), verification ladder (L0–L4), crypto audit chain

### Install for OpenCode

```bash
bunx @ephremyuan/citeagent@latest install
```

This auto-detects Python, checks for `citeagent` and `citeindex` packages, deploys agent configs, skills, and rules to `~/.config/opencode/`, and adds the plugin to your OpenCode config.

### Install for Claude Code

Add to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "citeagent": {
      "command": "python3",
      "args": ["-m", "citeagent.mcp_server"],
      "env": { "CITEAGENT_CORPUS_ROOT": "${PWD}/corpus" }
    }
  }
}
```

Or via CLI: `claude mcp add --transport stdio citeagent -- python3 -m citeagent.mcp_server`

### Install for Codex CLI

```bash
codex mcp add citeagent -- python3 -m citeagent.mcp_server
```

### Install for Cursor, Cline, Windsurf

See [mcp-setup.md](./mcp-setup.md) for exact config file paths and JSON formats.

> The OpenCode plugin provides the richest experience (agents, skills, hooks). Other MCP clients connect directly to the Python server.

---

## Architecture

CiteAgent is a **Python + TypeScript** system with an **OpenCode plugin** layer:

| Layer | Language | Role |
|-------|----------|------|
| **OpenCode Plugin** | TypeScript (npm) | MCP bridge, skill/rule deployment, agent configs, SafeHarness security hooks |
| **AI Engine & MCP Server** | Python (`citeagent`) | Agent adapters, chat/search logic, Tantivy indexes, integrity verification, MCP server |
| **Ingestion Engine** | Python (`citeindex`) | PDF, URL, media ingestion, GROBID, MinerU, DSPy, Merkle verification |
| **Storage** | Files + Tantivy indexes | Persistent store under `corpus/.citeindex/` with Tantivy full-text search |

### Key design rules

- **No embeddings.** All retrieval is BM25 keyword search — deterministic and reproducible.
- **Merkle-verified.** Every text node has a SHA-256 hash. Document integrity is a Merkle tree: `line → paragraph → column → page → document`.
- **Fail-closed integrity.** The integrity verifier rejects answers where any hash, Merkle proof, or citation key fails to resolve.
- **Citation cascade.** GROBID (deterministic) → LLM extraction (fallback) → PDF metadata (last resort).

### Corpus layout

```
corpus/
├── .citeindex/
│   ├── indexes/
│   │   ├── document_index/
│   │   ├── memory_index/
│   │   └── claim_index/
│   ├── documents/
│   │   ├── sources/
│   │   ├── structured/
│   │   └── transcripts/
│   └── memory/
│       └── sessions/
└── {legacy-folder}/
    ├── csl.json
    ├── document.json
    └── merkle.json
```

The `.citeindex/` tree is now the runtime source of truth. The legacy folders remain supported for migration and compatibility.

---

## Contributing

```bash
git clone https://github.com/Areopaguaworkshop/citeagent.git
cd citeagent

# Development setup with uv
uv tool install -e ".[dev]"
pytest
```

Contributions welcome — especially for:
- Additional citation styles beyond Chicago
- Language-specific OCR improvements
- New ingestion pipelines (e.g., EPUB, LaTeX)
- MCP server enhancements

## License

MIT License

---

## Citing CiteAgent

If you use CiteAgent in academic work, please cite:

```bibtex
@software{citeagent2025,
  author = {Yuan, Ephrem},
  title = {CiteAgent: AI Research Agent with Merkle-Verified Retrieval and Citation-Indexed Search},
  year = {2025},
  url = {https://github.com/Areopaguaworkshop/citeagent},
  note = {Python package: citeagent v0.4.0, citeindex v0.12.0, npm package: @ephremyuan/citeagent v0.3.8}
}
```

---

<p align="center">
  <em>Every claim deserves a source. Every source deserves a hash. Every hash deserves a proof.</em>
</p>
