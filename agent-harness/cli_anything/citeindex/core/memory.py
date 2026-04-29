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
    """Search past chat memory."""
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
    """List all memory threads."""
    threads = _backend.memory_list_threads(corpus_root=corpus_root)
    return {
        "status": "ok",
        "threads": threads,
    }