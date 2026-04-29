import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..deterministic import build_merkle_tree, build_hierarchical_merkle_tree, canonicalize_text, hash_payload
from ..models import IngestionConfig

logger = logging.getLogger(__name__)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_") or "source"


def make_source_id(input_ref: str) -> str:
    base = os.path.basename(input_ref) or input_ref
    base = os.path.splitext(base)[0]
    return slugify(base)


def split_paragraphs(text: str) -> List[str]:
    chunks = [canonicalize_text(p) for p in re.split(r"\n\s*\n", text)]
    return [p for p in chunks if p]


def build_nodes(source_id: str, page_paragraphs: List[Tuple[int, List[str]]]) -> List[Dict[str, Any]]:
    nodes: List[Dict[str, Any]] = []
    for page_number, paragraphs in page_paragraphs:
        for idx, paragraph in enumerate(paragraphs, start=1):
            text = canonicalize_text(paragraph)
            if not text:
                continue
            text_hash = hash_payload(text)
            section_slug = f"p{page_number}"
            unit_slug = f"para{idx}"
            node_id = f"{source_id}:{section_slug}:{unit_slug}:{text_hash[:8]}"
            nodes.append(
                {
                    "node_id": node_id,
                    "source_id": source_id,
                    "section_path": section_slug,
                    "text": text,
                    "sha256": text_hash,
                    "page": page_number,
                    "paragraph": idx,
                }
            )
    nodes.sort(key=lambda n: n["node_id"])
    return nodes


def build_nodes_with_granularity(
    source_id: str,
    page_paragraphs: List[Tuple[int, List[str]]],
    is_primary: bool = False,
) -> List[Dict[str, Any]]:
    """Build nodes with granularity based on source classification.

    Primary sources: line-level nodes (each line is a node)
    Secondary sources (default): paragraph-level nodes
    """
    if not is_primary:
        return build_nodes(source_id, page_paragraphs)

    nodes: List[Dict[str, Any]] = []
    for page_number, paragraphs in page_paragraphs:
        for pidx, paragraph in enumerate(paragraphs, start=1):
            text = canonicalize_text(paragraph)
            if not text:
                continue
            lines = [line for line in text.split("\n") if line.strip()]
            if not lines:
                continue
            section_slug = f"p{page_number}"
            for lidx, line in enumerate(lines, start=1):
                line_text = canonicalize_text(line)
                if not line_text:
                    continue
                line_hash = hash_payload(line_text)
                unit_slug = f"para{pidx}_line{lidx}"
                node_id = f"{source_id}:{section_slug}:{unit_slug}:{line_hash[:8]}"
                nodes.append(
                    {
                        "node_id": node_id,
                        "source_id": source_id,
                        "section_path": section_slug,
                        "text": line_text,
                        "sha256": line_hash,
                        "page": page_number,
                        "paragraph": pidx,
                        "line": lidx,
                    }
                )
    nodes.sort(key=lambda n: n["node_id"])
    return nodes


def build_document_structure(page_paragraphs: List[Tuple[int, List[str]]]) -> Dict[str, Any]:
    return {
        "pages": [
            {
                "page_number": page_number,
                "paragraphs": [
                    {
                        "paragraph_id": f"p{page_number}_{i+1}",
                        "text": p,
                        "lines": [line for line in p.split("\n") if line.strip()],
                    }
                    for i, p in enumerate(paragraphs)
                ],
            }
            for page_number, paragraphs in page_paragraphs
        ]
    }


def build_layout_document_structure(page_layouts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build document structure from layout analysis results (pages → columns → paragraphs)."""
    return {
        "pages": [
            {
                "page_number": pl["page_number"],
                "columns": pl.get("columns", []),
                "footnotes": pl.get("footnotes", []),
            }
            for pl in page_layouts
        ]
    }


def build_retrieval_index(nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "entries": [
            {
                "hash": n["sha256"],
                "page": n.get("page"),
                "paragraph": n.get("paragraph"),
                "text_reference": n["node_id"],
            }
            for n in nodes
        ]
    }


def build_merkle_for_nodes(nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    leaf_hashes = [n["sha256"] for n in nodes]
    return build_merkle_tree(leaf_hashes)


def make_basic_csl(source_id: str, title: str, csl_type: str, extra: Dict[str, Any] | None = None) -> Dict[str, Any]:
    csl: Dict[str, Any] = {
        "id": source_id,
        "type": csl_type,
        "title": title,
    }
    if extra:
        csl.update(extra)
    return csl


# ---------------------------------------------------------------------------
# Phase 1: LLM-based citation extraction (merged from legacy CitationExtractor)
# ---------------------------------------------------------------------------

def determine_doc_type(pdf_path: str, num_pages: int) -> str:
    """Determine document type using legacy type_judge rules."""
    try:
        from ...type_judge import determine_document_type
        return determine_document_type(pdf_path, num_pages)
    except Exception:
        logger.warning("type_judge unavailable, falling back to page-count heuristic")
        return "book" if num_pages >= 70 else "journal"


def extract_citation_with_llm(
    text: str,
    doc_type: str,
    config: Optional[IngestionConfig] = None,
) -> Dict[str, Any]:
    """Run LLM-based citation extraction and return rich CSL JSON.

    Merges the legacy CitationLLM path into the ingestion pipeline so that
    ``citeindex ingest`` produces both structural artifacts AND rich citation
    metadata in a single pass.

    Gracefully returns ``{}`` when dspy / LLM dependencies are unavailable so
    that the structural pipeline always completes.
    """
    cfg = config or IngestionConfig()

    try:
        from ...model import CitationLLM
        from ...utils import to_csl_json
    except Exception:
        logger.warning("LLM dependencies (dspy) not available; skipping citation extraction")
        return {}

    llm = CitationLLM(cfg.llm_model)

    # Truncate for LLM context window
    truncated = text[:8000] if len(text) > 8000 else text

    use_vertical = cfg.text_direction in ("vertical", "auto") and doc_type == "book"
    if use_vertical:
        try:
            from ...vertical_llm import VerticalCitationLLM
            vertical_llm = VerticalCitationLLM(cfg.llm_model)
            extracted = vertical_llm.extract_vertical_citation(truncated, doc_type)
        except Exception:
            logger.warning("Vertical LLM failed, falling back to standard LLM", exc_info=True)
            extracted = llm.extract_citation_from_text(truncated, doc_type)
    else:
        extracted = llm.extract_citation_from_text(truncated, doc_type)

    if not extracted:
        logger.warning("LLM citation extraction returned empty result")
        return {}

    csl = to_csl_json(extracted, doc_type)
    return csl


def _extract_citation_grobid(pdf_path: str) -> Dict[str, Any]:
    """Try grobid header extraction. Returns CSL dict or {}."""
    try:
        from .grobid import extract_document_metadata_grobid, is_grobid_available

        if not is_grobid_available():
            logger.info("GROBID not available, skipping")
            return {}

        csl = extract_document_metadata_grobid(pdf_path)
        if csl.get("title"):
            logger.info("GROBID metadata extraction succeeded")
            return csl
        logger.info("GROBID returned no title, treating as empty")
        return {}
    except Exception:
        logger.warning("GROBID extraction failed", exc_info=True)
        return {}


def enrich_csl_with_citation_cascade(
    base_csl: Dict[str, Any],
    ordered_text: str,
    pdf_path: Optional[str],
    num_pages: int,
    config: Optional[IngestionConfig] = None,
) -> Dict[str, Any]:
    """Enrich a basic CSL JSON dict using the citation extraction cascade.

    Cascade order (per migration plan Phase 1.3):
      1. GROBID (deterministic, primary)
      2. LLM extraction (probabilistic, fallback)
      3. PDF metadata only (last resort — base_csl as-is)

    Merges extracted fields into base_csl, preferring extracted values.
    """
    cfg = config or IngestionConfig()

    # Determine document type
    if cfg.doc_type_override:
        doc_type = cfg.doc_type_override
    elif pdf_path:
        doc_type = determine_doc_type(pdf_path, num_pages)
    else:
        doc_type = "book" if num_pages >= 70 else "journal"

    logger.info("Document type determined: %s (pages=%d)", doc_type, num_pages)

    # --- Cascade ---
    extracted_csl: Dict[str, Any] = {}
    extraction_method = "metadata-only"

    # 1. Try GROBID
    if pdf_path:
        extracted_csl = _extract_citation_grobid(pdf_path)
        if extracted_csl:
            extraction_method = "grobid"

    # 2. Fallback to LLM
    if not extracted_csl:
        extracted_csl = extract_citation_with_llm(ordered_text, doc_type, cfg)
        if extracted_csl:
            extraction_method = "llm"

    # 3. Last resort: base_csl as-is
    if not extracted_csl:
        logger.info("Citation cascade: using metadata-only (no enrichment)")
        return base_csl

    logger.info("Citation cascade: using %s extraction", extraction_method)

    # Merge: extracted values win for metadata fields; keep structural fields from base
    merged = dict(base_csl)
    for key, value in extracted_csl.items():
        if key in ("id",):
            continue  # keep deterministic id from base
        if value is not None:
            merged[key] = value
    merged["_extraction_method"] = extraction_method

    return merged


# Backward-compatible alias
enrich_csl_with_llm = enrich_csl_with_citation_cascade
