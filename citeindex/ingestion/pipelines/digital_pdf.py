"""Digital PDF ingestion pipeline.

Workflow (v0.2):
  1. GROBID  — deterministic metadata + references from raw PDF
  2. MinerU  — layout analysis (content_list + markdown + middle JSON)
  3. Pattern extraction from content_list, DSPy fallback, reconcile with GROBID
  4. Build section-hierarchical document structure with actual page numbers
  5. Merkle tree (no retrieval index)

Falls back to legacy fitz-based layout when MinerU is unavailable.
"""

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import fitz

from ..models import IngestionConfig, PipelineResult
from ..deterministic import build_hierarchical_merkle_tree
from .common import (
    build_document_structure,
    build_merkle_for_nodes,
    build_nodes_with_granularity,
    determine_doc_type,
    make_basic_csl,
    make_source_id,
    split_paragraphs,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Legacy fitz-based extraction (kept as fallback)
# ---------------------------------------------------------------------------

def _extract_page_paragraphs(pdf_path: str) -> List[Tuple[int, List[str]]]:
    doc = fitz.open(pdf_path)
    page_paragraphs: List[Tuple[int, List[str]]] = []
    for page_idx in range(doc.page_count):
        text = page_paragraphs_from_page(doc[page_idx])
        page_paragraphs.append((page_idx + 1, text))
    doc.close()
    return page_paragraphs


def page_paragraphs_from_page(page: fitz.Page) -> List[str]:
    text = page.get_text("text")
    paragraphs = split_paragraphs(text)
    if paragraphs:
        return paragraphs

    blocks = page.get_text("blocks")
    fallback: List[str] = []
    for block in sorted(blocks, key=lambda b: (b[1], b[0])):
        content = (block[4] or "").strip()
        if content:
            fallback.extend(split_paragraphs(content))
    return fallback


# ---------------------------------------------------------------------------
# Step 1: GROBID extraction
# ---------------------------------------------------------------------------

def _run_grobid(pdf_path: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Run GROBID on raw PDF. Returns (metadata_csl, references_dict)."""
    try:
        from .grobid import (
            extract_citations_grobid,
            extract_document_metadata_grobid,
            is_grobid_available,
        )

        if not is_grobid_available():
            logger.info("GROBID not available, skipping initial extraction")
            return {}, {}

        logger.info("Step 1: Running GROBID on raw PDF")
        metadata = extract_document_metadata_grobid(pdf_path)
        references = extract_citations_grobid(pdf_path)

        logger.info(
            "GROBID: metadata=%d fields, references=%d",
            len(metadata),
            len(references.get("references", [])),
        )
        return metadata, references

    except Exception:
        logger.warning("GROBID extraction failed", exc_info=True)
        return {}, {}


# ---------------------------------------------------------------------------
# Step 2: MinerU layout analysis
# ---------------------------------------------------------------------------

def _run_mineru(pdf_path: str) -> Optional[Dict[str, Any]]:
    """Run MinerU layout analysis. Returns output dict or None on failure."""
    try:
        from .mineru import is_mineru_available, run_mineru

        if not is_mineru_available():
            logger.info("MinerU not available, will fall back to fitz layout")
            return None

        logger.info("Step 2: Running MinerU layout analysis")
        result = run_mineru(pdf_path)
        logger.info("MinerU: output_dir=%s", result.get("output_dir", "?"))
        return result

    except Exception:
        logger.warning("MinerU failed, falling back to fitz layout", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Step 3: Pattern + DSPy extraction from MinerU content_list
# ---------------------------------------------------------------------------

def _run_extraction(
    content_list: List[Dict[str, Any]],
    mineru_markdown: str,
    grobid_metadata: Dict[str, Any],
    doc_type: str,
    config: IngestionConfig,
) -> Dict[str, Any]:
    """Pattern extraction from content_list, DSPy fallback, reconcile with GROBID."""
    from .dspy_extract import (
        extract_metadata_with_dspy_fallback,
        extract_page_numbers_from_content_list,
        reconcile_grobid_and_dspy,
    )

    # Separate discarded blocks for header/footer analysis
    discarded = [it for it in content_list if it.get("type") == "discarded"]

    logger.info("Step 3: Pattern extraction from content_list (%d items, %d discarded)",
                len(content_list), len(discarded))

    pattern_dspy_csl = extract_metadata_with_dspy_fallback(
        content_list=content_list,
        mineru_markdown=mineru_markdown,
        doc_type=doc_type,
        config=config,
        discarded_blocks=discarded,
    )

    # Reconcile with GROBID
    enriched = reconcile_grobid_and_dspy(grobid_metadata, pattern_dspy_csl, doc_type, config)
    logger.info("Reconciled CSL: method=%s, fields=%d",
                enriched.get("_extraction_method", "?"), len(enriched))
    return enriched


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(
    pdf_path: str,
    source_type: str = "digital_pdf",
    config: Optional[IngestionConfig] = None,
) -> PipelineResult:
    cfg = config or IngestionConfig()
    source_id = make_source_id(pdf_path)

    doc = fitz.open(pdf_path)
    title = doc.metadata.get("title") or os.path.basename(pdf_path)
    num_pages = doc.page_count
    doc.close()

    # Determine document type early
    if cfg.doc_type_override:
        doc_type = cfg.doc_type_override
    else:
        doc_type = determine_doc_type(pdf_path, num_pages)

    pageindex_tree_json = None  # populated if cfg.use_pageindex and MinerU path

    # ── Step 1: GROBID ─────────────────────────────────────────────
    grobid_metadata, grobid_references = _run_grobid(pdf_path)

    # ── Step 2: MinerU layout analysis ─────────────────────────────
    mineru_output = _run_mineru(pdf_path) if cfg.use_layout_analysis else None

    if mineru_output and mineru_output.get("content_list"):
        # === MinerU path (new) ===
        logger.info("Using MinerU content_list pipeline")
        from .dspy_extract import extract_page_numbers_from_content_list
        from .mineru import content_list_to_document_structure, content_list_to_paragraphs

        content_list = mineru_output["content_list"]
        mineru_markdown = mineru_output.get("markdown", "")

        # Build actual page number map from discarded blocks
        page_number_map = extract_page_numbers_from_content_list(content_list)

        # Build section-hierarchical document structure
        document_structure = content_list_to_document_structure(content_list, page_number_map)

        # ── PageIndex enhancement (optional) ───────────────────────
        pageindex_tree_json = None
        if cfg.use_pageindex:
            from .pageindex_tree import run_pageindex_tree, pageindex_to_citeindex_tree
            pi_result = run_pageindex_tree(pdf_path, model=cfg.pageindex_model)
            if pi_result and pi_result.get("structure"):
                logger.info("PageIndex tree available, will use for .citeindex.json")
                pageindex_tree_json = pi_result
            else:
                logger.info("PageIndex tree-building failed or empty, using MinerU structure")

        # Build paragraphs for nodes/merkle (using actual page numbers)
        page_paragraphs = content_list_to_paragraphs(content_list, page_number_map)

        # ── Step 3: Pattern + DSPy + reconcile ─────────────────────
        enriched_csl = _run_extraction(
            content_list=content_list,
            mineru_markdown=mineru_markdown,
            grobid_metadata=grobid_metadata,
            doc_type=doc_type,
            config=cfg,
        )

    elif cfg.use_layout_analysis:
        # === Fitz fallback path (legacy) ===
        logger.info("MinerU unavailable, falling back to fitz layout analysis")
        from .layout import analyze_document_layout
        from .common import build_layout_document_structure

        page_layouts = analyze_document_layout(pdf_path)
        page_paragraphs = _extract_paragraphs_from_layouts(page_layouts)
        document_structure = build_layout_document_structure(page_layouts)
        ordered_text = _collect_ordered_text(page_layouts)

        # Use the old cascade for fitz fallback
        from .common import enrich_csl_with_llm

        base_csl = make_basic_csl(
            source_id=source_id, title=title, csl_type="book",
            extra={"genre": source_type},
        )
        enriched_csl = enrich_csl_with_llm(
            base_csl=base_csl, ordered_text=ordered_text,
            pdf_path=pdf_path, num_pages=num_pages, config=cfg,
        )

    else:
        # === No layout analysis path ===
        page_paragraphs = _extract_page_paragraphs(pdf_path)
        document_structure = build_document_structure(page_paragraphs)
        ordered_text = "\n\n".join("\n".join(paras) for _, paras in page_paragraphs)

        from .common import enrich_csl_with_llm

        base_csl = make_basic_csl(
            source_id=source_id, title=title, csl_type="book",
            extra={"genre": source_type},
        )
        enriched_csl = enrich_csl_with_llm(
            base_csl=base_csl, ordered_text=ordered_text,
            pdf_path=pdf_path, num_pages=num_pages, config=cfg,
        )

    # ── Build final CSL (merge enriched into base) ─────────────────
    base_csl = make_basic_csl(
        source_id=source_id, title=title, csl_type="book",
        extra={"genre": source_type},
    )
    csl = dict(base_csl)
    for key, value in enriched_csl.items():
        if key == "id":
            continue
        if value is not None:
            csl[key] = value

    # Attach GROBID references if available
    if grobid_references.get("references"):
        csl["_cited_references"] = grobid_references["references"]

    # ── Nodes + Merkle tree (no retrieval index) ───────────────────
    nodes = build_nodes_with_granularity(source_id, page_paragraphs, is_primary=cfg.is_primary)
    merkle_tree = build_merkle_for_nodes(nodes)

    if cfg.use_layout_analysis and document_structure.get("pages"):
        hierarchical_merkle = build_hierarchical_merkle_tree(document_structure)
        merkle_tree["hierarchical_root"] = hierarchical_merkle["root"]
        merkle_tree["proof_tree"] = hierarchical_merkle.get("proof_tree")

    document_json: Dict[str, Any] = {
        "source_id": source_id,
        "source_type": source_type,
        "metadata": {
            "title": title,
            "page_count": len(page_paragraphs),
            "source_path": os.path.abspath(pdf_path),
        },
        "structure": document_structure,
        "nodes": nodes,
    }

    # ── Build PageIndex-enhanced CiteIndex tree if available ────────
    extra: Dict[str, Any] = {}
    if pageindex_tree_json is not None:
        from .pageindex_tree import pageindex_to_citeindex_tree
        ci_tree = pageindex_to_citeindex_tree(
            pi_result=pageindex_tree_json,
            doc_id=source_id,
            csl_data=csl,
            page_number_map=page_number_map,
            merkle_root=merkle_tree.get("root"),
        )
        extra["pageindex_tree"] = ci_tree
        logger.info("PageIndex → CiteIndex tree converted: %d sections",
                     len(ci_tree.get("level_1", [])))

    return PipelineResult(
        status="ok",
        source_id=source_id,
        resource_type=source_type,
        csl_json=csl,
        document_json=document_json,
        merkle_tree=merkle_tree,
        extra=extra,
    )


# ---------------------------------------------------------------------------
# Legacy helpers (used by fitz fallback and scanned_pdf.py)
# ---------------------------------------------------------------------------

def _extract_paragraphs_from_layouts(
    page_layouts: List[Dict[str, Any]],
) -> List[Tuple[int, List[str]]]:
    page_paragraphs: List[Tuple[int, List[str]]] = []
    for pl in page_layouts:
        paragraphs: List[str] = []
        for col in pl.get("columns", []):
            for para in col.get("paragraphs", []):
                text = para.get("text", "").strip()
                if text:
                    paragraphs.append(text)
        for fn in pl.get("footnotes", []):
            text = fn.get("text", "").strip()
            if text:
                paragraphs.append(text)
        page_paragraphs.append((pl["page_number"], paragraphs))
    return page_paragraphs


def _collect_ordered_text(page_layouts: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for pl in page_layouts:
        ordered = pl.get("ordered_text", "")
        if ordered.strip():
            parts.append(ordered)
    return "\n\n".join(parts)
