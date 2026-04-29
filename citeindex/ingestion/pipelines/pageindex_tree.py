"""PageIndex tree-building pipeline and schema converter.

Uses VectifyAI/PageIndex (vendored) to build an LLM-driven hierarchical
section tree from a PDF or Markdown document, then converts the result to
CiteIndex's PageIndexTree JSON format.

Data flow (PDF):
  PDF ─→ PageIndex page_index_main() ─→ PageIndex tree
  MinerU middle.json ─→ page_extractor.py ─→ page_number_map
  GROBID ─→ csl.json ─→ level_0
                         ↓
         pageindex_to_citeindex_tree()
                         ↓
         {doc_id}.citeindex.json

Data flow (URL/Markdown):
  HTML ─→ trafilatura ─→ markdown text
                         ↓
  PageIndex md_to_tree() ─→ PageIndex tree
                         ↓
         pageindex_to_citeindex_tree()
"""

import json
import logging
import os
import tempfile
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default model for PageIndex operations (local Ollama)
PAGEINDEX_MODEL = "ollama/qwen3.5:cloud"


def run_pageindex_tree(
    pdf_path: str,
    model: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Run PageIndex tree-building on a PDF.

    Returns the raw PageIndex result dict with ``doc_name`` and ``structure``,
    or *None* on failure.
    """
    try:
        from .pageindex import page_index_main
        from .pageindex.utils import ConfigLoader

        opt = ConfigLoader().load({
            "model": model or PAGEINDEX_MODEL,
            "if_add_node_id": "yes",
            "if_add_node_summary": "yes",
            "if_add_node_text": "no",
            "if_add_doc_description": "no",
        })

        logger.info("Running PageIndex tree-building on %s (model=%s)", pdf_path, opt.model)
        result = page_index_main(pdf_path, opt)

        structure = result.get("structure", [])
        if not structure:
            logger.warning("PageIndex returned empty structure for %s", pdf_path)
            return None

        logger.info(
            "PageIndex built tree for %s: %d top-level sections",
            pdf_path,
            len(structure),
        )
        return result

    except Exception:
        logger.warning("PageIndex tree-building failed for %s", pdf_path, exc_info=True)
        return None


def run_pageindex_md_tree(
    markdown_text: str,
    model: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Run PageIndex tree-building on markdown text (e.g. from URL articles).

    Writes markdown to a temp file, runs ``md_to_tree()``, returns the raw
    PageIndex result dict or *None* on failure.
    """
    import asyncio

    fd = None
    tmp_path = None
    try:
        from .pageindex.page_index_md import md_to_tree

        use_model = model or PAGEINDEX_MODEL

        # Write markdown to temp file (PageIndex expects a file path)
        fd, tmp_path = tempfile.mkstemp(prefix="citeindex_pi_", suffix=".md")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(markdown_text)
        fd = None  # os.fdopen closes the fd

        logger.info("Running PageIndex md_to_tree (model=%s, %d chars)", use_model, len(markdown_text))
        result = asyncio.run(md_to_tree(
            md_path=tmp_path,
            if_thinning=False,
            if_add_node_summary="yes",
            summary_token_threshold=200,
            model=use_model,
            if_add_doc_description="no",
            if_add_node_text="no",
            if_add_node_id="yes",
        ))

        structure = result.get("structure", [])
        if not structure:
            logger.warning("PageIndex md_to_tree returned empty structure")
            return None

        logger.info("PageIndex md_to_tree built: %d top-level sections", len(structure))
        return result

    except Exception:
        logger.warning("PageIndex md_to_tree failed", exc_info=True)
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


# ---------------------------------------------------------------------------
# Schema converter: PageIndex tree → CiteIndex PageIndexTree JSON
# ---------------------------------------------------------------------------


def pageindex_to_citeindex_tree(
    pi_result: Dict[str, Any],
    doc_id: str,
    csl_data: Dict[str, Any],
    page_number_map: Dict[int, int],
    merkle_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Convert a PageIndex result to CiteIndex PageIndexTree JSON.

    Parameters
    ----------
    pi_result : dict
        Raw output from ``page_index()`` with ``structure`` list.
    doc_id : str
        CiteIndex source_id / document identifier.
    csl_data : dict
        Enriched CSL-JSON metadata for level_0.
    page_number_map : dict
        Mapping ``{physical_page_idx (0-based) → actual_page_number}``.
        PageIndex uses 1-based physical indices; the map is 0-based.
    merkle_root : str, optional
        Document Merkle root hash.

    Returns
    -------
    dict
        CiteIndex PageIndexTree JSON matching ``kernel/types/tree.rs``.
    """
    structure = pi_result.get("structure", [])
    level_1 = _convert_sections(structure, doc_id, page_number_map)
    level_0 = _build_level0(csl_data, doc_id, merkle_root)

    return {
        "citeindex_version": "12.0",
        "tree_version": "1.0",
        "level_0": level_0,
        "level_1": level_1,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _map_page(physical_index: Optional[int], page_number_map: Dict[int, int]) -> Optional[int]:
    """Map a 1-based physical PDF page index to the actual page number.

    PageIndex ``start_index`` / ``end_index`` are 1-based.
    ``page_number_map`` keys are 0-based (MinerU convention).
    """
    if physical_index is None:
        return None
    zero_based = physical_index - 1
    return page_number_map.get(zero_based, physical_index)


def _page_range_str(
    start_idx: Optional[int],
    end_idx: Optional[int],
    page_number_map: Dict[int, int],
) -> Optional[str]:
    start = _map_page(start_idx, page_number_map)
    end = _map_page(end_idx, page_number_map)
    if start is None and end is None:
        return None
    if start == end:
        return str(start)
    return f"{start}-{end}"


def _convert_sections(
    nodes: List[Dict[str, Any]],
    doc_id: str,
    page_number_map: Dict[int, int],
) -> List[Dict[str, Any]]:
    """Convert top-level PageIndex nodes → CiteIndex level_1 SectionNodes."""
    sections: List[Dict[str, Any]] = []
    for node in nodes:
        pi_id = node.get("node_id", "")
        section = {
            "node_id": f"{doc_id}:section:{pi_id}",
            "heading": node.get("title"),
            "section_number": None,
            "section_type": "section",
            "page_range": _page_range_str(
                node.get("start_index"), node.get("end_index"), page_number_map
            ),
            "children": _convert_subsections(
                node.get("nodes", []), doc_id, pi_id, page_number_map
            ),
        }
        if node.get("summary"):
            section["ci_summary"] = node["summary"]
        sections.append(section)
    return sections


def _convert_subsections(
    nodes: List[Dict[str, Any]],
    doc_id: str,
    parent_id: str,
    page_number_map: Dict[int, int],
) -> List[Dict[str, Any]]:
    """Convert child PageIndex nodes → CiteIndex SubsectionNodes.

    Leaf nodes (no children) become a SubsectionNode wrapping a single
    LocatorNode so the tree always has the 3-level depth that the Rust
    ``PageIndexTree`` type expects.
    """
    subsections: List[Dict[str, Any]] = []
    for node in nodes:
        pi_id = node.get("node_id", "")
        children_nodes = node.get("nodes", [])

        if children_nodes:
            # Non-leaf: recurse into deeper children as locators
            subsection = {
                "node_id": f"{doc_id}:subsection:{pi_id}",
                "heading": node.get("title"),
                "section_number": None,
                "children": _convert_to_locators(
                    children_nodes, doc_id, pi_id, page_number_map
                ),
            }
        else:
            # Leaf: wrap as subsection with a single locator
            subsection = {
                "node_id": f"{doc_id}:subsection:{pi_id}",
                "heading": node.get("title"),
                "section_number": None,
                "children": [
                    _make_locator(node, doc_id, pi_id, page_number_map)
                ],
            }

        if node.get("summary"):
            subsection["ci_summary"] = node["summary"]
        subsections.append(subsection)

    # If no children at all, create a single catch-all subsection
    if not subsections:
        subsections.append({
            "node_id": f"{doc_id}:subsection:{parent_id}:default",
            "heading": None,
            "section_number": None,
            "children": [],
        })

    return subsections


def _convert_to_locators(
    nodes: List[Dict[str, Any]],
    doc_id: str,
    parent_id: str,
    page_number_map: Dict[int, int],
) -> List[Dict[str, Any]]:
    """Convert deepest PageIndex nodes → CiteIndex LocatorNodes."""
    locators: List[Dict[str, Any]] = []
    for node in nodes:
        locators.append(_make_locator(node, doc_id, parent_id, page_number_map))
    return locators


def _make_locator(
    node: Dict[str, Any],
    doc_id: str,
    parent_id: str,
    page_number_map: Dict[int, int],
) -> Dict[str, Any]:
    """Build a single CiteIndex LocatorNode from a PageIndex leaf node."""
    pi_id = node.get("node_id", "")
    start_page = _map_page(node.get("start_index"), page_number_map)
    end_page = _map_page(node.get("end_index"), page_number_map)

    return {
        "node_id": f"{doc_id}:locator:{pi_id}",
        "locator_type": "page_range",
        "page_number": start_page,
        "page_label": _page_range_str(
            node.get("start_index"), node.get("end_index"), page_number_map
        ),
        "text_blocks": [],
        "figures": [],
        "tables": [],
        "paragraph_number": None,
        "paragraph_id": f"{doc_id}:{pi_id}",
        "text": node.get("text"),
        "start_time": None,
        "end_time": None,
        "speaker": None,
        "transcript_text": None,
        "children": [],
    }


def _build_level0(
    csl_data: Dict[str, Any],
    doc_id: str,
    merkle_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Build CiteIndex level_0 (citation root) from CSL-JSON metadata."""
    return {
        "id": csl_data.get("id", doc_id),
        "type": csl_data.get("type", "article-journal"),
        "title": csl_data.get("title", doc_id),
        "author": csl_data.get("author", []),
        "editor": csl_data.get("editor", []),
        "issued": csl_data.get("issued"),
        "DOI": csl_data.get("DOI") or csl_data.get("doi"),
        "ISBN": csl_data.get("ISBN"),
        "URL": csl_data.get("URL"),
        "container-title": csl_data.get("container-title") or csl_data.get("container_title"),
        "volume": csl_data.get("volume"),
        "issue": csl_data.get("issue"),
        "page": csl_data.get("page"),
        "publisher": csl_data.get("publisher"),
        "publisher-place": csl_data.get("publisher-place"),
        "abstract": csl_data.get("abstract"),
        "language": csl_data.get("language"),
        "keyword": csl_data.get("keyword"),
        "ci_doc_id": doc_id,
        "ci_quality_tier": csl_data.get("ci_quality_tier", "silver"),
        "ci_hierarchy_path": csl_data.get("ci_hierarchy_path"),
        "ci_merkle_hash": merkle_root,
        "ci_source_type": csl_data.get("source_type"),
        "ci_ingested_at": csl_data.get("ingestion_timestamp"),
        "ci_structure_confidence": None,
        "ci_indexed_at": None,
        "ci_project_ids": [],
        "ci_claim_anchors": [],
    }
