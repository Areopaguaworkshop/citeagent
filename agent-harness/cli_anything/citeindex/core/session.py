"""Session management — stateful workflow tracking with undo/redo for CiteIndex CLI."""
from __future__ import annotations

import fcntl
import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _locked_save_json(path: str, data: Any, **dump_kwargs: Any) -> None:
    """Atomically write JSON with exclusive file locking."""
    dump_kwargs.setdefault("indent", 2)
    dump_kwargs.setdefault("ensure_ascii", False)
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with open(f"{path}.lock", "a", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        except (ImportError, OSError):
            pass  # Windows / unsupported FS — proceed unlocked
        fd, temp_path = tempfile.mkstemp(dir=directory, prefix=".session-", text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, **dump_kwargs)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


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

    def _session_path(self, session_id: str) -> Path:
        if not session_id or session_id == "active":
            raise ValueError("Session ID is invalid")
        base = self.storage_dir.resolve()
        path = (base / f"{session_id}.json").resolve()
        if path.parent != base:
            raise ValueError("Session ID must not contain a path")
        return path

    def _set_active(self, session_id: str) -> None:
        self._ensure_dir()
        self._session_path(session_id)
        _locked_save_json(str(self.storage_dir / "active.json"), {"session_id": session_id})

    def activate(self, session_id: str) -> None:
        self._set_active(session_id)

    def load_active(self) -> Optional[CiteIndexSession]:
        path = self.storage_dir / "active.json"
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return self.load_session(json.load(f)["session_id"])
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    def create_session(self, session_id: Optional[str] = None) -> CiteIndexSession:
        if session_id is None:
            session_id = f"citeindex-{_utc_now().strftime('%Y%m%d%H%M%S%f')}"
        session = CiteIndexSession(session_id=session_id)
        self.save_session(session)
        self._set_active(session.session_id)
        return session

    def save_session(self, session: CiteIndexSession) -> None:
        self._ensure_dir()
        path = str(self._session_path(session.session_id))
        _locked_save_json(path, session.to_dict())

    def load_session(self, session_id: str) -> Optional[CiteIndexSession]:
        path = self._session_path(session_id)
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return CiteIndexSession.from_dict(data)

    def delete_session(self, session_id: str) -> bool:
        path = self._session_path(session_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_sessions(self, include_inactive: bool = True) -> List[CiteIndexSession]:
        self._ensure_dir()
        sessions: List[CiteIndexSession] = []
        for path in self.storage_dir.glob("*.json"):
            if path.name == "active.json":
                continue
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
