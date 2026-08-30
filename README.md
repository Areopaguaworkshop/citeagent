<p align="center">
  <img src="./Citation-Extractor-logo.PNG" alt="CiteAgent Logo" width="150">
</p>

<h1 align="center">CiteAgent</h1>

<p align="center">
  <strong>A local, evidence-first academic agent layer for Codex and OpenCode.</strong>
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
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT">
  <img src="https://img.shields.io/badge/bun-%3E%3D1.0-blue.svg" alt="Bun">
  <img src="https://img.shields.io/badge/typescript-5.0+-blue.svg" alt="TypeScript">
  <img src="https://img.shields.io/npm/v/@ephremyuan/citeagent.svg" alt="npm version">
</p>

---

## An academic agent, not an autonomous scholar

Large Language Models write fluently but **cannot cite their sources**. When an LLM tells you about a study, a historical event, or a legal precedent, there is no way to verify the claim, trace it back to a page, or reproduce the evidence chain. For scholars, this makes LLM output fundamentally unusable in serious work.

**CiteAgent is the academic-paper counterpart to an agent layer such as oh-my-opencode.** It makes Codex and OpenCode useful inside a scholar's local research workspace: they can search approved sources, capture exact passages, check citations, and advance a paper through explicit checkpoints. The scholar remains responsible for questions, interpretation, source approval, authorship, and publication.

It is not a general OpenCode plugin with a research feature. Version 0.5.0 is a host-native academic-agent distribution: OpenCode receives its agents, skills, rules, and hooks; Codex receives the same research capability through a native MCP server. Both use one local, evidence-first engine.

### What CiteAgent does for researchers

- **Ingests any source** — PDFs (digital or scanned), URLs, DJVU, EPUB, DOCX, video/audio — into a structured, hash-verified corpus.
- **Answers questions** from approved local sources, with Chicago author-date citations that trace to exact passages.
- **Reduces unsupported claims** with deterministic BM25 retrieval, evidence-to-claim mapping, and fail-closed integrity checks.
- **Keeps paper work local** — metadata-only paper workspaces, source approvals, workflow state, and audits stay on disk; no corpus text is copied into workspace metadata.
- **Handles CJK vertical text**, multi-column layouts, footnote isolation, and scanned documents with automatic OCR language detection.

---

## Current Status

- **`@ephremyuan/citeagent`** (v0.5.0) — host-native academic-agent layer for Codex and OpenCode: 41 MCP tools, paper-scoped retrieval, checkpointed workflows, specialist agents, skills, rules, and SafeHarness hooks. Document ingestion optionally invokes the Python `citeindex` CLI.
- **`citeindex`** (v0.12.0+ on PyPI) — the ingestion engine (optional sidecar): PDF, URL, media, DJVU, Office document ingestion with GROBID, MinerU, DSPy, and Merkle verification.
- MCP server runs as `bunx @ephremyuan/citeagent mcp-server` and works with Claude Code, Codex, Cursor, Cline, Windsurf, and OpenCode.

---

## Documentation

| Document | Description |
|----------|-------------|
| [**install.md**](./install.md) | Full installation guide — Bun-only, no Python needed |
| [**mcp-setup.md**](./mcp-setup.md) | MCP client setup for Claude Code, Codex, Cursor, Cline, Windsurf |
| [**docs/project-report.md**](./docs/project-report.md) | Comprehensive project report — architecture, implementation status, tool inventory |
| [**docs/citeagent-audit-report.md**](./docs/citeagent-audit-report.md) | Detailed audit — migration phases, stub/partial implementations, priority assessment |
| [**PRIVACY.md**](./PRIVACY.md) | Public-release data boundary and local-state policy |
| [**CHANGELOG.md**](./CHANGELOG.md) | Release history, changes, and fixes |

---

## How academic work moves through CiteAgent

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

The engine is evidence-first; it does not turn search results or model memory into paper evidence:

1. **Create a paper workspace** — record the research question and activate one paper.
2. **Approve sources** — add only permitted local corpus IDs to that paper.
3. **Retrieve and verify** — search is constrained to approved sources; exact passages, hashes, and Merkle proofs can be checked.
4. **Checkpoint work** — progress through research → outline → draft → review with `proceed`, `refine`, or `abort` choices.
5. **Keep authorship with the host and scholar** — CiteAgent records and gates the workflow; the host may prepare prose only after the scholar approves the relevant checkpoint. When evidence is absent or altered, startup fails closed and reports the next action.

---

## Quick Start

See [**install.md**](./install.md) for the full installation guide.

### Installation

```bash
# CiteAgent — runs natively in TypeScript, no Python needed
bunx @ephremyuan/citeagent@latest install

# CiteIndex — ingestion engine (optional, for cite_ingest only)
uv tool install citeindex
```

> **No Python required for 39 of 41 tools.** Document ingestion tools optionally invoke the `citeindex` CLI. The `bunx @ephremyuan/citeagent mcp-server` command starts an MCP stdio server that works with any MCP-compatible tool.

### Use natively with Codex or OpenCode

CiteAgent provides a **TypeScript-native MCP server** — no Python required unless using document ingestion, which invokes the optional `citeindex` CLI.

> **Full setup guide for all tools:** [mcp-setup.md](./mcp-setup.md)

Quick configs (all clients use the same `bunx @ephremyuan/citeagent mcp-server` command):

**Claude Code** (`.mcp.json` at repo root, or `claude mcp add`):
```json
{
  "mcpServers": {
    "citeagent": {
      "command": "bunx",
      "args": ["@ephremyuan/citeagent", "mcp-server"],
      "env": { "CITEAGENT_CORPUS_ROOT": "${PWD}/corpus" }
    }
  }
}
```

**Codex CLI** (`~/.codex/config.toml`):
```toml
[mcp_servers.citeagent]
command = "bunx"
args = ["@ephremyuan/citeagent", "mcp-server"]
env = { CITEAGENT_CORPUS_ROOT = "./corpus" }
enabled = true
```

**Cursor** (`.cursor/mcp.json`), **Cline**, **Windsurf** — same `bunx @ephremyuan/citeagent mcp-server` pattern. See [mcp-setup.md](./mcp-setup.md) for exact file paths and formats.

### System Dependencies

```bash
# Bun (required — runs the MCP server)
curl -fsSL https://bun.sh/install | bash

# citeindex CLI (optional — for document ingestion only)
uv tool install citeindex

# OCR support (optional — for scanned PDFs via citeindex)
sudo apt-get install tesseract-ocr mediainfo ffmpeg    # Ubuntu/Debian
brew install tesseract mediainfo ffmpeg                 # macOS

# LLM backend (optional — for chat/generation)
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull qwen3
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

Use any MCP client (Claude Code, Codex, Cursor, OpenCode) with the `search_documents` tool, or the CiteAgent plugin's `cite_search` tool.

### Research with trace-bound citations

In Codex, use the MCP tools directly. In OpenCode, use the installed academic agents and skills. Both paths call the same local engine and evidence policy.

### Paper-scoped, checkpointed research

Create a metadata-only paper workspace, approve its corpus sources, and activate
it. While active, `cite_search` returns results only from approved source IDs.
No source text is copied into the workspace.

```text
paper_create    paper_id="my-paper" title="…" question="…"
paper_add_source paper_id="my-paper" source_id="local-source-id" role="primary"
paper_use       paper_id="my-paper"
workflow_start  topic="…"
workflow_resume workflow_id="…" choice="proceed"
```

Use `status` and `doctor` to inspect configuration without reading corpus text.
Use `state_record_session` only for opt-in local session metadata. See
[PRIVACY.md](./PRIVACY.md) for the release and data boundary.

### Workflow contract

`workflow_start` requires an active paper, at least one approved source that is
currently in the corpus, and at least one scoped result whose text hash and
Merkle proof verify. It then returns a checkpoint at `research`.

| Stage | `workflow_resume(..., "proceed")` | Other choices |
|---|---|---|
| `research` | advances to `outline` | `refine` repeats the checkpoint; `abort` deletes it |
| `outline` | advances to `draft` | `refine` repeats the checkpoint; `abort` deletes it |
| `draft` | advances to `review` | `refine` repeats the checkpoint; `abort` deletes it |
| `review` | completes and removes the workflow record | `refine` repeats the checkpoint; `abort` deletes it |

Workflow records are local, serialized for concurrent calls, and expire after
one hour. `paper_status`, `paper_audit`, `state_wake_up`, `state_snapshot`,
and `status` provide the corresponding metadata without returning corpus text.

---

## Host integrations

The npm package provides two native host surfaces:

1. **Codex and other MCP hosts** — `bunx @ephremyuan/citeagent mcp-server` exposes the academic engine directly.
2. **OpenCode** — `bunx @ephremyuan/citeagent install` adds academic agents, skills, rules, and hooks around that engine.

The plugin adds:
- **5 specialized agents** — researcher, verifier, explore-corpus, ingestor, reviewer
- **41 MCP tools** — `cite_search`, `cite_verify`, `cite_bibliographic_verify`, `cite_node_lookup`, `cite_ingest`, `cite_render`, `cite_tree`, `cite_regex_search`, `cite_paper_*`, `cite_workflow_*`, `cite_state_*`, `cite_status`, `cite_doctor`, and more
- **3 built-in MCP servers** — websearch (Exa), context7 (docs), grep_app (code search) — auto-connected
- **Skill & rule assets** auto-deployed on install
- **Hooks** — SafeHarness input sanitization and tier diagnostics, verification ladder (L0–L4), crypto audit chain

### Install the OpenCode academic-agent layer

```bash
bunx @ephremyuan/citeagent@latest install
```

This deploys agent configs, skills, and rules to `~/.config/opencode/`, and adds the plugin to your OpenCode config. No Python needed.

### Connect Codex and other MCP hosts

All use the same `bunx @ephremyuan/citeagent mcp-server` command. See [mcp-setup.md](./mcp-setup.md) for exact configurations.

---

## Architecture

CiteAgent is a **TypeScript-native academic-agent layer** with an **optional Python sidecar** for ingestion. The host is the interface; the local workspace and evidence policy are the product boundary.

| Layer | Language | Package | Role |
|-------|----------|---------|------|
| **Host surface** | TypeScript | `@ephremyuan/citeagent` (npm) | MCP server for Codex and compatible clients; native assets for OpenCode |
| **Academic engine** | TypeScript | Built into npm package | 41 tools: paper scope, BM25 retrieval, checkpoints, Merkle/bibliographic verification, exact-passage lookup, CSL, memory, crypto, and audit |
| **Academic guidance** | Markdown + TypeScript | npm assets | Researcher, verifier, ingestor, reviewer, and corpus-explorer instructions; skills, rules, and SafeHarness hooks |
| **Ingestion** | Python | `citeindex` (PyPI, sidecar) | PDF/URL/media ingestion — called via CLI subprocess |
| **Local paper state** | Files + MiniSearch | — | `corpus/.citeindex/` plus gitignored `.citeagent/` metadata, workflows, sessions, and audits |

### Key design rules

- **No embeddings.** All retrieval is BM25 keyword search — deterministic and reproducible.
- **Merkle-verified.** Every text node has a SHA-256 hash. Document integrity is a Merkle tree: `line → paragraph → column → page → document`.
- **Fail-closed integrity.** The integrity verifier rejects answers where any hash, Merkle proof, or citation key fails to resolve.
- **Scholar-controlled scope.** Only sources explicitly approved for the active paper are retrieved; workflow checkpoints require an explicit choice.
- **Local-first boundary.** Workspace metadata and session state are local. Operational diagnostics avoid returning corpus text.
- **Workflow is orchestration, not authorship.** CiteAgent gates verified research state for Codex or OpenCode; it does not claim scholarly authority or autonomously publish a paper.
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
└── {source-folder}/
    ├── csl.json
    ├── document.json
    └── merkle.json
```

---

## Contributing

```bash
git clone https://github.com/Areopaguaworkshop/citeagent.git
cd citeagent

# TypeScript plugin (primary development)
cd plugins/opencode-citeagent
bun install
bun run build:all
bun test

# Ingestion engine (separate repo)
# See https://github.com/Areopaguaworkshop/citeindex
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
  note = {npm package: @ephremyuan/citeagent v0.5.0, Python sidecar: citeindex v0.12.0}
}
```

---

<p align="center">
  <em>Every claim deserves a source. Every source deserves a hash. Every hash deserves a proof.</em>
</p>
