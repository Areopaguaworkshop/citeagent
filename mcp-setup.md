# CiteAgent MCP Setup Guide

> **No Python required.** CiteAgent's MCP server runs natively in TypeScript via `bunx`. All tools execute in-process — only `cite_ingest` (document ingestion) optionally shells out to the `citeindex` CLI.

## What CiteAgent Gives You

Once connected, you get tools for Merkle-verified academic research plus built-in web search and code search:

### CiteAgent Tools (TypeScript-native MCP server)

| Tool | What it does |
|------|-------------|
| `search_documents` | BM25 full-text search on your academic corpus |
| `search_claims` | Search claims in the argument graph |
| `search_memory` | Search persisted memory entries |
| `index_document` | Ingest a document (PDF, URL, media) into the corpus |
| `index_claim` | Index a claim extracted from a document |
| `delete_document` | Delete a document and associated data |
| `ag_query_claims` | Query claims from the argument graph |
| `ag_query_contradictions` | Find contradictions in the argument graph |
| `merkle_compute` | Compute Merkle tree hashes for a payload |
| `merkle_verify` | Verify a Merkle proof against a known root hash |
| `csl_render` | Render CSL citation to formatted bibliography (Chicago, APA, MLA…) |
| `tree_load` | Load PageIndex tree for a document |
| `tree_traverse` | Traverse PageIndex tree to a given depth |
| `regex_search` | Regex-based search on document nodes |
| `memory_save` | Save to persistent memory store |
| `memory_store_tier` | Store in a specific tier (working/episodic/long_term/corpus) |
| `memory_retrieve_tier` | Retrieve from a specific tier |
| `memory_consolidate` | Consolidate episodic → long-term |
| `tantivy_search` | Full-text search (uses BM25 engine) |
| `tantivy_index` | Index a document in full-text search |
| `audit_save` | Save an audit result (verdict + evidence hashes) |
| `audit_retrieve` | Retrieve a saved audit result |
| `crypto_sign` | Sign a message (HMAC-SHA256) |
| `crypto_verify` | Verify an HMAC-SHA256 signature |
| `crypto_audit_trail` | Return the audit chain for a session |
| `safeharness_check` | Run SafeHarness security layers on a tool call |
| `safeharness_sanitize` | Sanitize input for a tool call |

### Built-in MCP Servers (OpenCode plugin only)

When using the OpenCode plugin, these are auto-connected alongside CiteAgent:

| Server | Tool | What it does | Auth |
|--------|------|-------------|------|
| **websearch** | `web_search_exa` | Web search via Exa AI (or Tavily) | `EXA_API_KEY` or `TAVILY_API_KEY` |
| **context7** | `resolve-library-id` | Library/package documentation lookup | Optional `CONTEXT7_API_KEY` |
| **grep_app** | `search_code` | Search code across open-source GitHub repos | None |

> **Note:** For non-OpenCode MCP clients, add these MCP servers separately if desired.

---

## Prerequisites

### Required (TypeScript-native — no Python)

```bash
# Install Bun (if not already installed)
curl -fsSL https://bun.sh/install | bash

# Install the CiteAgent plugin (includes MCP server)
bunx @ephremyuan/citeagent@latest install
```

### Optional — for document ingestion only

```bash
# citeindex CLI (needed only for cite_ingest / cite_tantivy_index)
uv tool install citeindex
```

> **All other tools run natively in TypeScript.** No Python subprocess, no MCP stdio bridge to Python. The engine reads the on-disk corpus directly.

### Optional services

```bash
# OCR support (for scanned PDFs via citeindex)
sudo apt install tesseract-ocr        # Ubuntu/Debian
brew install tesseract                # macOS

# LLM backend (for chat/generation)
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull qwen3
```

---

## Add to Your Tool

### Recommended: TypeScript-native MCP server (all clients)

The `bunx @ephremyuan/citeagent mcp-server` command starts a standard MCP stdio server. Works with **any** MCP-compatible tool.

**Claude Code** (`.mcp.json` at repo root):

```json
{
  "mcpServers": {
    "citeagent": {
      "command": "bunx",
      "args": ["@ephremyuan/citeagent", "mcp-server"],
      "env": {
        "CITEAGENT_CORPUS_ROOT": "${PWD}/corpus"
      }
    }
  }
}
```

Or via CLI:

```bash
claude mcp add --transport stdio citeagent -- bunx @ephremyuan/citeagent mcp-server
```

**Codex CLI** (`~/.codex/config.toml`):

```toml
[mcp_servers.citeagent]
command = "bunx"
args = ["@ephremyuan/citeagent", "mcp-server"]
env = { CITEAGENT_CORPUS_ROOT = "./corpus" }
enabled = true
```

**Cursor** (`.cursor/mcp.json` at repo root):

```json
{
  "mcpServers": {
    "citeagent": {
      "command": "bunx",
      "args": ["@ephremyuan/citeagent", "mcp-server"],
      "env": {
        "CITEAGENT_CORPUS_ROOT": "${workspaceFolder}/corpus"
      }
    }
  }
}
```

**Cline** (VS Code Extension — `cline_mcp_settings.json`):

```json
{
  "mcpServers": {
    "citeagent": {
      "command": "bunx",
      "args": ["@ephremyuan/citeagent", "mcp-server"],
      "env": {
        "CITEAGENT_CORPUS_ROOT": "./corpus"
      },
      "disabled": false
    }
  }
}
```

**Windsurf** (`~/.codeium/windsurf/mcp_config.json`):

```json
{
  "mcpServers": {
    "citeagent": {
      "command": "bunx",
      "args": ["@ephremyuan/citeagent", "mcp-server"],
      "env": {
        "CITEAGENT_CORPUS_ROOT": "${env:PWD}/corpus"
      }
    }
  }
}
```

**OpenCode** (full plugin — agents + skills + hooks + MCP):

```bash
bunx @ephremyuan/citeagent@latest install
```

This deploys the plugin plus skills, agent configs, rules, and model mappings. The plugin uses the same TypeScript-native `CiteAgentEngine` internally — no subprocess.

---

## Custom Corpus Root

After adding the MCP server, restart your tool and check that CiteAgent tools appear:

```bash
# Claude Code
claude mcp list

# Codex CLI
codex mcp list
```

Quick smoke test — ask your AI agent:

```
Use search_documents to search for "test" with limit 1
```

If connected, it should return results (or "no documents indexed" if the corpus is empty). Then ingest your first document:

```
Use index_document to ingest "path/to/paper.pdf"
```

> **Note:** `index_document` requires the `citeindex` CLI (`uv tool install citeindex`). All other tools work without it.

---

## Custom Corpus Root

The `CITEAGENT_CORPUS_ROOT` environment variable controls where CiteAgent looks for your corpus. Defaults to `./corpus` relative to the working directory.

If you need a custom path:

```json
{
  "mcpServers": {
    "citeagent": {
      "command": "bunx",
      "args": ["@ephremyuan/citeagent", "mcp-server"],
      "env": {
        "CITEAGENT_CORPUS_ROOT": "/absolute/path/to/your/corpus"
      }
    }
  }
}
```

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `bun: command not found` | Bun not installed | `curl -fsSL https://bun.sh/install \| bash` |
| `@ephremyuan/citeagent not found` | Package not downloaded yet | `bunx @ephremyuan/citeagent@latest mcp-server` will auto-download |
| `index_document` fails | `citeindex` not installed (separate ingestion CLI) | `uv tool install citeindex` |
| Tools don't appear | MCP server not started or config path wrong | Restart the tool; check config file path |
| `CITEAGENT_CORPUS_ROOT` errors | Corpus directory doesn't exist | `mkdir -p corpus` |