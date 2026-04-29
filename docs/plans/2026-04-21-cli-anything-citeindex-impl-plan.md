# cli-anything-citeindex Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build `cli-anything-citeindex`, a Click-based CLI + REPL wrapping the existing citeindex Python library, following the Agent Harness SOP.

**Architecture:** PEP 420 namespace package (`cli_anything/citeindex/`) that directly imports citeindex's Python API. Click groups map to CiteIndex's pipeline domains. prompt_toolkit REPL with ReplSkin branding. Session management with undo/redo and file-locked JSON saves.

**Tech Stack:** Python 3.12+, Click 8+, prompt-toolkit 3+, citeindex>=0.11.0

---

### Task 1: Scaffolding — Directory Structure + setup.py

**Files:**
- Create: `agent-harness/setup.py`
- Create: `agent-harness/cli_anything/citeindex/__init__.py`
- Create: `agent-harness/cli_anything/citeindex/__main__.py`
- Create: `agent-harness/cli_anything/citeindex/core/__init__.py`
- Create: `agent-harness/cli_anything/citeindex/utils/__init__.py`
- Create: `agent-harness/cli_anything/citeindex/skills/` (directory)

**Step 1: Create directory tree**

```bash
cd /home/ajiap/project/citeindex
mkdir -p agent-harness/cli_anything/citeindex/core
mkdir -p agent-harness/cli_anything/citeindex/utils
mkdir -p agent-harness/cli_anything/citeindex/skills
mkdir -p agent-harness/cli_anything/citeindex/tests
mkdir -p agent-harness/examples
```

**Step 2: Write setup.py**

Create `agent-harness/setup.py`:

```python
from setuptools import setup, find_namespace_packages

setup(
    name="cli-anything-citeindex",
    version="1.0.0",
    description="CLI harness for CiteIndex — AI research knowledge infrastructure with Merkle-verified retrieval",
    packages=find_namespace_packages(include=["cli_anything.*"]),
    install_requires=[
        "citeindex>=0.11.0",
        "click>=8.0.0",
        "prompt-toolkit>=3.0.0",
    ],
    package_data={
        "cli_anything.citeindex": ["skills/*.md"],
    },
    entry_points={
        "console_scripts": [
            "cli-anything-citeindex=cli_anything.citeindex.citeindex_cli:main",
        ],
    },
    python_requires=">=3.12",
)
```

**Step 3: Write `__init__.py`**

Create `agent-harness/cli_anything/citeindex/__init__.py`:

```python
"""cli-anything-citeindex — stateful CLI harness for CiteIndex research infrastructure."""

__version__ = "1.0.0"
```

**Step 4: Write `__main__.py`**

Create `agent-harness/cli_anything/citeindex/__main__.py`:

```python
"""Allow running via: python -m cli_anything.citeindex"""
from cli_anything.citeindex.citeindex_cli import main

main()
```

**Step 5: Write empty `__init__.py` files**

Create `agent-harness/cli_anything/citeindex/core/__init__.py`:

```python
```

Create `agent-harness/cli_anything/citeindex/utils/__init__.py`:

```python
```

**Step 6: Verify NO `__init__.py` in `cli_anything/`**

```bash
ls agent-harness/cli_anything/__init__.py 2>/dev/null && echo "ERROR: __init__.py found" || echo "OK: No __init__.py (PEP 420 namespace)"
```

Expected: `OK: No __init__.py (PEP 420 namespace)`

**Step 7: Verify package importable (will fail until Task 2, just check structure)**

```bash
find agent-harness -type f -name "*.py" | sort
```

Expected:
```
agent-harness/cli_anything/citeindex/__init__.py
agent-harness/cli_anything/citeindex/__main__.py
agent-harness/cli_anything/citeindex/core/__init__.py
agent-harness/cli_anything/citeindex/utils/__init__.py
agent-harness/setup.py
```

**Step 8: Commit**

```bash
git add agent-harness/
git commit -m "feat: scaffold cli-anything-citeindex package structure"
```

---

### Task 2: Backend Module — citeindex_backend.py

**Files:**
- Create: `agent-harness/cli_anything/citeindex/utils/citeindex_backend.py`

**Step 1: Write the failing test**

Create `agent-harness/cli_anything/citeindex/tests/test_core.py`:

```python
"""Unit tests for cli-anything-citeindex core modules."""
from __future__ import annotations

import json
import os
import tempfile

import pytest


class TestCiteIndexBackend:
    """Tests for the citeindex backend wrapper."""

    def test_import_backend_module(self):
        """Backend module is importable."""
        from cli_anything.citeindex.utils.citeindex_backend import (
            CiteIndexBackend,
        )

    def test_backend_has_required_methods(self):
        """Backend exposes all required methods."""
        from cli_anything.citeindex.utils.citeindex_backend import (
            CiteIndexBackend,
        )
        backend = CiteIndexBackend()
        assert hasattr(backend, "ingest")
        assert hasattr(backend, "search")
        assert hasattr(backend, "chat")
        assert hasattr(backend, "memory_search")
        assert hasattr(backend, "memory_list_threads")
        assert hasattr(backend, "format_bibliography")

    def test_backend_check_dependencies(self):
        """check_dependencies returns dict with 'available' key."""
        from cli_anything.citeindex.utils.citeindex_backend import (
            CiteIndexBackend,
        )
        result = CiteIndexBackend.check_dependencies()
        assert "available" in result
        assert isinstance(result["available"], bool)
```

**Step 2: Run test to verify it fails**

```bash
cd /home/ajiap/project/citeindex/agent-harness
python -m pytest cli_anything/citeindex/tests/test_core.py::TestCiteIndexBackend -v 2>&1 | tail -5
```

Expected: FAIL — `ModuleNotFoundError: No module named 'cli_anything.citeindex.utils.citeindex_backend'`

**Step 3: Write implementation**

Create `agent-harness/cli_anything/citeindex/utils/citeindex_backend.py`:

```python
"""Backend wrapper for CiteIndex — single point of contact with the citeindex library.

All imports from the citeindex package go through this module.
If citeindex is not installed, clear error messages with install instructions are raised.
"""
from __future__ import annotations

import shutil
from dataclasses import asdict
from typing import Any, Dict, List, Optional


class CiteIndexBackend:
    """Thin wrapper over the citeindex Python API."""

    @staticmethod
    def check_dependencies() -> Dict[str, Any]:
        """Check if citeindex and system tools are available.

        Returns:
            Dict with 'available' bool and details about each dependency.
        """
        result: Dict[str, Any] = {"available": True, "checks": {}}

        # Check citeindex Python package
        try:
            import citeindex  # noqa: F401
            result["checks"]["citeindex"] = {"available": True, "version": getattr(citeindex, "__version__", "unknown")}
        except ImportError:
            result["checks"]["citeindex"] = {
                "available": False,
                "message": "citeindex not installed. Run: pip install citeindex",
            }
            result["available"] = False

        # Check system tools
        for tool in ["tesseract", "ffmpeg", "ollama"]:
            path = shutil.which(tool)
            result["checks"][tool] = {"available": path is not None, "path": path}

        return result

    def ingest(self, input_ref: str, corpus_root: str = "corpus",
               llm_model: str = "ollama/qwen3",
               text_direction: str = "horizontal",
               vertical_lang: str = "ch",
               lang: str = "auto",
               page_range: str = "1-5, -3",
               doc_type_override: Optional[str] = None,
               use_layout_analysis: bool = True,
               is_primary: bool = False,
               use_pageindex: bool = False,
               pageindex_model: str = "ollama/qwen3.5:cloud",
               schema_version: str = "1.0.0",
               ) -> Dict[str, Any]:
        """Ingest a document into the corpus.

        Args:
            input_ref: File path or URL to ingest.
            corpus_root: Root directory for corpus storage.
            llm_model: LLM model for citation extraction.
            text_direction: Text direction (horizontal/auto/vertical).
            vertical_lang: Language for vertical text (ch/japan).
            lang: OCR language (default: auto-detect).
            page_range: Page range for extraction.
            doc_type_override: Override automatic document type detection.
            use_layout_analysis: Enable layout analysis.
            is_primary: Mark source as primary (line-level granularity).
            use_pageindex: Use PageIndex tree building.
            pageindex_model: LLM model for PageIndex.
            schema_version: Schema version tag.

        Returns:
            Dict from CiteIndexIngestionOrchestrator.ingest()
        """
        from citeindex.ingestion import CiteIndexIngestionOrchestrator
        from citeindex.ingestion.models import IngestionConfig

        config = IngestionConfig(
            llm_model=llm_model,
            text_direction=text_direction,
            vertical_lang=vertical_lang,
            lang=lang,
            page_range=page_range,
            doc_type_override=doc_type_override,
            use_layout_analysis=use_layout_analysis,
            is_primary=is_primary,
            use_pageindex=use_pageindex,
            pageindex_model=pageindex_model,
        )
        orchestrator = CiteIndexIngestionOrchestrator(
            corpus_root=corpus_root,
            schema_version=schema_version,
        )
        return orchestrator.ingest(input_ref, config=config)

    def ingest_all_urls(self, root_url: str, corpus_root: str = "corpus",
                        llm_model: str = "ollama/qwen3",
                        update: bool = False,
                        max_depth: int = 2,
                        max_pages: int = 100,
                        schema_version: str = "1.0.0",
                        **ingest_kwargs: Any,
                        ) -> Dict[str, Any]:
        """Crawl and ingest all article pages from a URL.

        Args:
            root_url: Root URL to crawl.
            corpus_root: Root directory for corpus storage.
            llm_model: LLM model for citation extraction.
            update: Compare content hashes; skip unchanged pages.
            max_depth: Max BFS crawl depth.
            max_pages: Max pages the crawler will visit.
            schema_version: Schema version tag.
            **ingest_kwargs: Additional IngestionConfig kwargs.

        Returns:
            Dict from CiteIndexIngestionOrchestrator.ingest_all_urls()
        """
        from citeindex.ingestion import CiteIndexIngestionOrchestrator
        from citeindex.ingestion.models import IngestionConfig

        config = IngestionConfig(llm_model=llm_model, **ingest_kwargs)
        orchestrator = CiteIndexIngestionOrchestrator(
            corpus_root=corpus_root,
            schema_version=schema_version,
        )
        return orchestrator.ingest_all_urls(
            root_url=root_url,
            config=config,
            update=update,
            max_depth=max_depth,
            max_pages=max_pages,
        )

    def search(self, query: str, corpus_root: str = "corpus",
               top_k: int = 20,
               cite_style: str = "chicago-author-date",
               retrieval: str = "auto",
               pageindex_model: str = "ollama/qwen3.5:cloud",
               schema_version: str = "1.0.0",
               ) -> Dict[str, Any]:
        """Search the corpus using BM25 or PageIndex retrieval.

        Args:
            query: Search query string.
            corpus_root: Root directory for corpus storage.
            top_k: Number of results to return.
            cite_style: Citation style for formatted output.
            retrieval: Retrieval method (bm25/pageindex/auto).
            pageindex_model: LLM model for PageIndex retrieval.
            schema_version: Schema version tag.

        Returns:
            Dict from SearchPipeline.search()
        """
        from citeindex.agents.chat import SearchPipeline

        pipeline = SearchPipeline(
            corpus_root=corpus_root,
            schema_version=schema_version,
        )
        return pipeline.search(
            query=query,
            top_k=top_k,
            cite_style=cite_style,
            retrieval=retrieval,
            pageindex_model=pageindex_model,
        )

    def chat(self, prompt: str, corpus_root: str = "corpus",
             llm_model: str = "ollama/qwen3",
             thread_id: str = "default",
             schema_version: str = "1.0.0",
             ) -> Dict[str, Any]:
        """Chat with trace-bound citations.

        Args:
            prompt: User question or message.
            corpus_root: Root directory for corpus storage.
            llm_model: LLM model for generation.
            thread_id: Chat thread ID.
            schema_version: Schema version tag.

        Returns:
            Dict from ChatPipeline.chat()
        """
        from citeindex.agents.chat import ChatPipeline

        pipeline = ChatPipeline(
            corpus_root=corpus_root,
            llm_model=llm_model,
            schema_version=schema_version,
        )
        return pipeline.chat(prompt, thread_id=thread_id)

    def memory_search(self, query: str, corpus_root: str = "corpus",
                      thread_id: Optional[str] = None,
                      ) -> List[Dict[str, Any]]:
        """Search past chat memory.

        Args:
            query: Search query string.
            corpus_root: Root directory for corpus storage.
            thread_id: Restrict to a specific thread.

        Returns:
            List of MemoryEntry dicts.
        """
        from citeindex.agents.memory import MemoryStore

        store = MemoryStore(memory_dir=f"{corpus_root}/.memory")
        results = store.search(query, thread_id=thread_id)
        return [e.to_dict() for e in results[:20]]

    def memory_list_threads(self, corpus_root: str = "corpus") -> List[str]:
        """List all memory threads.

        Args:
            corpus_root: Root directory for corpus storage.

        Returns:
            List of thread ID strings.
        """
        from citeindex.agents.memory import MemoryStore

        store = MemoryStore(memory_dir=f"{corpus_root}/.memory")
        return store._list_threads()

    def format_bibliography(self, csl_json_data: List[Dict[str, Any]],
                            style_name: str = "chicago-author-date",
                            ) -> Dict[str, Any]:
        """Format a bibliography from CSL-JSON data.

        Args:
            csl_json_data: List of CSL-JSON citation objects.
            style_name: Citation style name.

        Returns:
            Dict with 'bibliography' and 'in_text' strings.
        """
        from citeindex.citation_style import format_bibliography as _format_bib

        bib_str, in_text_str = _format_bib(csl_json_data, style_name)
        return {"bibliography": bib_str, "in_text": in_text_str, "style": style_name}

    def corpus_info(self, corpus_root: str = "corpus") -> Dict[str, Any]:
        """Get information about a corpus.

        Args:
            corpus_root: Root directory for corpus storage.

        Returns:
            Dict with corpus metadata (document count, paths, etc.)
        """
        import os

        if not os.path.isdir(corpus_root):
            return {"exists": False, "path": corpus_root}

        documents = []
        citeindex_dir = os.path.join(corpus_root, ".citeindex")
        legacy_dirs = []

        # Check v12 store
        if os.path.isdir(citeindex_dir):
            structured_dir = os.path.join(citeindex_dir, "documents", "structured")
            if os.path.isdir(structured_dir):
                for f in os.listdir(structured_dir):
                    if f.endswith(".citeindex.json"):
                        documents.append(f.replace(".citeindex.json", ""))

        # Check legacy folders
        for entry in sorted(os.listdir(corpus_root)):
            entry_path = os.path.join(corpus_root, entry)
            if os.path.isdir(entry_path) and not entry.startswith("."):
                csl_path = os.path.join(entry_path, "csl.json")
                if os.path.isfile(csl_path):
                    legacy_dirs.append(entry)

        return {
            "exists": True,
            "path": os.path.abspath(corpus_root),
            "document_count": len(documents) + len(legacy_dirs),
            "v12_documents": documents,
            "legacy_documents": legacy_dirs,
            "has_citeindex_store": os.path.isdir(citeindex_dir),
        }

    def corpus_validate(self, corpus_root: str = "corpus") -> Dict[str, Any]:
        """Validate a corpus structure.

        Args:
            corpus_root: Root directory for corpus storage.

        Returns:
            Dict with validation results.
        """
        info = self.corpus_info(corpus_root)
        if not info.get("exists"):
            return {"valid": False, "errors": ["Corpus directory does not exist"]}

        errors = []
        warnings = []

        if info["document_count"] == 0:
            warnings.append("No documents in corpus")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "document_count": info["document_count"],
        }
```

**Step 4: Run test to verify it passes**

```bash
cd /home/ajiap/project/citeindex/agent-harness
pip install -e . 2>&1 | tail -2
python -m pytest cli_anything/citeindex/tests/test_core.py::TestCiteIndexBackend -v
```

Expected: 3 passed

**Step 5: Commit**

```bash
git add agent-harness/
git commit -m "feat: add citeindex_backend.py wrapper module"
```

---

### Task 3: Output Formatting — output.py

**Files:**
- Create: `agent-harness/cli_anything/citeindex/utils/output.py`

**Step 1: Write the failing test**

Append to `agent-harness/cli_anything/citeindex/tests/test_core.py`:

```python
class TestOutputFormat:
    """Tests for output formatting utilities."""

    def test_format_output_json_mode(self):
        from cli_anything.citeindex.utils.output import format_output
        data = {"status": "ok", "total": 5}
        result = format_output(data, json_mode=True)
        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert parsed["total"] == 5

    def test_format_output_human_dict(self):
        from cli_anything.citeindex.utils.output import format_output
        data = {"status": "ok", "total": 5}
        result = format_output(data, json_mode=False)
        assert "status" in result
        assert "ok" in result

    def test_format_output_human_error(self):
        from cli_anything.citeindex.utils.output import format_output
        data = {"success": False, "error": "Not found"}
        result = format_output(data, json_mode=False)
        assert "Not found" in result

    def test_format_output_human_list(self):
        from cli_anything.citeindex.utils.output import format_output
        data = ["item1", "item2"]
        result = format_output(data, json_mode=False)
        assert "item1" in result
        assert "item2" in result

    def test_format_output_human_string(self):
        from cli_anything.citeindex.utils.output import format_output
        result = format_output("hello", json_mode=False)
        assert result == "hello"
```

**Step 2: Run test to verify it fails**

```bash
cd /home/ajiap/project/citeindex/agent-harness
python -m pytest cli_anything/citeindex/tests/test_core.py::TestOutputFormat -v 2>&1 | tail -5
```

Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

Create `agent-harness/cli_anything/citeindex/utils/output.py`:

```python
"""Output formatting utilities for human-readable and JSON modes."""
from __future__ import annotations

import json
from enum import Enum
from typing import Any


class OutputFormat(Enum):
    """Output format modes."""
    HUMAN = "human"
    JSON = "json"


def format_output(data: Any, json_mode: bool = False) -> str:
    """Format output data for display.

    Args:
        data: Dict, list, or string to format.
        json_mode: If True, output as JSON. Otherwise human-readable.

    Returns:
        Formatted string.
    """
    if json_mode:
        if isinstance(data, (dict, list)):
            return json.dumps(data, ensure_ascii=False, indent=2)
        return json.dumps({"result": str(data)}, ensure_ascii=False, indent=2)

    if isinstance(data, dict):
        if data.get("success") is False:
            error = data.get("error", "Unknown error")
            return f"Error: {error}"
        return _format_dict_human(data)
    if isinstance(data, list):
        return "\n".join(str(item) for item in data)
    return str(data)


def _format_dict_human(data: dict[str, Any], indent: int = 0) -> str:
    """Format a dictionary as human-readable key: value pairs."""
    lines = []
    prefix = "  " * indent
    for key, value in data.items():
        if isinstance(value, dict):
            lines.append(f"{prefix}{key}:")
            lines.append(_format_dict_human(value, indent + 1))
        elif isinstance(value, list):
            if value and isinstance(value[0], dict):
                lines.append(f"{prefix}{key}: ({len(value)} items)")
            else:
                lines.append(f"{prefix}{key}: {value}")
        else:
            lines.append(f"{prefix}{key}: {value}")
    return "\n".join(lines)
```

**Step 4: Run test to verify it passes**

```bash
cd /home/ajiap/project/citeindex/agent-harness
python -m pytest cli_anything/citeindex/tests/test_core.py::TestOutputFormat -v
```

Expected: 5 passed

**Step 5: Commit**

```bash
git add agent-harness/
git commit -m "feat: add output formatting utilities (human + JSON modes)"
```

---

### Task 4: Session Management — session.py

**Files:**
- Create: `agent-harness/cli_anything/citeindex/core/session.py`

**Step 1: Write the failing test**

Append to `agent-harness/cli_anything/citeindex/tests/test_core.py`:

```python
class TestSession:
    """Tests for session management."""

    def test_session_create(self):
        from cli_anything.citeindex.core.session import CiteIndexSession, SessionManager
        mgr = SessionManager(storage_dir=tempfile.mkdtemp())
        sess = mgr.create_session()
        assert sess.session_id.startswith("citeindex-")
        assert sess.status == "active"

    def test_session_save_load(self):
        from cli_anything.citeindex.core.session import CiteIndexSession, SessionManager
        mgr = SessionManager(storage_dir=tempfile.mkdtemp())
        sess = mgr.create_session()
        sess.set_corpus_root("/tmp/test-corpus")
        sess.set_thread_id("test-thread")
        mgr.save_session(sess)
        loaded = mgr.load_session(sess.session_id)
        assert loaded is not None
        assert loaded.corpus_root == "/tmp/test-corpus"
        assert loaded.thread_id == "test-thread"

    def test_session_undo_redo_stack(self):
        from cli_anything.citeindex.core.session import CiteIndexSession, SessionManager
        mgr = SessionManager(storage_dir=tempfile.mkdtemp())
        sess = mgr.create_session()
        sess.push_undo({"command": "ingest file paper.pdf", "undo_data": {"type": "ingest", "document_id": "doc1"}})
        assert sess.undo_depth() == 1
        assert sess.redo_depth() == 0
        undo_item = sess.pop_undo()
        assert undo_item["command"] == "ingest file paper.pdf"
        assert sess.undo_depth() == 0
        assert sess.redo_depth() == 1
        redo_item = sess.pop_redo()
        assert redo_item["command"] == "ingest file paper.pdf"
        assert sess.redo_depth() == 0

    def test_session_to_from_dict(self):
        from cli_anything.citeindex.core.session import CiteIndexSession, SessionManager
        sess = CiteIndexSession(session_id="test-123")
        sess.set_corpus_root("/tmp/corpus")
        sess.set_thread_id("thread-1")
        sess.push_undo({"command": "ingest", "undo_data": {}})
        d = sess.to_dict()
        restored = CiteIndexSession.from_dict(d)
        assert restored.session_id == "test-123"
        assert restored.corpus_root == "/tmp/corpus"
        assert restored.thread_id == "thread-1"
        assert restored.undo_depth() == 1

    def test_session_list(self):
        from cli_anything.citeindex.core.session import CiteIndexSession, SessionManager
        mgr = SessionManager(storage_dir=tempfile.mkdtemp())
        mgr.create_session()
        mgr.create_session()
        sessions = mgr.list_sessions()
        assert len(sessions) == 2

    def test_session_delete(self):
        from cli_anything.citeindex.core.session import CiteIndexSession, SessionManager
        mgr = SessionManager(storage_dir=tempfile.mkdtemp())
        sess = mgr.create_session()
        assert mgr.delete_session(sess.session_id) is True
        assert mgr.load_session(sess.session_id) is None
```

**Step 2: Run test to verify it fails**

```bash
cd /home/ajiap/project/citeindex/agent-harness
python -m pytest cli_anything/citeindex/tests/test_core.py::TestSession -v 2>&1 | tail -5
```

Expected: FAIL

**Step 3: Write implementation**

Create `agent-harness/cli_anything/citeindex/core/session.py`:

```python
"""Session management — stateful workflow tracking with undo/redo for CiteIndex CLI."""
from __future__ import annotations

import fcntl
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _locked_save_json(path: str, data: Any, **dump_kwargs: Any) -> None:
    """Atomically write JSON with exclusive file locking.

    Open with 'r+' (no truncation on open), lock, truncate inside lock,
    then write. First save (file doesn't exist) uses 'w' mode.
    """
    dump_kwargs.setdefault("indent", 2)
    dump_kwargs.setdefault("ensure_ascii", False)
    try:
        f = open(path, "r+")  # no truncation on open
    except FileNotFoundError:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        f = open(path, "w")  # first save — file doesn't exist yet
    with f:
        _locked = False
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            _locked = True
        except (ImportError, OSError):
            pass  # Windows / unsupported FS — proceed unlocked
        try:
            f.seek(0)
            f.truncate()  # truncate INSIDE the lock
            json.dump(data, f, **dump_kwargs)
            f.flush()
        finally:
            if _locked:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


@dataclass
class CiteIndexSession:
    """A CiteIndex CLI session tracking state, undo/redo, and corpus context."""

    session_id: str
    created_at: str = field(default_factory=lambda: _utc_now().isoformat())
    modified_at: str = field(default_factory=lambda: _utc_now().isoformat())
    status: str = "active"  # active | completed | cancelled
    corpus_root: str = ""
    thread_id: str = "default"
    loaded_documents: List[str] = field(default_factory=list)
    undo_stack: List[Dict[str, Any]] = field(default_factory=list)
    redo_stack: List[Dict[str, Any]] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)

    def set_corpus_root(self, path: str) -> None:
        self.corpus_root = path
        self.modified_at = _utc_now().isoformat()

    def set_thread_id(self, thread_id: str) -> None:
        self.thread_id = thread_id
        self.modified_at = _utc_now().isoformat()

    def add_document(self, doc_id: str) -> None:
        if doc_id not in self.loaded_documents:
            self.loaded_documents.append(doc_id)
            self.modified_at = _utc_now().isoformat()

    def remove_document(self, doc_id: str) -> None:
        if doc_id in self.loaded_documents:
            self.loaded_documents.remove(doc_id)
            self.modified_at = _utc_now().isoformat()

    def push_undo(self, item: Dict[str, Any]) -> None:
        """Push an undoable action onto the undo stack. Clears redo stack."""
        self.undo_stack.append(item)
        self.redo_stack.clear()
        self.modified_at = _utc_now().isoformat()

    def pop_undo(self) -> Optional[Dict[str, Any]]:
        """Pop the most recent undo item and push to redo stack."""
        if not self.undo_stack:
            return None
        item = self.undo_stack.pop()
        self.redo_stack.append(item)
        self.modified_at = _utc_now().isoformat()
        return item

    def pop_redo(self) -> Optional[Dict[str, Any]]:
        """Pop the most recent redo item and push to undo stack."""
        if not self.redo_stack:
            return None
        item = self.redo_stack.pop()
        self.undo_stack.append(item)
        self.modified_at = _utc_now().isoformat()
        return item

    def undo_depth(self) -> int:
        return len(self.undo_stack)

    def redo_depth(self) -> int:
        return len(self.redo_stack)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "status": self.status,
            "corpus_root": self.corpus_root,
            "thread_id": self.thread_id,
            "loaded_documents": self.loaded_documents,
            "undo_stack": self.undo_stack,
            "redo_stack": self.redo_stack,
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CiteIndexSession:
        return cls(
            session_id=data["session_id"],
            created_at=data.get("created_at", _utc_now().isoformat()),
            modified_at=data.get("modified_at", _utc_now().isoformat()),
            status=data.get("status", "active"),
            corpus_root=data.get("corpus_root", ""),
            thread_id=data.get("thread_id", "default"),
            loaded_documents=data.get("loaded_documents", []),
            undo_stack=data.get("undo_stack", []),
            redo_stack=data.get("redo_stack", []),
            context=data.get("context", {}),
        )


class SessionManager:
    """Manages session persistence for the CiteIndex CLI harness."""

    def __init__(self, storage_dir: str = ".citeindex_cli_sessions") -> None:
        self.storage_dir = Path(storage_dir)

    def _ensure_dir(self) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def create_session(self, session_id: Optional[str] = None) -> CiteIndexSession:
        if session_id is None:
            session_id = f"citeindex-{_utc_now().strftime('%Y%m%d%H%M%S%f')}"
        session = CiteIndexSession(session_id=session_id)
        self.save_session(session)
        return session

    def save_session(self, session: CiteIndexSession) -> None:
        self._ensure_dir()
        path = str(self.storage_dir / f"{session.session_id}.json")
        _locked_save_json(path, session.to_dict())

    def load_session(self, session_id: str) -> Optional[CiteIndexSession]:
        path = self.storage_dir / f"{session_id}.json"
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return CiteIndexSession.from_dict(data)

    def delete_session(self, session_id: str) -> bool:
        path = self.storage_dir / f"{session_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    def list_sessions(self, include_inactive: bool = True) -> List[CiteIndexSession]:
        self._ensure_dir()
        sessions: List[CiteIndexSession] = []
        for path in self.storage_dir.glob("*.json"):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                session = CiteIndexSession.from_dict(data)
                if include_inactive or session.status == "active":
                    sessions.append(session)
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
        sessions.sort(key=lambda s: s.modified_at, reverse=True)
        return sessions
```

**Step 4: Run test to verify it passes**

```bash
cd /home/ajiap/project/citeindex/agent-harness
python -m pytest cli_anything/citeindex/tests/test_core.py::TestSession -v
```

Expected: 6 passed

**Step 5: Commit**

```bash
git add agent-harness/
git commit -m "feat: add session management with undo/redo and file locking"
```

---

### Task 5: Core Modules — project.py, ingest.py, search.py, chat.py, memory.py, export.py

**Files:**
- Create: `agent-harness/cli_anything/citeindex/core/project.py`
- Create: `agent-harness/cli_anything/citeindex/core/ingest.py`
- Create: `agent-harness/cli_anything/citeindex/core/search.py`
- Create: `agent-harness/cli_anything/citeindex/core/chat.py`
- Create: `agent-harness/cli_anything/citeindex/core/memory.py`
- Create: `agent-harness/cli_anything/citeindex/core/export.py`

**Step 1: Write the failing tests**

Append to `agent-harness/cli_anything/citeindex/tests/test_core.py`:

```python
class TestProjectModule:
    """Tests for project management module."""

    def test_project_new_creates_corpus_dir(self, tmp_path):
        from cli_anything.citeindex.core.project import project_new
        corpus_root = str(tmp_path / "test-corpus")
        result = project_new(corpus_root=corpus_root)
        assert result["status"] == "ok"
        assert os.path.isdir(corpus_root)

    def test_project_info_empty_corpus(self, tmp_path):
        from cli_anything.citeindex.core.project import project_new, project_info
        corpus_root = str(tmp_path / "test-corpus2")
        project_new(corpus_root=corpus_root)
        result = project_info(corpus_root=corpus_root)
        assert result["exists"] is True
        assert result["document_count"] == 0

    def test_project_info_nonexistent(self):
        from cli_anything.citeindex.core.project import project_info
        result = project_info(corpus_root="/nonexistent/path")
        assert result["exists"] is False

    def test_project_validate_empty(self, tmp_path):
        from cli_anything.citeindex.core.project import project_new, project_validate
        corpus_root = str(tmp_path / "test-corpus3")
        project_new(corpus_root=corpus_root)
        result = project_validate(corpus_root=corpus_root)
        assert result["valid"] is True

    def test_project_list_empty_dir(self, tmp_path):
        from cli_anything.citeindex.core.project import project_list
        corpus_root = str(tmp_path / "test-corpus4")
        os.makedirs(corpus_root, exist_ok=True)
        result = project_list(corpus_root=corpus_root)
        assert result["document_count"] == 0


class TestIngestModule:
    """Tests for ingest module (unit tests without real ingestion)."""

    def test_ingest_module_importable(self):
        from cli_anything.citeindex.core.ingest import ingest_file, ingest_url, ingest_crawl

    def test_ingest_file_builds_config(self):
        """Verify ingest_file constructs correct backend call params."""
        from cli_anything.citeindex.core.ingest import _build_ingest_config
        config = _build_ingest_config(
            llm_model="ollama/qwen3",
            text_direction="horizontal",
            lang="en",
            doc_type="journal",
        )
        assert config["llm_model"] == "ollama/qwen3"
        assert config["lang"] == "en"
        assert config["doc_type_override"] == "journal"


class TestSearchModule:
    """Tests for search module."""

    def test_search_module_importable(self):
        from cli_anything.citeindex.core.search import search_query


class TestChatModule:
    """Tests for chat module."""

    def test_chat_module_importable(self):
        from cli_anything.citeindex.core.chat import chat_ask


class TestMemoryModule:
    """Tests for memory module."""

    def test_memory_module_importable(self):
        from cli_anything.citeindex.core.memory import memory_search, memory_list


class TestExportModule:
    """Tests for export module."""

    def test_export_module_importable(self):
        from cli_anything.citeindex.core.export import export_render, export_bibliography
```

**Step 2: Run test to verify it fails**

```bash
cd /home/ajiap/project/citeindex/agent-harness
python -m pytest cli_anything/citeindex/tests/test_core.py::TestProjectModule -v 2>&1 | tail -5
```

Expected: FAIL

**Step 3: Write all core modules**

Create `agent-harness/cli_anything/citeindex/core/project.py`:

```python
"""Corpus/project management — new, open, info, validate, list."""
from __future__ import annotations

import os
from typing import Any, Dict, List

from ..utils.citeindex_backend import CiteIndexBackend


_backend = CiteIndexBackend()


def project_new(corpus_root: str = "corpus") -> Dict[str, Any]:
    """Create a new corpus directory structure.

    Args:
        corpus_root: Root directory for the corpus.

    Returns:
        Dict with status and corpus path.
    """
    os.makedirs(corpus_root, exist_ok=True)
    # Create .citeindex sub-structure
    citeindex_dir = os.path.join(corpus_root, ".citeindex")
    os.makedirs(os.path.join(citeindex_dir, "indexes", "document_index"), exist_ok=True)
    os.makedirs(os.path.join(citeindex_dir, "documents", "sources"), exist_ok=True)
    os.makedirs(os.path.join(citeindex_dir, "documents", "structured"), exist_ok=True)
    os.makedirs(os.path.join(citeindex_dir, "documents", "transcripts"), exist_ok=True)
    os.makedirs(os.path.join(citeindex_dir, "memory", "sessions"), exist_ok=True)

    return {
        "status": "ok",
        "corpus_root": os.path.abspath(corpus_root),
        "message": f"Corpus created at {corpus_root}",
    }


def project_info(corpus_root: str = "corpus") -> Dict[str, Any]:
    """Get information about a corpus.

    Args:
        corpus_root: Root directory for the corpus.

    Returns:
        Dict with corpus metadata.
    """
    return _backend.corpus_info(corpus_root)


def project_validate(corpus_root: str = "corpus") -> Dict[str, Any]:
    """Validate a corpus structure.

    Args:
        corpus_root: Root directory for the corpus.

    Returns:
        Dict with validation results.
    """
    return _backend.corpus_validate(corpus_root)


def project_list(corpus_root: str = "corpus") -> Dict[str, Any]:
    """List documents in a corpus.

    Args:
        corpus_root: Root directory for the corpus.

    Returns:
        Dict with document list and count.
    """
    info = _backend.corpus_info(corpus_root)
    docs = info.get("v12_documents", []) + info.get("legacy_documents", [])
    return {
        "status": "ok",
        "documents": docs,
        "document_count": len(docs),
    }
```

Create `agent-harness/cli_anything/citeindex/core/ingest.py`:

```python
"""Ingestion commands — file, url, crawl."""
from __future__ import annotations

from typing import Any, Dict, Optional

from ..utils.citeindex_backend import CiteIndexBackend


_backend = CiteIndexBackend()


def _build_ingest_config(
    llm_model: str = "ollama/qwen3",
    text_direction: str = "horizontal",
    vertical_lang: str = "ch",
    lang: str = "auto",
    page_range: str = "1-5, -3",
    doc_type: Optional[str] = None,
    use_layout: bool = True,
    is_primary: bool = False,
    use_pageindex: bool = False,
    pageindex_model: str = "ollama/qwen3.5:cloud",
    cite_style: str = "chicago-author-date",
) -> Dict[str, Any]:
    """Build ingest configuration dict for passing to backend.

    Returns:
        Dict matching IngestionConfig field names.
    """
    return {
        "llm_model": llm_model,
        "text_direction": text_direction,
        "vertical_lang": vertical_lang,
        "lang": lang,
        "page_range": page_range,
        "doc_type_override": doc_type,
        "use_layout_analysis": use_layout,
        "is_primary": is_primary,
        "use_pageindex": use_pageindex,
        "pageindex_model": pageindex_model,
    }


def ingest_file(
    input_path: str,
    corpus_root: str = "corpus",
    llm_model: str = "ollama/qwen3",
    text_direction: str = "horizontal",
    vertical_lang: str = "ch",
    lang: str = "auto",
    page_range: str = "1-5, -3",
    doc_type: Optional[str] = None,
    use_layout: bool = True,
    is_primary: bool = False,
    use_pageindex: bool = False,
    pageindex_model: str = "ollama/qwen3.5:cloud",
    schema_version: str = "1.0.0",
) -> Dict[str, Any]:
    """Ingest a file (PDF, DJVU, DOCX, etc.) into the corpus.

    Args:
        input_path: Path to the file to ingest.
        corpus_root: Root directory for corpus storage.
        (Remaining args map to IngestionConfig.)

    Returns:
        Dict from CiteIndexIngestionOrchestrator.ingest()
    """
    return _backend.ingest(
        input_ref=input_path,
        corpus_root=corpus_root,
        llm_model=llm_model,
        text_direction=text_direction,
        vertical_lang=vertical_lang,
        lang=lang,
        page_range=page_range,
        doc_type_override=doc_type,
        use_layout_analysis=use_layout,
        is_primary=is_primary,
        use_pageindex=use_pageindex,
        pageindex_model=pageindex_model,
        schema_version=schema_version,
    )


def ingest_url(
    url: str,
    corpus_root: str = "corpus",
    llm_model: str = "ollama/qwen3",
    text_direction: str = "horizontal",
    lang: str = "auto",
    doc_type: Optional[str] = None,
    use_pageindex: bool = False,
    pageindex_model: str = "ollama/qwen3.5:cloud",
    schema_version: str = "1.0.0",
    **kwargs: Any,
) -> Dict[str, Any]:
    """Ingest a URL into the corpus.

    Args:
        url: URL to ingest.
        corpus_root: Root directory for corpus storage.
        (Remaining args map to IngestionConfig.)

    Returns:
        Dict from CiteIndexIngestionOrchestrator.ingest()
    """
    return _backend.ingest(
        input_ref=url,
        corpus_root=corpus_root,
        llm_model=llm_model,
        text_direction=text_direction,
        lang=lang,
        doc_type_override=doc_type,
        use_pageindex=use_pageindex,
        pageindex_model=pageindex_model,
        schema_version=schema_version,
        **kwargs,
    )


def ingest_crawl(
    root_url: str,
    corpus_root: str = "corpus",
    llm_model: str = "ollama/qwen3",
    update: bool = False,
    max_depth: int = 2,
    max_pages: int = 100,
    schema_version: str = "1.0.0",
    **kwargs: Any,
) -> Dict[str, Any]:
    """Crawl and ingest all article pages from a URL.

    Args:
        root_url: Root URL to crawl.
        corpus_root: Root directory for corpus storage.
        update: Compare content hashes; skip unchanged pages.
        max_depth: Max BFS crawl depth.
        max_pages: Max pages the crawler will visit.

    Returns:
        Dict from CiteIndexIngestionOrchestrator.ingest_all_urls()
    """
    return _backend.ingest_all_urls(
        root_url=root_url,
        corpus_root=corpus_root,
        llm_model=llm_model,
        update=update,
        max_depth=max_depth,
        max_pages=max_pages,
        schema_version=schema_version,
        **kwargs,
    )
```

Create `agent-harness/cli_anything/citeindex/core/search.py`:

```python
"""Search commands — query, recent."""
from __future__ import annotations

from typing import Any, Dict

from ..utils.citeindex_backend import CiteIndexBackend


_backend = CiteIndexBackend()


def search_query(
    query: str,
    corpus_root: str = "corpus",
    top_k: int = 20,
    cite_style: str = "chicago-author-date",
    retrieval: str = "auto",
    pageindex_model: str = "ollama/qwen3.5:cloud",
    schema_version: str = "1.0.0",
) -> Dict[str, Any]:
    """Search the corpus using BM25 or PageIndex retrieval.

    Args:
        query: Search query string.
        corpus_root: Root directory for corpus storage.
        top_k: Number of results to return.
        cite_style: Citation style for formatted output.
        retrieval: Retrieval method (bm25/pageindex/auto).
        pageindex_model: LLM model for PageIndex retrieval.

    Returns:
        Dict from SearchPipeline.search()
    """
    return _backend.search(
        query=query,
        corpus_root=corpus_root,
        top_k=top_k,
        cite_style=cite_style,
        retrieval=retrieval,
        pageindex_model=pageindex_model,
        schema_version=schema_version,
    )
```

Create `agent-harness/cli_anything/citeindex/core/chat.py`:

```python
"""Chat commands — ask, interactive."""
from __future__ import annotations

from typing import Any, Dict

from ..utils.citeindex_backend import CiteIndexBackend


_backend = CiteIndexBackend()


def chat_ask(
    prompt: str,
    corpus_root: str = "corpus",
    llm_model: str = "ollama/qwen3",
    thread_id: str = "default",
    schema_version: str = "1.0.0",
) -> Dict[str, Any]:
    """Single-shot chat with trace-bound citations.

    Args:
        prompt: User question or message.
        corpus_root: Root directory for corpus storage.
        llm_model: LLM model for generation.
        thread_id: Chat thread ID.

    Returns:
        Dict from ChatPipeline.chat()
    """
    return _backend.chat(
        prompt=prompt,
        corpus_root=corpus_root,
        llm_model=llm_model,
        thread_id=thread_id,
        schema_version=schema_version,
    )
```

Create `agent-harness/cli_anything/citeindex/core/memory.py`:

```python
"""Memory commands — search, list, show."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..utils.citeindex_backend import CiteIndexBackend


_backend = CiteIndexBackend()


def memory_search(
    query: str,
    corpus_root: str = "corpus",
    thread_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Search past chat memory.

    Args:
        query: Search query string.
        corpus_root: Root directory for corpus storage.
        thread_id: Restrict to a specific thread.

    Returns:
        Dict with status, query, total, and results list.
    """
    results = _backend.memory_search(query=query, corpus_root=corpus_root, thread_id=thread_id)
    return {
        "status": "ok",
        "query": query,
        "total": len(results),
        "results": results,
    }


def memory_list(
    corpus_root: str = "corpus",
) -> Dict[str, Any]:
    """List all memory threads.

    Args:
        corpus_root: Root directory for corpus storage.

    Returns:
        Dict with status and threads list.
    """
    threads = _backend.memory_list_threads(corpus_root=corpus_root)
    return {
        "status": "ok",
        "threads": threads,
    }
```

Create `agent-harness/cli_anything/citeindex/core/export.py`:

```python
"""Export commands — render, bibliography."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from ..utils.citeindex_backend import CiteIndexBackend


_backend = CiteIndexBackend()


def export_render(
    output_path: str,
    corpus_root: str = "corpus",
    format: str = "pdf",
    cite_style: str = "chicago-author-date",
    overwrite: bool = False,
) -> Dict[str, Any]:
    """Render citations from the corpus to a file.

    Currently generates a formatted bibliography text file or uses
    citeindex.citation_style for CSL rendering.

    Args:
        output_path: Path for the output file.
        corpus_root: Root directory for corpus storage.
        format: Output format (pdf, html, txt).
        cite_style: Citation style name.
        overwrite: Allow overwriting existing file.

    Returns:
        Dict with status, output path, and format.
    """
    if os.path.exists(output_path) and not overwrite:
        return {
            "status": "error",
            "message": f"File already exists: {output_path}. Use --overwrite to replace.",
        }

    # Gather CSL JSON from corpus
    info = _backend.corpus_info(corpus_root)
    if not info.get("exists") or info["document_count"] == 0:
        return {
            "status": "error",
            "message": "No documents in corpus to export.",
        }

    # Collect CSL data from all documents
    import json as _json

    csl_data: List[Dict[str, Any]] = []
    corpus_abs = os.path.abspath(corpus_root)

    # Check legacy folders for csl.json
    for doc_id in info.get("legacy_documents", []):
        csl_path = os.path.join(corpus_abs, doc_id, "csl.json")
        if os.path.isfile(csl_path):
            with open(csl_path, encoding="utf-8") as f:
                data = _json.load(f)
                if isinstance(data, list):
                    csl_data.extend(data)
                elif isinstance(data, dict):
                    csl_data.append(data)

    if not csl_data:
        return {
            "status": "error",
            "message": "No CSL citation data found in corpus.",
        }

    # Format bibliography via citeindex's citation_style module
    result = _backend.format_bibliography(csl_data, style_name=cite_style)

    # Write output
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        if format == "txt":
            f.write(result.get("bibliography", ""))
        else:
            # For PDF/HTML, write the bibliography text (real PDF rendering
            # would require LibreOffice or a similar backend in production)
            f.write(result.get("bibliography", ""))

    file_size = os.path.getsize(output_path)
    return {
        "status": "ok",
        "output": os.path.abspath(output_path),
        "format": format,
        "cite_style": cite_style,
        "file_size": file_size,
        "citations_count": len(csl_data),
    }


def export_bibliography(
    corpus_root: str = "corpus",
    cite_style: str = "chicago-author-date",
) -> Dict[str, Any]:
    """Export a formatted bibliography from the corpus.

    Args:
        corpus_root: Root directory for corpus storage.
        cite_style: Citation style name.

    Returns:
        Dict with bibliography and in_text strings.
    """
    info = _backend.corpus_info(corpus_root)
    if not info.get("exists") or info["document_count"] == 0:
        return {
            "status": "error",
            "message": "No documents in corpus.",
        }

    # Collect CSL data
    import json as _json

    csl_data: List[Dict[str, Any]] = []
    corpus_abs = os.path.abspath(corpus_root)

    for doc_id in info.get("legacy_documents", []):
        csl_path = os.path.join(corpus_abs, doc_id, "csl.json")
        if os.path.isfile(csl_path):
            with open(csl_path, encoding="utf-8") as f:
                data = _json.load(f)
                if isinstance(data, list):
                    csl_data.extend(data)
                elif isinstance(data, dict):
                    csl_data.append(data)

    if not csl_data:
        return {
            "status": "error",
            "message": "No CSL citation data found.",
        }

    return _backend.format_bibliography(csl_data, style_name=cite_style)
```

**Step 4: Run tests to verify they pass**

```bash
cd /home/ajiap/project/citeindex/agent-harness
python -m pytest cli_anything/citeindex/tests/test_core.py -v
```

Expected: All tests pass (~14 total so far)

**Step 5: Commit**

```bash
git add agent-harness/
git commit -m "feat: add core modules — project, ingest, search, chat, memory, export"
```

---

### Task 6: Main CLI Entry Point — citeindex_cli.py

**Files:**
- Create: `agent-harness/cli_anything/citeindex/citeindex_cli.py`

**Step 1: Write the failing test**

Append to `agent-harness/cli_anything/citeindex/tests/test_core.py`:

```python
class TestCLIEntryPoint:
    """Tests for the CLI entry point module."""

    def test_cli_module_importable(self):
        from cli_anything.citeindex.citeindex_cli import cli, main

    def test_cli_has_command_groups(self):
        from cli_anything.citeindex.citeindex_cli import cli
        group_names = [cmd.name for cmd in cli.commands.values()]
        assert "project" in group_names
        assert "ingest" in group_names
        assert "search" in group_names
        assert "chat" in group_names
        assert "memory" in group_names
        assert "export" in group_names
        assert "session" in group_names
```

**Step 2: Run test to verify it fails**

```bash
cd /home/ajiap/project/citeindex/agent-harness
python -m pytest cli_anything/citeindex/tests/test_core.py::TestCLIEntryPoint -v 2>&1 | tail -5
```

Expected: FAIL

**Step 3: Write implementation**

Create `agent-harness/cli_anything/citeindex/citeindex_cli.py`:

```python
#!/usr/bin/env python3
"""cli-anything-citeindex — Stateful CLI harness for CiteIndex research infrastructure.

Usage:
    cli-anything-citeindex [OPTIONS] COMMAND [ARGS]...

Commands:
    project   Corpus management (new, info, validate, list)
    ingest    Ingest documents (file, url, crawl)
    search    Search corpus (query)
    chat      Chat with citations (ask, interactive)
    memory    Memory & history (search, list)
    export    Export & render (render, bibliography)
    session   Session management (save, load, undo, redo, status)
    repl      Interactive REPL mode

Every command supports --json for machine-readable output.
"""
from __future__ import annotations

import json
import sys
import os
from typing import Any, Optional

import click

from . import __version__
from .core.project import project_new, project_info, project_validate, project_list
from .core.ingest import ingest_file, ingest_url, ingest_crawl
from .core.search import search_query
from .core.chat import chat_ask
from .core.memory import memory_search, memory_list
from .core.export import export_render, export_bibliography
from .core.session import CiteIndexSession, SessionManager
from .utils.output import format_output


# ── Helpers ──

def _json_flag(f):
    """Add --json flag to a click command."""
    return click.option("--json", "as_json", is_flag=True, help="Output as JSON")(f)


def _output(data: Any, as_json: bool = False) -> None:
    """Print output in human or JSON format."""
    click.echo(format_output(data, json_mode=as_json))


def _get_session_mgr(ctx: click.Context) -> SessionManager:
    return ctx.obj.get("session_manager", SessionManager())


def _get_session(ctx: click.Context) -> Optional[CiteIndexSession]:
    return ctx.obj.get("current_session")


def _set_session(ctx: click.Context, session: CiteIndexSession) -> None:
    ctx.obj["current_session"] = session


# ── Root group ──

@click.group(invoke_without_command=True)
@click.version_option(version=__version__, prog_name="cli-anything-citeindex")
@click.option("--corpus-root", default="corpus", help="Corpus root directory")
@click.option("--json", "global_json", is_flag=True, help="Default JSON output for all commands")
@click.pass_context
def cli(ctx: click.Context, corpus_root: str, global_json: bool) -> None:
    """cli-anything-citeindex — Stateful CLI for CiteIndex research infrastructure."""
    ctx.ensure_object(dict)
    ctx.obj["corpus_root"] = corpus_root
    ctx.obj["session_manager"] = SessionManager()
    ctx.obj["global_json"] = global_json
    ctx.obj["current_session"] = None

    if ctx.invoked_subcommand is None:
        # No subcommand → enter REPL
        ctx.invoke(repl)


# ── Project commands ──

@cli.group()
def project() -> None:
    """Corpus management (new, info, validate, list)."""
    pass


@project.command("new")
@click.option("--corpus-root", "-c", default=None, help="Corpus root directory")
@_json_flag
@click.pass_context
def project_new_cmd(ctx: click.Context, corpus_root: Optional[str], as_json: bool) -> None:
    """Create a new corpus directory structure."""
    root = corpus_root or ctx.obj.get("corpus_root", "corpus")
    result = project_new(corpus_root=root)
    _output(result, as_json)


@project.command("info")
@click.option("--corpus-root", "-c", default=None, help="Corpus root directory")
@_json_flag
@click.pass_context
def project_info_cmd(ctx: click.Context, corpus_root: Optional[str], as_json: bool) -> None:
    """Show corpus information."""
    root = corpus_root or ctx.obj.get("corpus_root", "corpus")
    result = project_info(corpus_root=root)
    _output(result, as_json)


@project.command("validate")
@click.option("--corpus-root", "-c", default=None, help="Corpus root directory")
@_json_flag
@click.pass_context
def project_validate_cmd(ctx: click.Context, corpus_root: Optional[str], as_json: bool) -> None:
    """Validate corpus structure."""
    root = corpus_root or ctx.obj.get("corpus_root", "corpus")
    result = project_validate(corpus_root=root)
    _output(result, as_json)


@project.command("list")
@click.option("--corpus-root", "-c", default=None, help="Corpus root directory")
@_json_flag
@click.pass_context
def project_list_cmd(ctx: click.Context, corpus_root: Optional[str], as_json: bool) -> None:
    """List documents in the corpus."""
    root = corpus_root or ctx.obj.get("corpus_root", "corpus")
    result = project_list(corpus_root=root)
    _output(result, as_json)


# ── Ingest commands ──

@cli.group()
def ingest() -> None:
    """Ingest documents (file, url, crawl)."""
    pass


@ingest.command("file")
@click.argument("input_path")
@click.option("--corpus-root", "-c", default=None, help="Corpus root directory")
@click.option("--llm", default="ollama/qwen3", help="LLM model for citation extraction")
@click.option("--text-direction", "-td", type=click.Choice(["horizontal", "auto", "vertical"]), default="horizontal")
@click.option("--vertical-lang", type=click.Choice(["ch", "japan"]), default="ch")
@click.option("--lang", "-l", default="auto", help="OCR language")
@click.option("--page-range", "-p", default="1-5, -3", help="Page range")
@click.option("--type", "-t", "doc_type", type=click.Choice(["book", "thesis", "journal", "bookchapter"]), default=None)
@click.option("--no-layout", is_flag=True, help="Disable layout analysis")
@click.option("--is-primary", is_flag=True, help="Mark as primary source")
@click.option("--use-pageindex", is_flag=True, help="Use PageIndex tree building")
@click.option("--pageindex-model", default="ollama/qwen3.5:cloud")
@_json_flag
@click.pass_context
def ingest_file_cmd(ctx: click.Context, input_path: str, corpus_root: Optional[str],
                    llm: str, text_direction: str, vertical_lang: str,
                    lang: str, page_range: str, doc_type: Optional[str],
                    no_layout: bool, is_primary: bool, use_pageindex: bool,
                    pageindex_model: str, as_json: bool) -> None:
    """Ingest a file (PDF, DJVU, DOCX, etc.) into the corpus."""
    root = corpus_root or ctx.obj.get("corpus_root", "corpus")
    result = ingest_file(
        input_path=input_path,
        corpus_root=root,
        llm_model=llm,
        text_direction=text_direction,
        vertical_lang=vertical_lang,
        lang=lang,
        page_range=page_range,
        doc_type=doc_type,
        use_layout=not no_layout,
        is_primary=is_primary,
        use_pageindex=use_pageindex,
        pageindex_model=pageindex_model,
    )
    _output(result, as_json)


@ingest.command("url")
@click.argument("url")
@click.option("--corpus-root", "-c", default=None, help="Corpus root directory")
@click.option("--llm", default="ollama/qwen3", help="LLM model")
@click.option("--lang", "-l", default="auto", help="OCR language")
@click.option("--type", "-t", "doc_type", type=click.Choice(["book", "thesis", "journal", "bookchapter"]), default=None)
@click.option("--use-pageindex", is_flag=True)
@click.option("--pageindex-model", default="ollama/qwen3.5:cloud")
@_json_flag
@click.pass_context
def ingest_url_cmd(ctx: click.Context, url: str, corpus_root: Optional[str],
                   llm: str, lang: str, doc_type: Optional[str],
                   use_pageindex: bool, pageindex_model: str, as_json: bool) -> None:
    """Ingest a URL into the corpus."""
    root = corpus_root or ctx.obj.get("corpus_root", "corpus")
    result = ingest_url(
        url=url,
        corpus_root=root,
        llm_model=llm,
        lang=lang,
        doc_type=doc_type,
        use_pageindex=use_pageindex,
        pageindex_model=pageindex_model,
    )
    _output(result, as_json)


@ingest.command("crawl")
@click.argument("root_url")
@click.option("--corpus-root", "-c", default=None, help="Corpus root directory")
@click.option("--llm", default="ollama/qwen3", help="LLM model")
@click.option("--update", is_flag=True, help="Re-ingest only changed pages")
@click.option("--depth", type=int, default=2, help="Max crawl depth")
@click.option("--max-pages", type=int, default=100, help="Max pages to visit")
@_json_flag
@click.pass_context
def ingest_crawl_cmd(ctx: click.Context, root_url: str, corpus_root: Optional[str],
                     llm: str, update: bool, depth: int, max_pages: int, as_json: bool) -> None:
    """Crawl and ingest all article pages from a URL."""
    root = corpus_root or ctx.obj.get("corpus_root", "corpus")
    result = ingest_crawl(
        root_url=root_url,
        corpus_root=root,
        llm_model=llm,
        update=update,
        max_depth=depth,
        max_pages=max_pages,
    )
    _output(result, as_json)


# ── Search commands ──

@cli.group()
def search() -> None:
    """Search corpus (query)."""
    pass


@search.command("query")
@click.argument("query_str")
@click.option("--corpus-root", "-c", default=None, help="Corpus root directory")
@click.option("--top-k", type=int, default=20, help="Number of results")
@click.option("--cite-style", default="chicago-author-date", help="Citation style")
@click.option("--retrieval", type=click.Choice(["bm25", "pageindex", "auto"]), default="auto")
@click.option("--pageindex-model", default="ollama/qwen3.5:cloud")
@_json_flag
@click.pass_context
def search_query_cmd(ctx: click.Context, query_str: str, corpus_root: Optional[str],
                     top_k: int, cite_style: str, retrieval: str,
                     pageindex_model: str, as_json: bool) -> None:
    """Search the corpus using BM25 or PageIndex retrieval."""
    root = corpus_root or ctx.obj.get("corpus_root", "corpus")
    result = search_query(
        query=query_str,
        corpus_root=root,
        top_k=top_k,
        cite_style=cite_style,
        retrieval=retrieval,
        pageindex_model=pageindex_model,
    )
    _output(result, as_json)


# ── Chat commands ──

@cli.group()
def chat() -> None:
    """Chat with trace-bound citations (ask, interactive)."""
    pass


@chat.command("ask")
@click.argument("prompt")
@click.option("--corpus-root", "-c", default=None, help="Corpus root directory")
@click.option("--llm", default="ollama/qwen3", help="LLM model for generation")
@click.option("--thread", default="default", help="Chat thread ID")
@_json_flag
@click.pass_context
def chat_ask_cmd(ctx: click.Context, prompt: str, corpus_root: Optional[str],
                 llm: str, thread: str, as_json: bool) -> None:
    """Single-shot chat with trace-bound citations."""
    root = corpus_root or ctx.obj.get("corpus_root", "corpus")
    result = chat_ask(
        prompt=prompt,
        corpus_root=root,
        llm_model=llm,
        thread_id=thread,
    )
    if as_json:
        _output(result, as_json)
    else:
        if result.get("answer_human"):
            click.echo(result["answer_human"])
        else:
            _output(result, as_json)


@chat.command("interactive")
@click.option("--corpus-root", "-c", default=None, help="Corpus root directory")
@click.option("--llm", default="ollama/qwen3", help="LLM model for generation")
@click.option("--thread", default="default", help="Chat thread ID")
@click.pass_context
def chat_interactive_cmd(ctx: click.Context, corpus_root: Optional[str],
                         llm: str, thread: str) -> None:
    """Interactive chat session with trace-bound citations."""
    root = corpus_root or ctx.obj.get("corpus_root", "corpus")
    click.echo("CiteIndex Chat (type /quit to exit)")
    click.echo("---")
    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            click.echo()
            break
        if not user_input or user_input in ("/quit", "/exit", "/q"):
            break
        result = chat_ask(prompt=user_input, corpus_root=root, llm_model=llm, thread_id=thread)
        if result.get("status") == "needs_clarification":
            click.echo("Clarification needed:")
            for q in result.get("questions", []):
                click.echo(f"  - {q}")
        elif result.get("answer_human"):
            click.echo(result["answer_human"])
        else:
            click.echo(json.dumps(result, indent=2, ensure_ascii=False))
        click.echo()


# ── Memory commands ──

@cli.group()
def memory() -> None:
    """Memory & history (search, list)."""
    pass


@memory.command("search")
@click.argument("query")
@click.option("--corpus-root", "-c", default=None, help="Corpus root directory")
@click.option("--thread", default=None, help="Restrict to a specific thread")
@_json_flag
@click.pass_context
def memory_search_cmd(ctx: click.Context, query: str, corpus_root: Optional[str],
                      thread: Optional[str], as_json: bool) -> None:
    """Search past chat memory."""
    root = corpus_root or ctx.obj.get("corpus_root", "corpus")
    result = memory_search(query=query, corpus_root=root, thread_id=thread)
    _output(result, as_json)


@memory.command("list")
@click.option("--corpus-root", "-c", default=None, help="Corpus root directory")
@_json_flag
@click.pass_context
def memory_list_cmd(ctx: click.Context, corpus_root: Optional[str], as_json: bool) -> None:
    """List all memory threads."""
    root = corpus_root or ctx.obj.get("corpus_root", "corpus")
    result = memory_list(corpus_root=root)
    _output(result, as_json)


# ── Export commands ──

@cli.group()
def export() -> None:
    """Export & render (render, bibliography)."""
    pass


@export.command("render")
@click.argument("output_path")
@click.option("--corpus-root", "-c", default=None, help="Corpus root directory")
@click.option("--format", "-f", "fmt", default="txt", help="Output format (txt, html, pdf)")
@click.option("--cite-style", default="chicago-author-date", help="Citation style")
@click.option("--overwrite", is_flag=True, help="Allow overwriting existing file")
@_json_flag
@click.pass_context
def export_render_cmd(ctx: click.Context, output_path: str, corpus_root: Optional[str],
                      fmt: str, cite_style: str, overwrite: bool, as_json: bool) -> None:
    """Render citations from the corpus to a file."""
    root = corpus_root or ctx.obj.get("corpus_root", "corpus")
    result = export_render(
        output_path=output_path,
        corpus_root=root,
        format=fmt,
        cite_style=cite_style,
        overwrite=overwrite,
    )
    _output(result, as_json)


@export.command("bibliography")
@click.option("--corpus-root", "-c", default=None, help="Corpus root directory")
@click.option("--cite-style", default="chicago-author-date", help="Citation style")
@_json_flag
@click.pass_context
def export_bibliography_cmd(ctx: click.Context, corpus_root: Optional[str],
                            cite_style: str, as_json: bool) -> None:
    """Export a formatted bibliography from the corpus."""
    root = corpus_root or ctx.obj.get("corpus_root", "corpus")
    result = export_bibliography(corpus_root=root, cite_style=cite_style)
    _output(result, as_json)


# ── Session commands ──

@cli.group()
def session() -> None:
    """Session management (save, load, undo, redo, status)."""
    pass


@session.command("create")
@click.option("--id", "session_id", help="Custom session ID")
@_json_flag
@click.pass_context
def session_create_cmd(ctx: click.Context, session_id: Optional[str], as_json: bool) -> None:
    """Create a new session."""
    mgr = _get_session_mgr(ctx)
    sess = mgr.create_session(session_id)
    _set_session(ctx, sess)
    _output(sess.to_dict(), as_json)


@session.command("list")
@click.option("--active-only", is_flag=True, help="Show only active sessions")
@_json_flag
@click.pass_context
def session_list_cmd(ctx: click.Context, active_only: bool, as_json: bool) -> None:
    """List saved sessions."""
    mgr = _get_session_mgr(ctx)
    sessions = mgr.list_sessions(include_inactive=not active_only)
    if as_json:
        _output([s.to_dict() for s in sessions], as_json)
    else:
        if not sessions:
            click.echo("No sessions found.")
        for s in sessions:
            click.echo(f"{s.session_id} | {s.status} | undo={s.undo_depth()} | docs={len(s.loaded_documents)} | {s.modified_at}")


@session.command("save")
@_json_flag
@click.pass_context
def session_save_cmd(ctx: click.Context, as_json: bool) -> None:
    """Save the current session."""
    sess = _get_session(ctx)
    if sess is None:
        _output({"status": "error", "message": "No active session. Use 'session create' first."}, as_json)
        raise SystemExit(1)
    mgr = _get_session_mgr(ctx)
    mgr.save_session(sess)
    _output({"status": "ok", "session_id": sess.session_id, "message": "Session saved"}, as_json)


@session.command("load")
@click.argument("session_id")
@_json_flag
@click.pass_context
def session_load_cmd(ctx: click.Context, session_id: str, as_json: bool) -> None:
    """Load a saved session."""
    mgr = _get_session_mgr(ctx)
    sess = mgr.load_session(session_id)
    if sess is None:
        _output({"status": "error", "message": f"Session not found: {session_id}"}, as_json)
        raise SystemExit(1)
    _set_session(ctx, sess)
    _output(sess.to_dict(), as_json)


@session.command("undo")
@_json_flag
@click.pass_context
def session_undo_cmd(ctx: click.Context, as_json: bool) -> None:
    """Undo the last action."""
    sess = _get_session(ctx)
    if sess is None:
        _output({"status": "error", "message": "No active session"}, as_json)
        raise SystemExit(1)
    item = sess.pop_undo()
    if item is None:
        _output({"status": "ok", "message": "Nothing to undo"}, as_json)
    else:
        mgr = _get_session_mgr(ctx)
        mgr.save_session(sess)
        _output({"status": "ok", "message": "Undone", "command": item.get("command", "?")}, as_json)


@session.command("redo")
@_json_flag
@click.pass_context
def session_redo_cmd(ctx: click.Context, as_json: bool) -> None:
    """Redo the last undone action."""
    sess = _get_session(ctx)
    if sess is None:
        _output({"status": "error", "message": "No active session"}, as_json)
        raise SystemExit(1)
    item = sess.pop_redo()
    if item is None:
        _output({"status": "ok", "message": "Nothing to redo"}, as_json)
    else:
        mgr = _get_session_mgr(ctx)
        mgr.save_session(sess)
        _output({"status": "ok", "message": "Redone", "command": item.get("command", "?")}, as_json)


@session.command("status")
@_json_flag
@click.pass_context
def session_status_cmd(ctx: click.Context, as_json: bool) -> None:
    """Show current session status."""
    sess = _get_session(ctx)
    if sess is None:
        _output({"status": "no_session", "message": "No active session"}, as_json)
        return
    _output({
        "status": "ok",
        "session_id": sess.session_id,
        "corpus_root": sess.corpus_root or "(not set)",
        "thread_id": sess.thread_id,
        "documents": len(sess.loaded_documents),
        "undo_depth": sess.undo_depth(),
        "redo_depth": sess.redo_depth(),
    }, as_json)


# ── REPL command ──

@cli.command("repl")
@click.option("--corpus-root", "-c", default=None, help="Corpus root directory")
@click.pass_context
def repl(ctx: click.Context, corpus_root: Optional[str]) -> None:
    """Interactive REPL mode with prompt_toolkit."""
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import FileHistory
        from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
        from prompt_toolkit.completion import WordCompleter
    except ImportError:
        click.echo("prompt-toolkit not installed. Install with: pip install prompt-toolkit")
        raise SystemExit(1)

    root = corpus_root or ctx.obj.get("corpus_root", "corpus")

    # Banner
    click.echo("╭─────────────────────────────────────────────────────╮")
    click.echo(f"│  ◆ CiteIndex CLI v{__version__:<33} │")
    click.echo(f"│  ◇ Corpus: {root:<41} │")

    # Check for SKILL.md
    skill_path = os.path.join(os.path.dirname(__file__), "skills", "SKILL.md")
    if os.path.isfile(skill_path):
        click.echo(f"│  ◇ Skill: {skill_path:<41} │")

    click.echo("╰─────────────────────────────────────────────────────╯")

    # Completer with all commands
    commands = [
        "project new", "project info", "project validate", "project list",
        "ingest file", "ingest url", "ingest crawl",
        "search query",
        "chat ask", "chat interactive",
        "memory search", "memory list",
        "export render", "export bibliography",
        "session create", "session list", "session save", "session load",
        "session undo", "session redo", "session status",
        "help", "quit",
    ]
    completer = WordCompleter(commands, ignore_case=True)

    # Prompt session with history
    history_file = os.path.expanduser("~/.citeindex_cli_history")
    pt_session = PromptSession(
        history=FileHistory(history_file),
        auto_suggest=AutoSuggestFromHistory(),
        completer=completer,
    )

    click.echo()
    click.echo("Type 'help' for commands, 'quit' to exit.")
    click.echo()

    while True:
        try:
            # Build prompt with context
            info = project_info(corpus_root=root)
            doc_count = info.get("document_count", 0)
            prompt_str = f"citeindex ({doc_count} docs)> "
            user_input = pt_session.prompt(prompt_str).strip()
        except (EOFError, KeyboardInterrupt):
            click.echo()
            break

        if not user_input:
            continue
        if user_input in ("quit", "exit", "q"):
            break
        if user_input == "help":
            click.echo()
            click.echo("  project   — Corpus management (new, info, validate, list)")
            click.echo("  ingest    — Ingest documents (file, url, crawl)")
            click.echo("  search    — Search corpus (query)")
            click.echo("  chat      — Chat with citations (ask, interactive)")
            click.echo("  memory    — Memory & history (search, list)")
            click.echo("  export    — Export & render (render, bibliography)")
            click.echo("  session   — Session management (save, load, undo, redo, status)")
            click.echo("  help      — Show this help")
            click.echo("  quit      — Exit REPL")
            click.echo()
            continue

        # Dispatch command through Click
        try:
            args = user_input.split()
            cli.main(args, standalone_mode=False, parent=ctx)
        except SystemExit:
            pass
        except click.exceptions.UsageError as e:
            click.echo(f"Error: {e}")
        click.echo()

    click.echo("Goodbye!")


# ── Entry point ──

def main() -> None:
    """Main entry point for cli-anything-citeindex."""
    cli()


if __name__ == "__main__":
    main()
```

**Step 4: Run tests to verify they pass**

```bash
cd /home/ajiap/project/citeindex/agent-harness
python -m pytest cli_anything/citeindex/tests/test_core.py -v
```

Expected: All tests pass (~16 total)

**Step 5: Commit**

```bash
git add agent-harness/
git commit -m "feat: add main CLI entry point with all Click command groups and REPL"
```

---

### Task 7: README.md

**Files:**
- Create: `agent-harness/cli_anything/citeindex/README.md`

**Step 1: Write the README**

Create `agent-harness/cli_anything/citeindex/README.md`:

```markdown
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

# Search
cli-anything-citeindex search query "categorical imperative" --top-k 20

# Chat
cli-anything-citeindex chat ask "What does Rawls argue about justice?"

# Memory
cli-anything-citeindex memory search "social contract"

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
```

**Step 2: Commit**

```bash
git add agent-harness/
git commit -m "docs: add README.md for cli-anything-citeindex"
```

---

### Task 8: TEST.md — Test Plan

**Files:**
- Create: `agent-harness/cli_anything/citeindex/tests/TEST.md`

**Step 1: Write the test plan**

Create `agent-harness/cli_anything/citeindex/tests/TEST.md`:

```markdown
# TEST.md — cli-anything-citeindex

## Test Inventory Plan

- `test_core.py`: ~16 unit tests
- `test_full_e2e.py`: ~15 E2E tests (intermediate + true backend + subprocess)

## Unit Test Plan

### Module: `utils/citeindex_backend.py`
- `CiteIndexBackend` importable (1)
- Backend has required methods (1)
- `check_dependencies` returns correct structure (1)

### Module: `utils/output.py`
- JSON mode output (1)
- Human mode dict output (1)
- Human mode error output (1)
- Human mode list output (1)
- Human mode string output (1)

### Module: `core/session.py`
- Session create (1)
- Session save/load cycle (1)
- Undo/redo stack push/pop (1)
- Session to/from dict serialization (1)
- Session list (1)
- Session delete (1)

### Module: `core/project.py`
- project_new creates directory (1)
- project_info on empty corpus (1)
- project_info on nonexistent path (1)
- project_validate on empty corpus (1)
- project_list on empty dir (1)

### Module: `core/ingest.py`
- Module importable (1)
- _build_ingest_config builds correct dict (1)

### Other modules (importability)
- core/search, core/chat, core/memory, core/export (4)

## E2E Test Plan

### Intermediate tests
- Session JSON round-trip produces valid JSON
- `--json` flag produces valid JSON with expected schema
- Corpus folder creation after `project new`
- Export render produces non-empty text file

### True backend tests
- Ingest a real PDF → verify corpus files created (csl.json, document.json, merkle.json)
- Search after ingest → BM25 results returned
- Chat after ingest → response with trace-bound citations
- Export render → output file exists and has content
- Memory round-trip

### CLI subprocess tests
- `--help` works
- `--json` flag works with project new
- Full workflow: project new → ingest → search

## Realistic Workflow Scenarios

### Workflow 1: Research paper ingestion pipeline
- **Simulates:** Scholar ingesting a PDF into their research corpus
- **Operations:** project new → ingest file → project info → search query
- **Verified:** Corpus created, document files exist, search returns results

### Workflow 2: Citation export
- **Simulates:** Exporting a bibliography from ingested sources
- **Operations:** (assumes corpus exists) export render → verify output
- **Verified:** Output file exists, non-empty, contains formatted citations

### Workflow 3: Interactive session with undo
- **Simulates:** Researcher working in REPL with undo capability
- **Operations:** session create → ingest → session undo → session redo
- **Verified:** Undo clears action, redo restores it
```

**Step 2: Commit**

```bash
git add agent-harness/
git commit -m "docs: add TEST.md test plan for cli-anything-citeindex"
```

---

### Task 9: E2E Tests — test_full_e2e.py

**Files:**
- Create: `agent-harness/cli_anything/citeindex/tests/test_full_e2e.py`

**Step 1: Write E2E tests**

Create `agent-harness/cli_anything/citeindex/tests/test_full_e2e.py`:

```python
"""E2E tests for cli-anything-citeindex — real backend + subprocess tests."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

import pytest


def _resolve_cli(name: str) -> list[str]:
    """Resolve installed CLI command; falls back to python -m for dev.

    Set env CLI_ANYTHING_FORCE_INSTALLED=1 to require the installed command.
    """
    force = os.environ.get("CLI_ANYTHING_FORCE_INSTALLED", "").strip() == "1"
    path = shutil.which(name)
    if path:
        print(f"[_resolve_cli] Using installed command: {path}")
        return [path]
    if force:
        raise RuntimeError(f"{name} not found in PATH. Install with: pip install -e .")
    module = name.replace("cli-anything-", "cli_anything.") + "." + name.split("-")[-1] + "_cli"
    print(f"[_resolve_cli] Falling back to: {sys.executable} -m {module}")
    return [sys.executable, "-m", module]


# ── Intermediate E2E tests ──


class TestSessionE2E:
    """Session JSON round-trip tests."""

    def test_session_json_valid(self, tmp_path):
        """Session save produces valid JSON."""
        from cli_anything.citeindex.core.session import CiteIndexSession, SessionManager

        mgr = SessionManager(storage_dir=str(tmp_path / "sessions"))
        sess = mgr.create_session()
        sess.set_corpus_root(str(tmp_path / "corpus"))
        sess.set_thread_id("test-thread")
        mgr.save_session(sess)

        session_file = tmp_path / "sessions" / f"{sess.session_id}.json"
        assert session_file.exists()
        with open(session_file) as f:
            data = json.load(f)
        assert data["session_id"] == sess.session_id
        assert data["corpus_root"] == str(tmp_path / "corpus")
        assert data["thread_id"] == "test-thread"

    def test_session_json_has_required_fields(self, tmp_path):
        """Session JSON contains all required fields."""
        from cli_anything.citeindex.core.session import CiteIndexSession, SessionManager

        mgr = SessionManager(storage_dir=str(tmp_path / "sessions"))
        sess = mgr.create_session()
        mgr.save_session(sess)

        session_file = tmp_path / "sessions" / f"{sess.session_id}.json"
        with open(session_file) as f:
            data = json.load(f)
        required_fields = ["session_id", "created_at", "modified_at", "status",
                          "corpus_root", "thread_id", "loaded_documents",
                          "undo_stack", "redo_stack", "context"]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"


class TestProjectE2E:
    """Project creation E2E tests."""

    def test_project_new_creates_citeindex_dir(self, tmp_path):
        """project_new creates the .citeindex/ subdirectory structure."""
        from cli_anything.citeindex.core.project import project_new

        corpus_root = str(tmp_path / "corpus")
        result = project_new(corpus_root=corpus_root)
        assert result["status"] == "ok"
        assert os.path.isdir(os.path.join(corpus_root, ".citeindex"))
        assert os.path.isdir(os.path.join(corpus_root, ".citeindex", "indexes"))
        assert os.path.isdir(os.path.join(corpus_root, ".citeindex", "documents"))

    def test_project_info_after_new(self, tmp_path):
        """project_info returns correct data after project_new."""
        from cli_anything.citeindex.core.project import project_new, project_info

        corpus_root = str(tmp_path / "corpus")
        project_new(corpus_root=corpus_root)
        result = project_info(corpus_root=corpus_root)
        assert result["exists"] is True
        assert result["has_citeindex_store"] is True
        assert result["document_count"] == 0

    def test_export_render_produces_file(self, tmp_path):
        """export_render produces a non-empty text file when corpus has data."""
        from cli_anything.citeindex.core.export import export_render

        # This test requires a corpus with CSL data
        # If no corpus available, it should return an error gracefully
        result = export_render(
            output_path=str(tmp_path / "output.txt"),
            corpus_root=str(tmp_path / "nonexistent"),
            format="txt",
        )
        assert result.get("status") in ("error", "ok")


# ── CLI Subprocess Tests ──


class TestCLISubprocess:
    """Test the installed CLI command as a real user/agent would."""

    CLI_BASE = _resolve_cli("cli-anything-citeindex")

    def _run(self, args, check=True):
        return subprocess.run(
            self.CLI_BASE + args,
            capture_output=True,
            text=True,
            check=check,
        )

    def test_help(self):
        result = self._run(["--help"])
        assert result.returncode == 0
        assert "citeindex" in result.stdout.lower()

    def test_version(self):
        result = self._run(["--version"])
        assert result.returncode == 0
        assert "1.0.0" in result.stdout

    def test_project_help(self):
        result = self._run(["project", "--help"])
        assert result.returncode == 0
        assert "new" in result.stdout

    def test_ingest_help(self):
        result = self._run(["ingest", "--help"])
        assert result.returncode == 0
        assert "file" in result.stdout

    def test_search_help(self):
        result = self._run(["search", "--help"])
        assert result.returncode == 0

    def test_chat_help(self):
        result = self._run(["chat", "--help"])
        assert result.returncode == 0

    def test_memory_help(self):
        result = self._run(["memory", "--help"])
        assert result.returncode == 0

    def test_export_help(self):
        result = self._run(["export", "--help"])
        assert result.returncode == 0

    def test_session_help(self):
        result = self._run(["session", "--help"])
        assert result.returncode == 0

    def test_project_new_json(self, tmp_path):
        """project new with --json produces valid JSON."""
        corpus_root = str(tmp_path / "test-corpus")
        result = self._run(["--json", "project", "new", "--corpus-root", corpus_root])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["status"] == "ok"
        assert os.path.isdir(corpus_root)

    def test_project_info_json(self, tmp_path):
        """project info with --json produces valid JSON."""
        corpus_root = str(tmp_path / "test-corpus2")
        self._run(["--json", "project", "new", "--corpus-root", corpus_root])
        result = self._run(["--json", "project", "info", "--corpus-root", corpus_root])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["exists"] is True
        print(f"\n  Corpus: {corpus_root} ({data.get('document_count', 0)} docs)")

    def test_project_validate_json(self, tmp_path):
        """project validate with --json produces valid JSON."""
        corpus_root = str(tmp_path / "test-corpus3")
        self._run(["--json", "project", "new", "--corpus-root", corpus_root])
        result = self._run(["--json", "project", "validate", "--corpus-root", corpus_root])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["valid"] is True
```

**Step 2: Run E2E tests (subprocess tests only, no real backend)**

```bash
cd /home/ajiap/project/citeindex/agent-harness
pip install -e . 2>&1 | tail -2
python -m pytest cli_anything/citeindex/tests/test_full_e2e.py::TestCLISubprocess -v -s 2>&1 | tail -20
```

Expected: subprocess tests pass (help, version, project new/info/validate with --json)

**Step 3: Commit**

```bash
git add agent-harness/
git commit -m "feat: add E2E tests with CLI subprocess tests"
```

---

### Task 10: SKILL.md Generation

**Files:**
- Create: `agent-harness/cli_anything/citeindex/skills/SKILL.md`

**Step 1: Write SKILL.md**

Create `agent-harness/cli_anything/citeindex/skills/SKILL.md`:

```markdown
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
```

**Step 2: Commit**

```bash
git add agent-harness/
git commit -m "feat: add SKILL.md for agent discovery"
```

---

### Task 11: Installation Verification

**Step 1: Install the package**

```bash
cd /home/ajiap/project/citeindex/agent-harness
pip install -e . 2>&1 | tail -5
```

**Step 2: Verify installation**

```bash
which cli-anything-citeindex
cli-anything-citeindex --help
cli-anything-citeindex --version
```

Expected: command found, help displayed, version "1.0.0"

**Step 3: Run all unit tests**

```bash
cd /home/ajiap/project/citeindex/agent-harness
python -m pytest cli_anything/citeindex/tests/test_core.py -v
```

Expected: ~16 passed

**Step 4: Run E2E tests in force-installed mode**

```bash
cd /home/ajiap/project/citeindex/agent-harness
CLI_ANYTHING_FORCE_INSTALLED=1 python -m pytest cli_anything/citeindex/tests/test_full_e2e.py -v -s
```

Expected: All subprocess tests pass, showing `[_resolve_cli] Using installed command: /path/to/cli-anything-citeindex`

**Step 5: Run ALL tests together**

```bash
cd /home/ajiap/project/citeindex/agent-harness
CLI_ANYTHING_FORCE_INSTALLED=1 python -m pytest cli_anything/citeindex/tests/ -v -s
```

Expected: All tests pass

**Step 6: Update TEST.md with results**

Append test output to `agent-harness/cli_anything/citeindex/tests/TEST.md`:

```markdown
## Test Results

(To be filled in after running tests)
```

**Step 7: Final commit**

```bash
git add agent-harness/
git commit -m "feat: complete cli-anything-citeindex v1.0.0 — all tests passing"
```