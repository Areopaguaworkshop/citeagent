# @ephremyuan/citeagent

OpenCode plugin for CiteAgent — AI research knowledge infrastructure with Merkle-verified retrieval, citation-indexed search, and trace-bound chat.

## Install

```bash
bunx @ephremyuan/citeagent@latest install
```

The installer automatically:
- Adds the plugin to `~/.config/opencode/opencode.jsonc`
- Deploys skills to `~/.config/opencode/skills/`
- Deploys agent configs to `~/.config/opencode/agents/`
- Deploys rules to `~/.config/opencode/rules/`
- Generates agent model mappings in `~/.config/opencode/citeagent.json`

### Options

| Flag | Description |
|------|-------------|
| `--reset` | Overwrite existing configuration |
| `--dry-run` | Simulate install without writing files |

## Prerequisites

```bash
# Optional: citeindex CLI for document ingestion (PDF, URL, media)
# If not installed, cite_ingest/cite_tantivy_index will warn but other tools work fine
uv tool install citeindex

# Optional: OCR support
sudo apt install tesseract-ocr

# Optional: LLM backend (for chat/generation)
# https://ollama.ai
```

> No Python runtime required — all citation tools run natively in TypeScript.

## Uninstall

1. Remove `"@ephremyuan/citeagent"` from `~/.config/opencode/opencode.jsonc` `plugin` array
2. Remove config: `rm ~/.config/opencode/citeagent.json`
3. Remove assets: `rm ~/.config/opencode/skills/citeagent-*.md ~/.config/opencode/agents/citeagent-*.md ~/.config/opencode/rules/citeagent-*.md`

## Agents

| Agent | Mode | Description |
|-------|------|-------------|
| `citeagent-researcher` | primary | Academic research with citation-verified evidence |
| `citeagent-verifier` | subagent (hidden) | Independent Merkle proof audit |
| `citeagent-explore-corpus` | subagent (hidden) | Fast corpus search and browsing |
| `citeagent-ingestor` | subagent (hidden) | Document ingestion (PDF, URL, media) |
| `citeagent-reviewer` | subagent (hidden) | Reproducible structured corpus review |

## Tools

The plugin provides 25+ tools via the native TypeScript CiteAgentEngine:

- `cite_search` — BM25 full-text search
- `cite_verify` — Merkle proof verification
- `cite_bibliographic_verify` — opt-in DOI/title existence check through Crossref
- `cite_node_lookup` — exact passage retrieval for claim-to-evidence audits
- `cite_render` — CSL citation rendering (Chicago, APA, MLA...)
- `cite_ingest` — Document ingestion with Merkle hashing
- `cite_tree` / `cite_tree_traverse` — PageIndex document tree
- `cite_argument_query` — Argument graph (claims, contradictions)
- `cite_memory_*` — 4-tier persistent memory (working → episodic → long_term → corpus)
- And more (see source)

## Architecture

```
User question
     │
     ▼
citeagent-researcher (OpenCode agent)
     │
     ├── cite_search ──→ CiteAgentEngine (TypeScript, in-process)
     ├── cite_verify ──→ CiteAgentEngine
     ├── cite_ingest ──→ citeindex CLI (optional sidecar)
     │
     ├── @citeagent-explore-corpus (OpenCode subagent)
     └── @citeagent-verifier (OpenCode subagent)
```

All tools except `cite_ingest`/`cite_tantivy_index` run natively in TypeScript — no Python subprocess or MCP stdio bridge required. The engine reads the on-disk corpus directly and implements BM25 search (MiniSearch), Merkle verification, CSL rendering, memory store, and audit trail in-process.

## License

MIT
