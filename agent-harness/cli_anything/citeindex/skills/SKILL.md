---
name: "cli-anything-citeindex"
description: "CLI harness for CiteIndex — AI research knowledge infrastructure with Merkle-verified retrieval, citation-indexed search, and trace-bound chat"
---

# cli-anything-citeindex

A command-line interface for CiteIndex's research infrastructure. Ingest documents, search with BM25, chat with trace-bound citations, and export bibliographies — all from the terminal or as an agent tool.

## Prerequisites

```bash
# Python package
pip install cli-anything-citeindex

# System dependencies (required)
sudo apt-get install tesseract-ocr ffmpeg   # Debian/Ubuntu
brew install tesseract ffmpeg               # macOS

# LLM backend (required for chat/generation)
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull qwen3
```

## Command Syntax

```bash
cli-anything-citeindex [GLOBAL OPTIONS] COMMAND [ARGS]...
```

### Global Options

- `--corpus-root PATH` — Corpus root directory (default: `corpus`)
- `--json` — Output all commands as JSON (for agents)
- `--version` — Show version
- `--help` — Show help

### Command Groups

| Group | Commands | Description |
|-------|----------|-------------|
| `project` | `new`, `info`, `validate`, `list` | Corpus management |
| `ingest` | `file`, `url`, `crawl` | Document ingestion |
| `search` | `query` | BM25/PageIndex search |
| `chat` | `ask`, `interactive` | Citation-traced chat |
| `memory` | `search`, `list` | Chat memory & history |
| `export` | `render`, `bibliography` | Citation rendering |
| `session` | `create`, `list`, `save`, `load`, `undo`, `redo`, `status` | Session management |

## Usage Examples

### Ingest a PDF

```bash
cli-anything-citeindex ingest file paper.pdf --type journal --lang en
```

### Search the corpus

```bash
cli-anything-citeindex --json search query "categorical imperative" --top-k 10
```

### Chat with citations

```bash
cli-anything-citeindex chat ask "What does Rawls argue about justice?"
```

### Export a bibliography

```bash
cli-anything-citeindex export render bibliography.txt --format txt
```

### Session with undo

```bash
cli-anything-citeindex session create
cli-anything-citeindex ingest file paper.pdf
cli-anything-citeindex session undo
```

### Interactive REPL

```bash
cli-anything-citeindex
# → enters REPL with prompt_toolkit, history, autocompletion
```

## Agent-Specific Guidance

### JSON Output Mode

Use `--json` for all commands when operating as an agent:

```bash
cli-anything-citeindex --json project info
cli-anything-citeindex --json search query "kant" --top-k 20
cli-anything-citeindex --json chat ask "What is the main argument?"
```

All JSON output follows the format:
```json
{"status": "ok", ...}
```

Error responses:
```json
{"status": "error", "message": "..."}
```

### Typical Agent Workflow

1. `project info` — Check corpus state
2. `ingest file <path>` — Add documents
3. `search query <terms>` — Find relevant passages
4. `chat ask <question>` — Get cited answers
5. `export render <path>` — Export results

### Error Handling

- Exit code 0 = success
- Exit code 1 = error (check stderr or JSON `status` field)
- Exit code 2 = usage error (wrong arguments)