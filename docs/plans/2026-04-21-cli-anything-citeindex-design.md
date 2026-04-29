# cli-anything-citeindex Design Document

**Date:** 2026-04-21  
**Status:** Approved  
**Approach:** Thin Wrapper (Approach A)

---

## Overview

Create a `cli-anything-citeindex` CLI package following the Agent Harness SOP. It wraps the existing `citeindex` Python library (agents, ingestion, search, chat, memory) with a Click-based CLI, prompt_toolkit REPL, JSON output mode, session management, and undo/redo.

The new package lives at `agent-harness/` in the project root as a **PEP 420 namespace package** under `cli_anything.citeindex`. It does **not** modify or replace the existing `citeindex` package.

---

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Package location | `agent-harness/` at project root | Follows harness SOP, isolation from existing package |
| Namespace pattern | PEP 420 (`cli_anything/` no `__init__.py`) | Coexists with other cli-anything packages |
| Wrapping strategy | Thin wrapper over Python API | Zero duplication, direct imports from citeindex |
| Backend pattern | `citeindex_backend.py` imports citeindex | Single contact point, clear boundary |
| Dependencies | All hard deps | Follows harness rule: citeindex is useless without real deps |
| REPL | Full cli-anything REPL with ReplSkin | prompt_toolkit, autocompletion, history |
| Session | Full session with undo/redo | JSON files, file locking, undo stack per command |
| Output | Dual: human + `--json` machine | ReplSkin for human, structured JSON for agents |

---

## Directory Structure

```
agent-harness/
├── CITEINDEX.md                 # Project-specific analysis & SOP
├── setup.py                     # PyPI package (cli-anything-citeindex)
├── cli_anything/                # NO __init__.py (PEP 420 namespace)
│   └── citeindex/               # HAS __init__.py
│       ├── __init__.py
│       ├── __main__.py          # python -m cli_anything.citeindex
│       ├── README.md            # HOW TO RUN — required
│       ├── citeindex_cli.py     # Main CLI entry (Click + REPL)
│       ├── core/
│       │   ├── __init__.py
│       │   ├── project.py       # Corpus create/open/info/validate/list
│       │   ├── ingest.py        # Ingest file/url/crawl
│       │   ├── search.py        # Search query/recent
│       │   ├── chat.py          # Chat ask/interactive
│       │   ├── memory.py        # Memory search/list/show
│       │   ├── export.py        # Render citations, bibliography
│       │   └── session.py       # Session save/load/undo/redo/status
│       ├── utils/
│       │   ├── __init__.py
│       │   ├── citeindex_backend.py  # Backend: imports from citeindex
│       │   └── repl_skin.py     # Unified REPL skin
│       ├── skills/
│       │   └── SKILL.md         # Agent-discoverable skill file
│       └── tests/
│           ├── TEST.md          # Test plan + results
│           ├── test_core.py     # Unit tests (~35)
│           └── test_full_e2e.py # E2E tests (~33)
└── examples/                   # Example workflows
```

---

## Command Groups & API Mapping

| Command Group | Click Group | Maps To | Key Subcommands |
|---|---|---|---|
| **Project** | `project` | `CiteIndexIngestionOrchestrator`, corpus I/O | `new`, `open`, `info`, `validate`, `list` |
| **Ingest** | `ingest` | `CiteIndexIngestionOrchestrator.ingest()` | `file`, `url`, `crawl` |
| **Search** | `search` | `SearchPipeline.search()` | `query`, `recent` |
| **Chat** | `chat` | `ChatPipeline.chat()` | `ask`, `interactive` |
| **Memory** | `memory` | `MemoryStore.search/list()` | `search`, `list`, `show` |
| **Export** | `export` | `citation_style` + citeproc-py | `render`, `bibliography` |
| **Session** | `session` | `core/session.py` (new) | `save`, `load`, `undo`, `redo`, `status` |

### Command Examples

```bash
# Project
cli-anything-citeindex project new --corpus-root ./my-research
cli-anything-citeindex project info
cli-anything-citeindex project validate

# Ingest
cli-anything-citeindex ingest file paper.pdf --type journal
cli-anything-citeindex ingest url https://arxiv.org/abs/2401.12345
cli-anything-citeindex ingest crawl https://site.com/articles --depth 3

# Search
cli-anything-citeindex search query "categorical imperative" --top-k 20 --retrieval bm25

# Chat
cli-anything-citeindex chat ask "What does Rawls argue about justice?"
cli-anything-citeindex chat interactive

# Memory
cli-anything-citeindex memory search "social contract"
cli-anything-citeindex memory list

# Export
cli-anything-citeindex export render output.pdf --format pdf
cli-anything-citeindex export bibliography

# Session
cli-anything-citeindex session save
cli-anything-citeindex session load my-session.json
cli-anything-citeindex session undo
cli-anything-citeindex session redo

# Global
cli-anything-citeindex --json search query "kant"
cli-anything-citeindex --corpus-root ./corpus project info
cli-anything-citeindex  # → enters REPL
```

---

## Session Model

### Session State

```json
{
  "version": "1.0.0",
  "corpus_root": "/path/to/corpus",
  "thread_id": "default",
  "loaded_documents": ["smith_2024_theory", "jones_2023_method"],
  "undo_stack": [
    {
      "command": "ingest file paper.pdf",
      "timestamp": "2026-04-21T10:30:00Z",
      "undo_data": {
        "type": "ingest",
        "document_id": "smith_2024_theory",
        "files_created": ["corpus/smith_2024_theory/csl.json", "..."]
      }
    }
  ],
  "redo_stack": [],
  "created_at": "2026-04-21T10:00:00Z",
  "updated_at": "2026-04-21T10:30:00Z"
}
```

### Undo/Redo Semantics

| Command | Undo Action | Feasible? |
|---------|-------------|-----------|
| `ingest file/url` | Remove document folder from corpus | Yes |
| `chat ask` | Remove JSONL entry (warn: Merkle DAG break) | Partial |
| `search query` | N/A (read-only) | N/A |
| `project new` | Remove `.citeindex/` directory | Yes |
| `export render` | Delete output file | Yes |
| `memory search/list` | N/A (read-only) | N/A |

### File Locking

Session saves use `fcntl.flock(LOCK_EX)` per harness spec:
- Open with `"r+"` (no truncation on open)
- Lock → truncate → write → flush → unlock
- First save uses `"w"` mode (file doesn't exist yet)

---

## REPL Design

### Branding

```
╭─────────────────────────────────────────────────────╮
│  ◆ CiteIndex CLI v1.0.0                            │
│  ◇ Corpus: /path/to/corpus (3 documents loaded)    │
│  ◇ Thread: default                                 │
│  ◇ Skill: /path/to/cli_anything/citeindex/skills/SKILL.md │
╰─────────────────────────────────────────────────────╯
```

### Prompt

```
citeindex:my-research (3 docs) > 
```

### Prompt toolkit features
- Persistent command history
- Subcommand/flag autocompletion
- Context status bar (corpus, thread, doc count)
- Multi-line input for chat

### Default behavior
- `cli-anything-citeindex` with no args → REPL (via `invoke_without_command=True`)
- All subcommands work both in REPL and as CLI args

---

## Output Format

### Human mode (default)
- Tables, colors, ✓/✗/⚠ symbols via ReplSkin
- `skin.success()`, `skin.error()`, `skin.warning()`, `skin.info()`
- `skin.table()` for structured data

### Machine mode (`--json`)
- Structured JSON for every command
- Example: `{"status": "ok", "query": "kant", "results": [...], "total": 12}`
- Enables programmatic agent consumption

---

## Testing Strategy

### Unit Tests (`test_core.py`) — ~35 tests
- `project.py`: corpus creation, path validation, info retrieval
- `ingest.py`: config mapping, argument parsing
- `search.py`: query parameter validation, result formatting
- `chat.py`: prompt construction, thread management
- `memory.py`: search formatting, list rendering
- `session.py`: save/load cycle, undo/redo stack, file locking, JSON serialization

### E2E — Intermediate (`test_full_e2e.py`) — ~15 tests
- Session JSON structure validation
- `--json` flag produces valid JSON schema
- Corpus folder creation after `project new`
- Citation rendering intermediate output

### E2E — True Backend (`test_full_e2e.py`) — ~10 tests
- Ingest real PDF → verify corpus files (csl.json, document.json, merkle.json)
- Ingest URL → verify structured output
- Search after ingest → BM25 results returned
- Chat after ingest → trace-bound citations in response
- Export render → verify PDF magic bytes `%PDF-`
- Memory round-trip → chat + memory search

**No graceful degradation.** citeindex + system deps must be installed.

### CLI Subprocess Tests (`test_full_e2e.py`) — ~8 tests
- `_resolve_cli("cli-anything-citeindex")` helper
- Test `--help`, `--json`, `project new`, `ingest file`, `search query`, `chat ask`, `session save/load`, full workflow

---

## setup.py

```python
from setuptools import setup, find_namespace_packages

setup(
    name="cli-anything-citeindex",
    version="1.0.0",
    packages=find_namespace_packages(include=["cli_anything.*"]),
    install_requires=[
        "citeindex>=0.11.0",
        "click>=8.0.0",
        "prompt-toolkit>=3.0.0",
    ],
    entry_points={
        "console_scripts": [
            "cli-anything-citeindex=cli_anything.citeindex.citeindex_cli:main",
        ],
    },
    python_requires=">=3.12",
)
```

---

## SKILL.md

Generated after all tests pass. Auto-detected by ReplSkin and displayed in the REPL banner. Contains:
- YAML frontmatter (name, description)
- Installation prerequisites
- Command groups and syntax
- Usage examples
- Agent-specific guidance for `--json` output

---

## Implementation Phases

1. **Phase 1**: Scaffolding (directory structure, setup.py, `__init__.py` files, `__main__.py`)
2. **Phase 2**: Core data layer (`citeindex_backend.py`, `project.py`, `session.py`)
3. **Phase 3**: Command modules (`ingest.py`, `search.py`, `chat.py`, `memory.py`, `export.py`)
4. **Phase 4**: CLI entry point (`citeindex_cli.py` with Click groups and all subcommands)
5. **Phase 5**: REPL (`repl_skin.py`, REPL mode, prompt_toolkit integration)
6. **Phase 6**: Testing (`TEST.md`, `test_core.py`, `test_full_e2e.py`)
7. **Phase 7**: SKILL.md generation
8. **Phase 8**: Installation verification (pip install -e, CLI_ANYTHING_FORCE_INSTALLED tests)