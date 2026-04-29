"""URL article ingestion pipeline.

Workflow:
  1. Fetch HTML (Playwright → requests)
  2. Extract content as markdown with headings (trafilatura → readability)
  3. Extract metadata (Zotero → trafilatura)
  4. Pattern-scan for in-page citation guidance (若要引用/Cite this/etc.)
  5. Parse citation string (regex first, DSPy fallback)
  6. Reconcile: citation guidance wins over Zotero/trafilatura
  7. Build section-hierarchical paragraphs from markdown headings
  8. Merkle tree (no retrieval index)
"""

import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
import trafilatura

from ..models import IngestionConfig, PipelineResult
from .common import (
    build_merkle_for_nodes,
    build_nodes,
    make_basic_csl,
    make_source_id,
    split_paragraphs,
)

logger = logging.getLogger(__name__)


def _write_html_snapshot(html: str) -> str:
    fd, path = tempfile.mkstemp(prefix="citeindex_url_", suffix=".html")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(html)
    return path


# ---------------------------------------------------------------------------
# Fetching: Playwright primary, requests fallback
# ---------------------------------------------------------------------------

def _fetch_with_playwright(url: str) -> Optional[str]:
    """Fetch a URL rendering JavaScript via Playwright."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)
            html = page.content()
            browser.close()
            return html
    except Exception:
        logger.info("Playwright fetch failed or not installed, falling back to requests")
        return None


def _fetch_with_requests(url: str) -> str:
    """Simple HTTP GET fallback."""
    resp = requests.get(url, timeout=30, headers={"User-Agent": "CiteIndex/0.11"})
    resp.raise_for_status()
    return resp.text


def _fetch_html(url: str) -> str:
    """Fetch URL with Playwright primary, requests fallback."""
    html = _fetch_with_playwright(url)
    if html:
        return html
    return _fetch_with_requests(url)


# ---------------------------------------------------------------------------
# Content extraction: trafilatura markdown (preserves headings)
# ---------------------------------------------------------------------------

def _extract_markdown(html: str) -> str:
    """Extract main content as markdown, preserving headings."""
    extracted = trafilatura.extract(
        html,
        output_format="markdown",
        include_links=True,
        include_tables=True,
    )
    if extracted and extracted.strip():
        return extracted

    # Fallback: plain text
    logger.info("trafilatura markdown returned empty, trying plain text")
    plain = trafilatura.extract(html)
    if plain and plain.strip():
        return plain

    logger.info("trafilatura returned empty, trying readability-lxml fallback")
    try:
        from readability import Document

        doc = Document(html)
        summary_html = doc.summary()
        from lxml import etree

        tree = etree.HTML(summary_html)
        text = " ".join(tree.itertext()).strip() if tree is not None else ""
        if text:
            return text
    except Exception:
        logger.info("readability-lxml fallback failed or not installed")

    return html


# ---------------------------------------------------------------------------
# Metadata extraction: Zotero → trafilatura
# ---------------------------------------------------------------------------

def _extract_metadata_zotero(url: str) -> Dict[str, Any]:
    """Try zotero translation-server for rich metadata."""
    try:
        resp = requests.post(
            "http://localhost:1969/web",
            headers={"Content-Type": "text/plain"},
            data=url,
            timeout=15,
        )
        if resp.status_code == 200:
            items = resp.json()
            if items and isinstance(items, list) and items[0]:
                item = items[0]
                meta: Dict[str, Any] = {}
                if item.get("title"):
                    meta["title"] = item["title"]
                if item.get("creators"):
                    authors = []
                    for c in item["creators"]:
                        if c.get("lastName"):
                            name: Dict[str, str] = {"family": c["lastName"]}
                            if c.get("firstName"):
                                name["given"] = c["firstName"]
                            authors.append(name)
                    if authors:
                        meta["author"] = authors
                if item.get("date"):
                    meta["date"] = item["date"]
                if item.get("publicationTitle"):
                    meta["container-title"] = item["publicationTitle"]
                if item.get("language"):
                    meta["language"] = item["language"]
                return meta
    except Exception:
        logger.info("zotero-translator not available, falling back to trafilatura metadata")
    return {}


def _extract_metadata(html: str, url: str) -> Dict[str, Any]:
    """Extract metadata with Zotero primary, trafilatura fallback."""
    meta = _extract_metadata_zotero(url)
    if meta.get("title"):
        logger.info("Zotero metadata extraction succeeded")
        return meta

    metadata_obj = trafilatura.extract_metadata(html)
    return {
        "title": (metadata_obj.title if metadata_obj else None) or url,
        "author": metadata_obj.author if metadata_obj else None,
        "date": metadata_obj.date if metadata_obj else None,
    }


# ---------------------------------------------------------------------------
# Citation guidance extraction (pattern-based)
# ---------------------------------------------------------------------------

# Patterns to find citation guidance blocks
_CITE_GUIDANCE_PATTERNS = [
    # Chinese: 若要引用本文 / 若要引用本文，请按以下格式
    re.compile(
        r"若要引用本文[，,]?\s*(?:请按以下格式[：:]?\s*)?(.*?)(?:[。]|也请参考|$)",
        re.DOTALL,
    ),
    # Chinese: 引用格式
    re.compile(r"引用格式\s*[：:]\s*(.*?)(?:[。]|$)", re.DOTALL),
    # Chinese: 版权申明.*转载.*
    re.compile(
        r"版权申明\s*[：:]\s*若您想转载此文[，,]?\s*(.*?)(?:[。]|请按|$)",
        re.DOTALL,
    ),
    # English: Cite this article/entry
    re.compile(
        r"Cite\s+this\s+(?:article|entry)\s*[：:\n]\s*(.*?)(?:\n\n|\n##|\Z)",
        re.DOTALL | re.IGNORECASE,
    ),
    # German: Zitierweise
    re.compile(r"Zitierweise\s*[：:]\s*(.*?)(?:\n\n|\Z)", re.DOTALL),
    # French: Pour citer
    re.compile(r"Pour\s+citer\s*[：:]\s*(.*?)(?:\n\n|\Z)", re.DOTALL | re.IGNORECASE),
]

# Chinese citation string parsers:
#   Author，《Title》，Series（Place：Publisher，Date）
#   Author译《Title》（Place：Publisher，Year）
# Two patterns: 《》 (guillemets, may contain inner <>) and bare <>
_CN_CITE_BOOK_RE = re.compile(
    r"(?P<author>[^，,《]+?)[，,]\s*"
    r"(?:译\s*)?"
    r"《(?P<title>.+?)》[，,]\s*"
    r"(?P<series>.+?)"
    r"[（(](?P<place>[^：:）)]+)[：:](?P<publisher>[^，,）)]+)[，,]"
    r"(?P<date>[^）)]+)[）)]"
)
_CN_CITE_SIMPLE_RE = re.compile(
    r"(?P<author>[^，,《<]+?)[，,]?\s*"
    r"(?:译\s*)?"
    r"[《<](?P<title>[^》>]+)[》>]\s*"
    r"[（(](?P<place>[^：:）)]+)[：:](?P<publisher>[^，,）)]+)[，,]"
    r"(?P<date>[^）)]+)[）)]"
)

# Western Chicago-style: Author. "Title." *Journal*. Published Date. URL
_CHICAGO_CITE_RE = re.compile(
    r"(?P<author>[^.]+?)\.\s*"
    r'["""\u201c\u00ab](?P<title>[^"""\u201d\u00bb]+)["""\u201d\u00bb]\s*\.?\s*'
    r"(?:\*(?P<journal>[^*]+)\*\s*\.?\s*)?"
    r"(?:Published\s+)?(?P<date>[A-Z][a-z]+ \d{1,2},?\s+\d{4}|\d{4}[-/]\d{2}[-/]\d{2}|\d{4})"
)


def _find_citation_guidance(text: str) -> Optional[str]:
    """Scan text for citation guidance blocks, return the citation string."""
    for pat in _CITE_GUIDANCE_PATTERNS:
        m = pat.search(text)
        if m:
            cite_str = m.group(1).strip()
            # Clean up markdown artifacts
            cite_str = re.sub(r"\[#\].*$", "", cite_str, flags=re.MULTILINE).strip()
            cite_str = re.sub(r"\[([^\]]+)\]\[[^\]]*\]", r"\1", cite_str)
            cite_str = re.sub(r"\[([^\]]+)\]\([^\)]*\)", r"\1", cite_str)
            if len(cite_str) > 10:
                return cite_str
    return None


def _parse_citation_string(cite_str: str) -> Dict[str, Any]:
    """Parse a citation guidance string into CSL fields (regex first)."""
    # Try Chinese format — book style with series (《Title》，Series（Place：Publisher，Date）)
    m = _CN_CITE_BOOK_RE.search(cite_str)
    if not m:
        # Simpler format: 《Title》（Place：Publisher，Date）
        m = _CN_CITE_SIMPLE_RE.search(cite_str)

    if m:
        result: Dict[str, Any] = {}
        result["author"] = [{"literal": m.group("author").strip()}]
        result["title"] = m.group("title").strip()
        if m.group("publisher"):
            result["publisher"] = m.group("publisher").strip()
        if m.group("place"):
            result["publisher-place"] = m.group("place").strip()
        try:
            series = m.group("series")
            if series and series.strip():
                result["collection-title"] = series.strip().rstrip("，,")
        except IndexError:
            pass
        date_str = m.group("date").strip()
        result["_raw_date"] = date_str
        parsed_date = _parse_date_string(date_str)
        if parsed_date:
            result["issued"] = parsed_date
        return result

    # Try Chicago format
    m = _CHICAGO_CITE_RE.search(cite_str)
    if m:
        result = {}
        author_raw = m.group("author").strip()
        if "," in author_raw:
            parts = author_raw.split(",", 1)
            result["author"] = [{"family": parts[0].strip(), "given": parts[1].strip()}]
        else:
            result["author"] = [{"literal": author_raw}]
        result["title"] = m.group("title").strip()
        if m.group("journal"):
            result["container-title"] = m.group("journal").strip()
        date_str = m.group("date").strip()
        parsed_date = _parse_date_string(date_str)
        if parsed_date:
            result["issued"] = parsed_date
        return result

    return {}


def _parse_date_string(date_str: str) -> Optional[Dict[str, Any]]:
    """Parse various date formats into CSL date-parts."""
    # Chinese: 2025年10月29日
    m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", date_str)
    if m:
        return {"date-parts": [[int(m.group(1)), int(m.group(2)), int(m.group(3))]]}

    # ISO: 2025-10-29 or 2025/10/29
    m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", date_str)
    if m:
        return {"date-parts": [[int(m.group(1)), int(m.group(2)), int(m.group(3))]]}

    # English: March 4, 2011
    m = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
        r"(\d{1,2}),?\s+(\d{4})",
        date_str,
        re.IGNORECASE,
    )
    if m:
        months = {
            "january": 1, "february": 2, "march": 3, "april": 4,
            "may": 5, "june": 6, "july": 7, "august": 8,
            "september": 9, "october": 10, "november": 11, "december": 12,
        }
        return {"date-parts": [[int(m.group(3)), months[m.group(1).lower()], int(m.group(2))]]}

    # Year only: 2025
    m = re.search(r"(\d{4})", date_str)
    if m:
        return {"date-parts": [[int(m.group(1))]]}

    return None


def _extract_citation_from_guidance(
    text: str,
    config: Optional[IngestionConfig] = None,
) -> Dict[str, Any]:
    """Find and parse in-page citation guidance. DSPy fallback for unparseable strings."""
    cite_str = _find_citation_guidance(text)
    if not cite_str:
        return {}

    logger.info("Found citation guidance: %s", cite_str[:120])

    # Try regex parsing first
    parsed = _parse_citation_string(cite_str)
    if parsed.get("title"):
        logger.info("Regex-parsed citation guidance successfully")
        parsed["_citation_source"] = "in_page_guidance"
        return parsed

    # DSPy fallback
    logger.info("Regex could not parse citation string, trying DSPy")
    cfg = config or IngestionConfig()
    try:
        import dspy
        from ...llm import get_llm_model
        from ...model import ParseCitationString

        lm = get_llm_model(cfg.llm_model, temperature=0.1)
        with dspy.context(lm=lm):
            predictor = dspy.Predict(ParseCitationString)
            result = predictor(citation_string=cite_str)

        parsed = {}
        if result.author:
            parsed["author"] = [{"literal": result.author.strip()}]
        if result.title:
            parsed["title"] = result.title.strip()
        if result.publisher:
            parsed["publisher"] = result.publisher.strip()
        if result.publication_date:
            pd = _parse_date_string(result.publication_date)
            if pd:
                parsed["issued"] = pd
        if parsed.get("title"):
            parsed["_citation_source"] = "in_page_guidance_dspy"
            return parsed
    except Exception:
        logger.warning("DSPy citation parsing failed", exc_info=True)

    return {}


# ---------------------------------------------------------------------------
# Section-hierarchical structure from markdown
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)(?:\s*\[#\].*)?$")


def _parse_markdown_sections(
    markdown_text: str, url: str
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Tuple[int, List[str]]]]:
    """Parse markdown into section-hierarchical pages and paragraph list.

    Returns:
        (pages, section_tree, page_paragraphs)

        pages: list of page dicts with section_number as page_number
        section_tree: nested section hierarchy
        page_paragraphs: [(section_number, [paragraph_texts])] for nodes
    """
    lines = markdown_text.split("\n")

    # First pass: identify sections and their content
    sections: List[Dict[str, Any]] = []
    current_section: Dict[str, Any] = {
        "title": "(intro)",
        "level": 0,
        "paragraphs": [],
        "anchor": "",
    }

    buf: List[str] = []

    def flush_buf():
        if buf:
            text = "\n".join(buf).strip()
            if text:
                current_section["paragraphs"].append(text)
            buf.clear()

    for line in lines:
        m = _HEADING_RE.match(line)
        if m:
            flush_buf()
            # Save current section
            if current_section["paragraphs"]:
                sections.append(current_section)

            level = len(m.group(1))
            heading_text = m.group(2).strip()
            # Extract anchor from [#](anchor) if present
            anchor_m = re.search(r"\[#\]\(#([^)]+)\)", line)
            anchor = anchor_m.group(1) if anchor_m else re.sub(
                r"[^\w\u4e00-\u9fff]+", "-", heading_text.lower()
            ).strip("-")

            current_section = {
                "title": heading_text,
                "level": level,
                "paragraphs": [],
                "anchor": anchor,
            }
        else:
            stripped = line.strip()
            if not stripped:
                flush_buf()
            else:
                buf.append(stripped)

    flush_buf()
    if current_section["paragraphs"]:
        sections.append(current_section)

    # Build pages (one per section), section_tree, and page_paragraphs
    pages: List[Dict[str, Any]] = []
    page_paragraphs: List[Tuple[int, List[str]]] = []
    section_tree: List[Dict[str, Any]] = []
    tree_stack: List[Dict[str, Any]] = []

    for sec_idx, sec in enumerate(sections):
        sec_num = sec_idx + 1
        sec_url = f"{url}#{sec['anchor']}" if sec["anchor"] else url

        # Build paragraphs for this section-page
        para_list: List[Dict[str, Any]] = []
        para_texts: List[str] = []
        for pi, para_text in enumerate(sec["paragraphs"], start=1):
            # Split further by double-newline within the paragraph
            sub_paras = split_paragraphs(para_text)
            for si, sp in enumerate(sub_paras):
                para_id = f"s{sec_num}_para{pi}" if len(sub_paras) == 1 else f"s{sec_num}_para{pi}_{si+1}"
                para_list.append({
                    "paragraph_id": para_id,
                    "text": sp,
                    "section": sec["title"],
                })
                para_texts.append(sp)

        pages.append({
            "page_number": sec_num,
            "section_title": sec["title"],
            "section_level": sec["level"],
            "section_url": sec_url,
            "paragraphs": para_list,
            "footnotes": [],
        })
        page_paragraphs.append((sec_num, para_texts))

        # Build section tree
        tree_node: Dict[str, Any] = {
            "title": sec["title"],
            "level": sec["level"],
            "section_number": sec_num,
            "url": sec_url,
            "children": [],
        }

        # Find parent in stack
        while tree_stack and tree_stack[-1]["level"] >= sec["level"]:
            tree_stack.pop()

        if tree_stack:
            tree_stack[-1]["children"].append(tree_node)
        else:
            section_tree.append(tree_node)

        tree_stack.append(tree_node)

    return pages, section_tree, page_paragraphs


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

def run(
    url: str,
    config: Optional[IngestionConfig] = None,
) -> PipelineResult:
    cfg = config or IngestionConfig()
    source_id = make_source_id(url)
    now = datetime.now(timezone.utc)

    # ── Step 1: Fetch ──────────────────────────────────────────────
    html = _fetch_html(url)

    # ── Step 2: Extract content as markdown (preserves headings) ──
    markdown_text = _extract_markdown(html)

    # ── Step 3: Extract metadata (Zotero first) ───────────────────
    metadata = _extract_metadata(html, url)
    title = metadata.get("title") or url
    author = metadata.get("author")
    date = metadata.get("date")

    # ── Step 4-5: Find & parse in-page citation guidance ──────────
    guidance_csl = _extract_citation_from_guidance(markdown_text, cfg)

    # Also try from raw HTML for JS-rendered cite sections
    if not guidance_csl:
        guidance_csl = _extract_citation_from_guidance(html, cfg)

    # ── Step 6: Reconcile — citation guidance wins ────────────────
    csl_extra: Dict[str, Any] = {
        "URL": url,
        "accessed": {
            "date-parts": [[now.year, now.month, now.day]],
        },
    }

    # Start with Zotero/trafilatura metadata
    if author:
        if isinstance(author, list):
            csl_extra["author"] = author
        else:
            csl_extra["author"] = [{"literal": author}]

    if date:
        if isinstance(date, str) and len(date) >= 4 and date[:4].isdigit():
            csl_extra["issued"] = {"date-parts": [[int(date[:4])]]}

    container_title = metadata.get("container-title")
    if container_title:
        csl_extra["container-title"] = container_title

    # Override with citation guidance (it's more authoritative)
    if guidance_csl:
        logger.info("Overriding metadata with in-page citation guidance")
        if guidance_csl.get("author"):
            csl_extra["author"] = guidance_csl["author"]
        if guidance_csl.get("title"):
            title = guidance_csl["title"]
        if guidance_csl.get("issued"):
            csl_extra["issued"] = guidance_csl["issued"]
        if guidance_csl.get("publisher"):
            csl_extra["publisher"] = guidance_csl["publisher"]
        if guidance_csl.get("publisher-place"):
            csl_extra["publisher-place"] = guidance_csl["publisher-place"]
        if guidance_csl.get("container-title"):
            csl_extra["container-title"] = guidance_csl["container-title"]
        if guidance_csl.get("collection-title"):
            csl_extra["collection-title"] = guidance_csl["collection-title"]
        csl_extra["_citation_source"] = guidance_csl.get("_citation_source", "in_page_guidance")

    csl_json = make_basic_csl(source_id, title, "webpage", csl_extra)

    # ── Step 7: Build section-hierarchical structure ───────────────
    pages, section_tree, page_paragraphs = _parse_markdown_sections(markdown_text, url)
    nodes = build_nodes(source_id, page_paragraphs)

    # ── Step 8: Merkle tree (no retrieval index) ──────────────────
    merkle_tree = build_merkle_for_nodes(nodes)

    # ── PageIndex enhancement (optional) ──────────────────────────
    extra: Dict[str, Any] = {
        "source_snapshot_path": _write_html_snapshot(html),
        "cleanup_source_snapshot": True,
    }
    if cfg.use_pageindex and markdown_text.strip():
        from .pageindex_tree import run_pageindex_md_tree, pageindex_to_citeindex_tree
        pi_result = run_pageindex_md_tree(markdown_text, model=cfg.pageindex_model)
        if pi_result and pi_result.get("structure"):
            ci_tree = pageindex_to_citeindex_tree(
                pi_result=pi_result,
                doc_id=source_id,
                csl_data=csl_json,
                page_number_map={},  # URLs have no physical page numbers
                merkle_root=merkle_tree.get("root"),
            )
            extra["pageindex_tree"] = ci_tree
            logger.info("PageIndex tree built for URL: %d sections",
                        len(ci_tree.get("level_1", [])))

    document_json: Dict[str, Any] = {
        "source_id": source_id,
        "source_type": "url_article",
        "metadata": {
            "title": title,
            "url": url,
            "author": csl_extra.get("author"),
            "publication_date": date,
        },
        "structure": {
            "pages": pages,
            "section_tree": section_tree,
        },
        "nodes": nodes,
    }

    return PipelineResult(
        status="ok",
        source_id=source_id,
        resource_type="url_article",
        csl_json=csl_json,
        document_json=document_json,
        merkle_tree=merkle_tree,
        extra=extra,
    )
