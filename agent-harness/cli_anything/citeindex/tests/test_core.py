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
        from cli_anything.citeindex.core.session import CiteIndexSession
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
        from cli_anything.citeindex.core.session import SessionManager
        mgr = SessionManager(storage_dir=tempfile.mkdtemp())
        mgr.create_session()
        mgr.create_session()
        sessions = mgr.list_sessions()
        assert len(sessions) == 2

    def test_session_delete(self):
        from cli_anything.citeindex.core.session import SessionManager
        mgr = SessionManager(storage_dir=tempfile.mkdtemp())
        sess = mgr.create_session()
        assert mgr.delete_session(sess.session_id) is True
        assert mgr.load_session(sess.session_id) is None


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
        """Verify _build_ingest_config constructs correct dict."""
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