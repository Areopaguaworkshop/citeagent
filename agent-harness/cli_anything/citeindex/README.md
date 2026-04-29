# cli-anything-citeindex

CLI harness for CiteIndex — AI research knowledge infrastructure with Merkle-verified retrieval.

## Installation

### Prerequisites

```bash
# Python package
pip install -e .

# System dependencies (required)
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
```

### Install the CLI

```bash
cd agent-harness
pip install -e .
```

### Verify installation

```bash
which cli-anything-citeindex
cli-anything-citeindex --help
```

## Usage

### Interactive REPL (default)

```bash
cli-anything-citeindex
# → enters REPL with prompt_toolkit, history, autocompletion
```

### One-shot commands

```bash
# Project management
cli-anything-citeindex project new --corpus-root ./my-research
cli-anything-citeindex project info

# Ingest documents
cli-anything-citeindex ingest file paper.pdf --type journal
cli-anything-citeindex ingest url https://arxiv.org/abs/2401.12345
cli-anything-citeindex ingest crawl https://site.com/articles --depth 3

# Search
cli-anything-citeindex search query "categorical imperative" --top-k 20

# Chat
cli-anything-citeindex chat ask "What does Rawls argue about justice?"
cli-anything-citeindex chat interactive

# Memory
cli-anything-citeindex memory search "social contract"
cli-anything-citeindex memory list

# Export
cli-anything-citeindex export render output.txt

# Session
cli-anything-citeindex session create
cli-anything-citeindex session undo
```

### JSON output for agents

```bash
cli-anything-citeindex --json search query "kant"
# → {"status": "ok", "query": "kant", "results": [...], "total": 12}
```

## Running Tests

```bash
cd agent-harness

# Unit tests
python -m pytest cli_anything/citeindex/tests/test_core.py -v

# Full E2E tests (requires citeindex + system deps installed)
CLI_ANYTHING_FORCE_INSTALLED=1 python -m pytest cli_anything/citeindex/tests/ -v -s
```

## Architecture

This CLI is a thin wrapper over the existing `citeindex` Python library. It does not
reimplement any functionality — all operations delegate to `citeindex`'s agents,
ingestion pipelines, and search engines via `citeindex_backend.py`.