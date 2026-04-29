"""Export commands — render, bibliography."""
from __future__ import annotations

import json as _json
import os
from typing import Any, Dict, List

from ..utils.citeindex_backend import CiteIndexBackend


_backend = CiteIndexBackend()


def _collect_csl_data(corpus_root: str) -> List[Dict[str, Any]]:
    """Collect CSL-JSON data from all documents in a corpus."""
    info = _backend.corpus_info(corpus_root)
    if not info.get("exists") or info["document_count"] == 0:
        return []

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

    return csl_data


def export_render(
    output_path: str,
    corpus_root: str = "corpus",
    format: str = "txt",
    cite_style: str = "chicago-author-date",
    overwrite: bool = False,
) -> Dict[str, Any]:
    """Render citations from the corpus to a file."""
    if os.path.exists(output_path) and not overwrite:
        return {
            "status": "error",
            "message": f"File already exists: {output_path}. Use --overwrite to replace.",
        }

    csl_data = _collect_csl_data(corpus_root)
    if not csl_data:
        return {
            "status": "error",
            "message": "No CSL citation data found in corpus.",
        }

    result = _backend.format_bibliography(csl_data, style_name=cite_style)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
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
    """Export a formatted bibliography from the corpus."""
    csl_data = _collect_csl_data(corpus_root)
    if not csl_data:
        return {
            "status": "error",
            "message": "No CSL citation data found.",
        }

    return _backend.format_bibliography(csl_data, style_name=cite_style)