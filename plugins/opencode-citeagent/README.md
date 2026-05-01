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
# Required: Python + citeindex (via uv tool — isolated, no venv needed)
uv tool install citeagent
uv tool install citeindex

# Verify
python3 -c "import citeagent" && citeindex --version

# Optional: OCR support
sudo apt install tesseract-ocr

# Optional: LLM backend (for chat/generation)
# https://ollama.ai
```

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
| `citeagent-reviewer` | subagent (hidden) | Systematic literature review |

## Tools

The plugin provides 25+ tools via MCP bridge to the Python backend:

- `cite_search` — BM25 full-text search
- `cite_verify` — Merkle proof verification
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
     ├── cite_search ──→ Retrieval agent (Python/MCP)
     ├── cite_verify ──→ Integrity agent (Python/MCP)
     ├── cite_ingest ──→ Ingestion agent (Python/MCP)
     │
     ├── @citeagent-explore-corpus (OpenCode subagent)
     └── @citeagent-verifier (OpenCode subagent)
```

The plugin spawns `python3 -m citeagent.mcp_server` as a subprocess and communicates via MCP over stdio. The OpenCode plugin auto-detects the Python runtime from `uv tool install` paths.

## License

MIT
