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