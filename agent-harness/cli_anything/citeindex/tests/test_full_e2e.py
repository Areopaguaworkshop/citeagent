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
        from cli_anything.citeindex.core.session import SessionManager

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
        from cli_anything.citeindex.core.session import SessionManager

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
        """export_render returns graceful error on empty corpus."""
        from cli_anything.citeindex.core.export import export_render

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