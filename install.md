# CiteAgent Installation Guide

Install and configure CiteAgent — a Merkle-verified academic research system for LLM agents — by following the instructions below.

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
| verifier | `qwen3:8b` | `claude-haiku-4-5` | `gpt-5.4-mini` |
| explore-corpus | `qwen3:4b` | `claude-haiku-4-5` | `gpt-5-nano` |
| ingestor | `qwen3:8b` | `claude-haiku-4-5` | `gpt-5.4-mini` |
| reviewer | `qwen3:14b` | `claude-sonnet-4-6` | `gpt-5.4` |

**Guidance:** Use Ollama for free/local usage. Claude and OpenAI provide higher-quality results. Assign cheaper/haiku-tier models to subagents; reserve sonnet/GPT-5.4 for the researcher and reviewer.

---

## For Humans

### Prerequisites

- **Python 3.12+**
- **System dependencies:** `tesseract` (OCR), `ffmpeg` (media), `ollama` (local LLM)

### 1. Install Python packages

```bash
pip install citeagent citeindex
```

### 2. Install system dependencies

```bash
# macOS
brew install tesseract ffmpeg
brew install ollama

# Ubuntu/Debian
sudo apt install tesseract-ocr ffmpeg
curl -fsSL https://ollama.com/install.sh | sh
```

### 3. Configure LLM backend

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

### 4. Install OpenCode plugin

```bash
bunx @ephremyuan/citeagent@latest install
```

### 5. Configure other MCP clients

For Claude Code, Codex, Cursor, Cline, and Windsurf — see [**mcp-setup.md**](./mcp-setup.md).

### 6. Verify installation

```bash
python3 -c "import citeagent" && citeagent --version
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

### Step 1 — Install packages

```bash
pip install citeagent citeindex
```

### Step 2 — Install system dependencies

Check for and install required tools:

```bash
# Verify presence
tesseract --version
ffmpeg -version

# Install if missing (adjust per OS)
# macOS:  brew install tesseract ffmpeg ollama
# Linux:  sudo apt install tesseract-ocr ffmpeg && curl -fsSL https://ollama.com/install.sh | sh
```

### Step 3 — Configure LLM backend

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

### Step 4 — Install OpenCode plugin

```bash
bunx @ephremyuan/citeagent@latest install
```

### Step 5 — Configure other MCP clients

For Claude Code, Codex, Cursor, Cline, or Windsurf configurations, refer the user to [**mcp-setup.md**](./mcp-setup.md).

### Step 6 — Verify

Confirm everything works:

```bash
python3 -c "import citeagent" && citeagent --version
```

If both succeed, CiteAgent is installed and ready.