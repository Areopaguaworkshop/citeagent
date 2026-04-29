"""Ingestion commands — file, url, crawl."""
from __future__ import annotations

from typing import Any, Dict, Optional

from ..utils.citeindex_backend import CiteIndexBackend


_backend = CiteIndexBackend()


def _build_ingest_config(
    llm_model: str = "ollama/qwen3",
    text_direction: str = "horizontal",
    vertical_lang: str = "ch",
    lang: str = "auto",
    page_range: str = "1-5, -3",
    doc_type: Optional[str] = None,
    use_layout: bool = True,
    is_primary: bool = False,
    use_pageindex: bool = False,
    pageindex_model: str = "ollama/qwen3.5:cloud",
    cite_style: str = "chicago-author-date",
) -> Dict[str, Any]:
    """Build ingest configuration dict for passing to backend."""
    return {
        "llm_model": llm_model,
        "text_direction": text_direction,
        "vertical_lang": vertical_lang,
        "lang": lang,
        "page_range": page_range,
        "doc_type_override": doc_type,
        "use_layout_analysis": use_layout,
        "is_primary": is_primary,
        "use_pageindex": use_pageindex,
        "pageindex_model": pageindex_model,
    }


def ingest_file(
    input_path: str,
    corpus_root: str = "corpus",
    llm_model: str = "ollama/qwen3",
    text_direction: str = "horizontal",
    vertical_lang: str = "ch",
    lang: str = "auto",
    page_range: str = "1-5, -3",
    doc_type: Optional[str] = None,
    use_layout: bool = True,
    is_primary: bool = False,
    use_pageindex: bool = False,
    pageindex_model: str = "ollama/qwen3.5:cloud",
    schema_version: str = "1.0.0",
) -> Dict[str, Any]:
    """Ingest a file (PDF, DJVU, DOCX, etc.) into the corpus."""
    return _backend.ingest(
        input_ref=input_path,
        corpus_root=corpus_root,
        llm_model=llm_model,
        text_direction=text_direction,
        vertical_lang=vertical_lang,
        lang=lang,
        page_range=page_range,
        doc_type_override=doc_type,
        use_layout_analysis=use_layout,
        is_primary=is_primary,
        use_pageindex=use_pageindex,
        pageindex_model=pageindex_model,
        schema_version=schema_version,
    )


def ingest_url(
    url: str,
    corpus_root: str = "corpus",
    llm_model: str = "ollama/qwen3",
    text_direction: str = "horizontal",
    lang: str = "auto",
    doc_type: Optional[str] = None,
    use_pageindex: bool = False,
    pageindex_model: str = "ollama/qwen3.5:cloud",
    schema_version: str = "1.0.0",
    **kwargs: Any,
) -> Dict[str, Any]:
    """Ingest a URL into the corpus."""
    return _backend.ingest(
        input_ref=url,
        corpus_root=corpus_root,
        llm_model=llm_model,
        text_direction=text_direction,
        lang=lang,
        doc_type_override=doc_type,
        use_pageindex=use_pageindex,
        pageindex_model=pageindex_model,
        schema_version=schema_version,
        **kwargs,
    )


def ingest_crawl(
    root_url: str,
    corpus_root: str = "corpus",
    llm_model: str = "ollama/qwen3",
    update: bool = False,
    max_depth: int = 2,
    max_pages: int = 100,
    schema_version: str = "1.0.0",
    **kwargs: Any,
) -> Dict[str, Any]:
    """Crawl and ingest all article pages from a URL."""
    return _backend.ingest_all_urls(
        root_url=root_url,
        corpus_root=corpus_root,
        llm_model=llm_model,
        update=update,
        max_depth=max_depth,
        max_pages=max_pages,
        schema_version=schema_version,
        **kwargs,
    )