"""Corpus/project management — new, open, info, validate, list."""
from __future__ import annotations

import os
from typing import Any, Dict, List

from ..utils.citeindex_backend import CiteIndexBackend


_backend = CiteIndexBackend()


def project_new(corpus_root: str = "corpus") -> Dict[str, Any]:
    """Create a new corpus directory structure."""
    os.makedirs(corpus_root, exist_ok=True)
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
    """Get information about a corpus."""
    return _backend.corpus_info(corpus_root)


def project_validate(corpus_root: str = "corpus") -> Dict[str, Any]:
    """Validate a corpus structure."""
    return _backend.corpus_validate(corpus_root)


def project_list(corpus_root: str = "corpus") -> Dict[str, Any]:
    """List documents in a corpus."""
    info = _backend.corpus_info(corpus_root)
    docs = info.get("v12_documents", []) + info.get("legacy_documents", [])
    return {
        "status": "ok",
        "documents": docs,
        "document_count": len(docs),
    }