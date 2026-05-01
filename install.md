# CiteAgent Installation Guide

Install and configure CiteAgent — a Merkle-verified academic research system for LLM agents — by following the instructions below.

> **Full documentation**: See [docs/project-report.md](./docs/project-report.md) for architecture, implementation status, and tool inventory. See [docs/citeagent-audit-report.md](./docs/citeagent-audit-report.md) for the detailed audit. See [mcp-setup.md](./mcp-setup.md) for MCP client configurations.

## CiteAgent Agents

CiteAgent provides 5 purpose-built agents for OpenCode:

| Agent | Role | Purpose |
|-------|------|---------|
| `citeagent-researcher` | primary | Academic research, citation-verified evidence |
| `citeagent-verifier` | subagent | Merkle proof checking, integrity verification |
| `citeagent-explore-corpus` | subagent | Fast corpus search, tree browsing |
| `citeagent-ingestor` | subagent | Document ingestion, PDF/URL/media |
| `citeagent-reviewer` | subagent | Literature review, gap identification |

## Model Selection

| Agent | Ollama (free) | Claude | OpenAI |
|-------|---------------|--------|--------|
| researcher | `qwen3:8b` | `claude-sonnet-4-6` | `gpt-5.4-mini` |
| verifier | `qwen3:8b` | `claude-haiku-4-5` | `gpt-5-nano` |
| explore-corpus | `qwen3:4b` | `claude-haiku-4-5` | `gpt-5-nano` |
| ingestor | `qwen3:8b` | `claude-haiku-4-5` | `gpt-5.4-mini` |
| reviewer | `qwen3:14b` | `claude-sonnet-4-6` | `gpt-5.4` |

**Guidance:** Use Ollama for free/local usage. Claude and OpenAI provide higher-quality results. Assign cheaper/haiku-tier models to subagents; reserve sonnet/GPT-5.4 for the researcher and reviewer.

---

## For Humans

### Prerequisites

- **Bun** (required) — JavaScript runtime for the MCP server
- **citeindex CLI** (optional — needed only for `cite_ingest` / `cite_tantivy_index`)
- **System dependencies:** `tesseract` (OCR), `ffmpeg` (media), `ollama` (local LLM) — all optional

### 1. Install Bun

```bash
curl -fsSL https://bun.sh/install | bash
```

### 2. Install CiteAgent plugin

```bash
bunx @ephremyuan/citeagent@latest install
```

> The plugin runs natively in TypeScript — **no Python required**. All citation tools work in-process. Only `cite_ingest` (document ingestion) optionally needs the `citeindex` CLI.

### 3. Install citeindex (optional — for document ingestion)

```bash
uv tool install citeindex
```

> Only needed if you want to ingest new documents. All other tools work without it.

### 4. Install system dependencies (optional)

```bash
# macOS
brew install tesseract ffmpeg
brew install ollama

# Ubuntu/Debian
sudo apt install tesseract-ocr ffmpeg
curl -fsSL https://ollama.com/install.sh | sh
```

### 5. Configure LLM backend (optional — for chat/generation)

**Ollama (free, local):**

```bash
ollama pull qwen3:4b
ollama pull qwen3:8b
ollama pull qwen3:14b
ollama serve  # starts on localhost:11434
```

**Claude (Anthropic):**

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

**OpenAI (GPT):**

```bash
export OPENAI_API_KEY="sk-..."
```

### 6. Configure other MCP clients

For Claude Code, Codex, Cursor, Cline, and Windsurf — see [**mcp-setup.md**](./mcp-setup.md).

> **All MCP clients now use the same TypeScript-native server.** No Python subprocess required. The config is `bunx @ephremyuan/citeagent mcp-server`.

### 7. Verify installation

```bash
# Plugin tools work natively — check the plugin loaded:
bunx @ephremyuan/citeagent@latest install --dry-run

# Or test the MCP server directly:
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"capabilities":{}}}' | bunx @ephremyuan/citeagent mcp-server

# If you installed citeindex (optional):
citeindex --version
```

---

## For LLM Agents

When helping a user install CiteAgent, follow these steps in order.

### Step 0 — Ask which LLM provider

Ask the user which backend they want:

- **Ollama** — free, local, no API key needed
- **Claude** — requires `ANTHROPIC_API_KEY`
- **OpenAI** — requires `OPENAI_API_KEY`

Configure based on their choice.

### Step 1 — Install Bun

```bash
curl -fsSL https://bun.sh/install | bash
```

### Step 2 — Install OpenCode plugin

```bash
bunx @ephremyuan/citeagent@latest install
```

> No Python required. The MCP server runs natively in TypeScript.

### Step 3 — Install citeindex (optional)

```bash
uv tool install citeindex
```

> Only needed for document ingestion. All other tools run natively in TypeScript.

### Step 4 — Install system dependencies (optional)

```bash
# Verify presence
tesseract --version

# Install if missing (adjust per OS)
# macOS:  brew install tesseract ffmpeg ollama
# Linux:  sudo apt install tesseract-ocr ffmpeg && curl -fsSL https://ollama.com/install.sh | sh
```

### Step 5 — Configure LLM backend

**If Ollama:**

```bash
ollama pull qwen3:4b && ollama pull qwen3:8b && ollama pull qwen3:14b
ollama serve
```

**If Claude:** Get the user's `ANTHROPIC_API_KEY` and set it:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

**If OpenAI:** Get the user's `OPENAI_API_KEY` and set it:

```bash
export OPENAI_API_KEY="sk-..."
```

### Step 6 — Configure MCP clients

For Claude Code, Codex, Cursor, Cline, or Windsurf — the config is the same for all:

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

For exact file paths and alternatives, refer the user to [**mcp-setup.md**](./mcp-setup.md).

### Step 7 — Verify

```bash
bunx @ephremyuan/citeagent@latest install --dry-run
citeindex --version  # optional, only if installed
```

If the plugin install succeeds and the MCP server starts, CiteAgent is ready.