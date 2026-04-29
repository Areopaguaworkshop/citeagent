"""Layout analysis for PDF pages: column detection, footnote isolation, reading order."""

import logging
import statistics
from collections import Counter
from typing import Any, Dict, List, Tuple

import fitz

logger = logging.getLogger(__name__)


def extract_text_blocks(page: fitz.Page) -> List[Dict[str, Any]]:
    """Extract text blocks with positional coordinates and font info from a page.

    Returns list of dicts with keys:
      page_number, block_id, text, bbox (x0,y0,x1,y1), font_size, font_name, lines
    """
    page_dict = page.get_text("dict")
    page_number = page.number + 1
    blocks: List[Dict[str, Any]] = []

    for block_idx, block in enumerate(page_dict.get("blocks", [])):
        if "lines" not in block:
            continue

        lines: List[Dict[str, Any]] = []
        font_sizes: List[float] = []
        font_names: List[str] = []

        for line in block["lines"]:
            spans = line.get("spans", [])
            line_text = "".join(span.get("text", "") for span in spans)
            if not line_text.strip():
                continue

            for span in spans:
                size = span.get("size", 0.0)
                name = span.get("font", "")
                char_count = len(span.get("text", ""))
                font_sizes.extend([size] * char_count)
                font_names.extend([name] * char_count)

            lines.append({
                "text": line_text,
                "bbox": list(line["bbox"]),
            })

        if not lines:
            continue

        full_text = "\n".join(ln["text"] for ln in lines)
        size_counter = Counter(font_sizes)
        name_counter = Counter(font_names)
        dominant_size = size_counter.most_common(1)[0][0] if size_counter else 0.0
        dominant_name = name_counter.most_common(1)[0][0] if name_counter else ""

        blocks.append({
            "page_number": page_number,
            "block_id": block_idx,
            "text": full_text,
            "bbox": list(block["bbox"]),
            "font_size": dominant_size,
            "font_name": dominant_name,
            "lines": lines,
        })

    return blocks


def detect_columns(
    blocks: List[Dict[str, Any]], page_width: float
) -> List[List[Dict[str, Any]]]:
    """Detect column boundaries using x-coordinate clustering.

    Groups blocks into columns by clustering their x0 coordinates.
    Returns list of columns, each column is a list of blocks, ordered left-to-right.
    """
    if not blocks:
        return []

    sorted_blocks = sorted(blocks, key=lambda b: b["bbox"][0])
    gap_threshold = page_width * 0.10

    columns: List[List[Dict[str, Any]]] = [[sorted_blocks[0]]]
    for block in sorted_blocks[1:]:
        prev_x1_values = [b["bbox"][2] for b in columns[-1]]
        prev_x1_max = max(prev_x1_values)
        cur_x0 = block["bbox"][0]

        if cur_x0 - prev_x1_max > gap_threshold:
            columns.append([block])
        else:
            columns[-1].append(block)

    return columns


def detect_footnotes(
    blocks: List[Dict[str, Any]], page_height: float
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Identify footnotes based on position and font size.

    Rules from YAML:
    - Located near bottom of page (bottom 15%)
    - Smaller font size than body text median
    - Often begins with numeric marker

    Returns (body_blocks, footnote_blocks)
    """
    if not blocks:
        return [], []

    font_sizes = [b["font_size"] for b in blocks if b["font_size"] > 0]
    if not font_sizes:
        return list(blocks), []

    median_size = statistics.median(font_sizes)
    bottom_threshold = page_height * 0.85

    body: List[Dict[str, Any]] = []
    footnotes: List[Dict[str, Any]] = []

    for block in blocks:
        y0 = block["bbox"][1]
        text = block["text"].lstrip()
        in_bottom = y0 >= bottom_threshold
        small_font = block["font_size"] < median_size * 0.85
        has_marker = len(text) > 1 and text[0].isdigit() and text[1] in (" ", ".", "\t")

        if in_bottom and (small_font or has_marker):
            footnotes.append(block)
        else:
            body.append(block)

    return body, footnotes


def resolve_reading_order(
    columns: List[List[Dict[str, Any]]], footnotes: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Construct deterministic reading order across columns.

    Algorithm from YAML:
    1. Sort columns left to right
    2. Sort blocks top to bottom within each column
    3. Append footnotes after body

    Returns ordered list of all blocks.
    """
    ordered: List[Dict[str, Any]] = []

    cols_sorted = sorted(columns, key=lambda col: min(b["bbox"][0] for b in col))
    for col in cols_sorted:
        for block in sorted(col, key=lambda b: b["bbox"][1]):
            ordered.append(block)

    for fn in sorted(footnotes, key=lambda b: b["bbox"][1]):
        ordered.append(fn)

    return ordered


def analyze_page_layout(page: fitz.Page, page_number: int) -> Dict[str, Any]:
    """Main entry point: analyze a single page's layout.

    Returns structured dict:
    {
        "page_number": int,
        "columns": [
            {
                "column_id": int,
                "paragraphs": [
                    {"paragraph_id": str, "text": str, "lines": [...], "bbox": [...]}
                ]
            }
        ],
        "footnotes": [
            {"footnote_id": str, "text": str, "bbox": [...]}
        ],
        "ordered_text": str
    }
    """
    blocks = extract_text_blocks(page)
    body_blocks, footnote_blocks = detect_footnotes(blocks, page.rect.height)
    columns = detect_columns(body_blocks, page.rect.width)
    ordered = resolve_reading_order(columns, footnote_blocks)

    column_dicts: List[Dict[str, Any]] = []
    for col_idx, col_blocks in enumerate(columns):
        col_sorted = sorted(col_blocks, key=lambda b: b["bbox"][1])
        paragraphs: List[Dict[str, Any]] = []
        for para_idx, block in enumerate(col_sorted, start=1):
            paragraphs.append({
                "paragraph_id": f"p{page_number}_c{col_idx}_para{para_idx}",
                "text": block["text"],
                "lines": block["lines"],
                "bbox": block["bbox"],
            })
        column_dicts.append({
            "column_id": col_idx,
            "paragraphs": paragraphs,
        })

    fn_dicts: List[Dict[str, Any]] = []
    for fn_idx, fn_block in enumerate(
        sorted(footnote_blocks, key=lambda b: b["bbox"][1]), start=1
    ):
        fn_dicts.append({
            "footnote_id": f"p{page_number}_fn{fn_idx}",
            "text": fn_block["text"],
            "bbox": fn_block["bbox"],
        })

    ordered_text = "\n\n".join(block["text"] for block in ordered)

    return {
        "page_number": page_number,
        "columns": column_dicts,
        "footnotes": fn_dicts,
        "ordered_text": ordered_text,
    }


def analyze_document_layout(pdf_path: str) -> List[Dict[str, Any]]:
    """Analyze layout for all pages in a PDF document.

    Returns list of page layout dicts from analyze_page_layout().
    """
    doc = fitz.open(pdf_path)
    results: List[Dict[str, Any]] = []
    for page_idx in range(doc.page_count):
        page = doc[page_idx]
        page_number = page_idx + 1
        try:
            layout = analyze_page_layout(page, page_number)
        except Exception:
            logger.exception("Layout analysis failed for page %d", page_number)
            layout = {
                "page_number": page_number,
                "columns": [],
                "footnotes": [],
                "ordered_text": "",
            }
        results.append(layout)
    doc.close()
    return results
