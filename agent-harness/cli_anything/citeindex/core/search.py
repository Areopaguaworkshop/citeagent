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
    """Search the corpus using BM25 or PageIndex retrieval."""
    return _backend.search(
        query=query,
        corpus_root=corpus_root,
        top_k=top_k,
        cite_style=cite_style,
        retrieval=retrieval,
        pageindex_model=pageindex_model,
        schema_version=schema_version,
    )