# CiteAgent MCP Setup Guide

> **For AI agents (Claude Code, Codex, Cursor, Cline, Windsurf, etc.):** This document tells you how to install and connect CiteAgent so you can use its citation-verified research tools.

## What CiteAgent Gives You

Once connected, you get **25+ tools** for Merkle-verified academic research:

| Tool | What it does |
|------|-------------|
| `cite_search` | BM25 full-text search on your academic corpus |
| `cite_search_claims` | Search claims in the argument graph |
| `cite_verify` | Verify Merkle proof for an evidence node |
| `cite_render` | Render CSL citation to formatted bibliography (Chicago, APA, MLA…) |
| `cite_ingest` | Ingest a document (PDF, URL, media) into the corpus |
| `cite_tree` | Load PageIndex tree for a document |
| `cite_tree_traverse` | Traverse PageIndex tree to a given depth |
| `cite_argument_query` | Query the argument graph (claims, contradictions) |
| `cite_regex_search` | Regex-based search on document nodes |
| `cite_memory_save` | Save to persistent memory store |
| `cite_search_memory` | Search the memory store |
| `cite_memory_store_tier` | Store in a specific tier (working/episodic/long_term/corpus) |
| `cite_memory_retrieve_tier` | Retrieve from a specific tier |
| `cite_memory_consolidate` | Consolidate episodic → long-term |
| `cite_memory_summarize` | Summarize memory entries |
| `cite_index_claim` | Index a new claim in the argument graph |
| `cite_write_edge` | Write an edge (support/contradict/relate) between claims |
| `cite_delete_document` | Delete a document and associated data |
| `cite_merkle_compute` | Compute Merkle tree hashes for a payload |
| `cite_audit_save` | Save an audit result (verdict + evidence hashes) |
| `cite_audit_retrieve` | Retrieve a saved audit result |
| `cite_crypto_sign` | Sign a message (HMAC-SHA256) |
| `cite_crypto_verify` | Verify an HMAC-SHA256 signature |
| `cite_crypto_audit_trail` | Return the audit chain for a session |
| `cite_safeharness_check` | Run all 4 SafeHarness layers on a tool call |
| `cite_safeharness_sanitize` | Sanitize input for a tool call |
| `cite_safeharness_checkpoint` | Create a state checkpoint before a write |
| `cite_safeharness_rollback` | Rollback from a checkpoint |
| `cite_safeharness_status` | Get current SafeHarness security status |
| `cite_tantivy_index` | Low-level: add file to Tantivy index |
| `cite_tantivy_search` | Low-level: Tantivy search |

## Prerequisites

Before adding the MCP server, install the Python package:

```bash
pip install citeindex
```

Verify it works:

```bash
python3 -c "import citeindex; print('OK')"
```

System dependencies (optional but recommended):

```bash
# Ubuntu/Debian
sudo apt-get install tesseract-ocr mediainfo ffmpeg

# macOS
brew install tesseract mediainfo ffmpeg
```

LLM backend for chat/generation (optional):

```bash
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull qwen3
```

## Add to Your Tool

### Claude Code

**Option A: Project-scoped** (recommended — shareable via VCS)

Create `.mcp.json` at your project root:

```json
{
  "mcpServers": {
    "citeagent": {
      "command": "python3",
      "args": ["-m", "citeindex.mcp_server"],
      "env": {
        "CITEAGENT_CORPUS_ROOT": "${PWD}/corpus"
      }
    }
  }
}
```

**Option B: CLI command**

```bash
claude mcp add --transport stdio citeagent -- python3 -m citeindex.mcp_server
```

**Option C: User-scoped** (available in all projects)

```bash
claude mcp add --transport stdio --scope user citeagent -- python3 -m citeindex.mcp_server
```

With environment variables:

```bash
claude mcp add --transport stdio --scope user \
  --env CITEAGENT_CORPUS_ROOT=/path/to/corpus \
  citeagent -- python3 -m citeindex.mcp_server
```

### Codex CLI

Edit `~/.codex/config.toml` (user-scoped, all projects):

```toml
[mcp_servers.citeagent]
command = "python3"
args = ["-m", "citeindex.mcp_server"]
env = { CITEAGENT_CORPUS_ROOT = "./corpus" }
enabled = true
```

Or per-project in `.codex/config.toml` (trusted projects only).

Or via CLI:

```bash
codex mcp add citeagent -- python3 -m citeindex.mcp_server
```

### Cursor

Create `.cursor/mcp.json` at your project root:

```json
{
  "mcpServers": {
    "citeagent": {
      "command": "python3",
      "args": ["-m", "citeindex.mcp_server"],
      "env": {
        "CITEAGENT_CORPUS_ROOT": "${workspaceFolder}/corpus"
      }
    }
  }
}
```

Or global: `~/.cursor/mcp.json` (same format).

### Cline (VS Code Extension)

Edit `cline_mcp_settings.json`:

- **macOS:** `~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`
- **Linux:** `~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`
- **Windows:** `%APPDATA%\Code\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json`

```json
{
  "mcpServers": {
    "citeagent": {
      "command": "python3",
      "args": ["-m", "citeindex.mcp_server"],
      "env": {
        "CITEAGENT_CORPUS_ROOT": "./corpus"
      },
      "disabled": false
    }
  }
}
```

### Windsurf (Codeium)

Edit `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "citeagent": {
      "command": "python3",
      "args": ["-m", "citeindex.mcp_server"],
      "env": {
        "CITEAGENT_CORPUS_ROOT": "${env:PWD}/corpus"
      }
    }
  }
}
```

> **Note:** Windsurf uses `${env:VAR}` for environment variable interpolation.

### OpenCode (full plugin — agents + skills + hooks)

```bash
bunx @ephremyuan/citeagent@latest install
```

This deploys the plugin plus skills, agent configs, rules, and model mappings. See [plugins/opencode-citeagent/README.md](./plugins/opencode-citeagent/README.md).

## Verify the Connection

After adding the MCP server, restart your tool and check that CiteAgent tools appear:

```bash
# Claude Code
claude mcp list

# Codex CLI
codex mcp list
```

Quick smoke test — ask your AI agent:

```
Use cite_search to search for "test" with limit 1
```

If connected, it should return results (or "no documents indexed" if the corpus is empty). Then ingest your first document:

```
Use cite_ingest to ingest "path/to/paper.pdf"
```

## Custom Python Path

If your Python with `citeindex` installed is not the default `python3`, set `CITEAGENT_PYTHON`:

```json
{
  "mcpServers": {
    "citeagent": {
      "command": "/path/to/your/python3",
      "args": ["-m", "citeindex.mcp_server"],
      "env": {
        "CITEAGENT_CORPUS_ROOT": "./corpus"
      }
    }
  }
}
```

Priority: `CITEAGENT_PYTHON` env → project `.venv/bin/python3` → `~/.rye/py/` → `~/.local/share/uv/python/` → system `python3`.

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `Connection error (-32000)` | Python process crashed or `citeindex` not installed | Run `python3 -c "import citeindex"` to verify |
| `No module named citeindex.mcp_server` | Old version of citeindex | `pip install -U citeindex` |
| `tesseract not found` | OCR not installed | `sudo apt install tesseract-ocr` or `brew install tesseract` |
| Tools don't appear | MCP server not started or config path wrong | Restart the tool; check config file path |
| `CITEAGENT_CORPUS_ROOT` errors | Corpus directory doesn't exist | Create it: `mkdir -p corpus` |