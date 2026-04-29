import logging
import os
from typing import Optional

from ..models import IngestionConfig, PipelineResult
from . import digital_pdf

logger = logging.getLogger(__name__)


def _ensure_searchable_with_lang_detection(pdf_path: str, config: IngestionConfig) -> str:
    """Run OCR with automatic language detection (merged from legacy ocr_lang_detect)."""
    if config.lang != "auto":
        from ...utils import ensure_searchable_pdf
        return ensure_searchable_pdf(pdf_path, config.lang)

    from ...utils import ensure_searchable_pdf_with_detection
    return ensure_searchable_pdf_with_detection(pdf_path)


def _clean_ocr_text(text: str, num_pages: int, config: IngestionConfig) -> str:
    """Apply OCR text cleaning before further processing."""
    try:
        from ...ocr_text_clean_before_llm import clean_extracted_text
        from ...utils import parse_page_range

        extracted_pages = parse_page_range(config.page_range, num_pages)
        return clean_extracted_text(
            text, num_pages, config.text_direction, config.page_range, extracted_pages
        )
    except Exception:
        logger.warning("OCR text cleaning failed, using raw text", exc_info=True)
        return text


def _handle_vertical_text(pdf_path: str, config: IngestionConfig) -> Optional[str]:
    """Detect and handle vertical CJK text, returning extracted text or None."""
    if config.text_direction == "horizontal":
        return None

    try:
        from ...vertical_handler import is_pdf_vertical, process_vertical_pdf

        if config.text_direction == "vertical":
            logger.info("Forced vertical mode, processing with PaddleOCR")
            return process_vertical_pdf(pdf_path, config.vertical_lang)

        # auto mode: detect then decide
        if is_pdf_vertical(pdf_path, config.vertical_lang):
            logger.info("Vertical layout detected, processing with PaddleOCR")
            return process_vertical_pdf(pdf_path, config.vertical_lang)

    except Exception:
        logger.warning("Vertical text handling failed, falling back to standard", exc_info=True)

    return None


def run(
    pdf_path: str,
    config: Optional[IngestionConfig] = None,
) -> PipelineResult:
    cfg = config or IngestionConfig()

    # Step 1: Try vertical text path first (legacy vertical_handler support)
    vertical_text = _handle_vertical_text(pdf_path, cfg)
    if vertical_text is not None:
        # For vertical PDFs, skip layout analysis (columns don't apply)
        vert_cfg = IngestionConfig(
            llm_model=cfg.llm_model,
            text_direction="vertical",
            vertical_lang=cfg.vertical_lang,
            lang=cfg.lang,
            page_range=cfg.page_range,
            citation_style=cfg.citation_style,
            doc_type_override=cfg.doc_type_override,
            use_layout_analysis=False,
        )
        result = digital_pdf.run(pdf_path, source_type="scanned_pdf", config=vert_cfg)
        return result

    # Step 2: OCR normalization with language auto-detection
    searchable_pdf = _ensure_searchable_with_lang_detection(pdf_path, cfg)

    # Step 3: Clean OCR text (blank page filtering, header/footer removal)
    try:
        import fitz
        doc = fitz.open(searchable_pdf)
        num_pages = doc.page_count
        raw_text = "\n".join(doc[i].get_text("text") for i in range(num_pages))
        doc.close()
        _clean_ocr_text(raw_text, num_pages, cfg)
        logger.debug("OCR text cleaning applied (%d pages)", num_pages)
    except Exception:
        logger.debug("OCR text cleaning skipped", exc_info=True)

    # Step 4: Run through the digital PDF pipeline (with layout analysis)
    result = digital_pdf.run(searchable_pdf, source_type="scanned_pdf", config=cfg)

    if result.document_json is not None:
        result.document_json["metadata"]["normalized_pdf_path"] = searchable_pdf
        result.document_json["metadata"]["original_pdf_path"] = os.path.abspath(pdf_path)

    return result
