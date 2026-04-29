"""URL discovery and content-hash utilities for batch URL article ingestion.

Crawls a root URL using BFS, extracts internal links, and filters
for article-like pages. Also provides lightweight content hashing
for detecting page changes (used by --update-url-article).
"""

import asyncio
import hashlib
import logging
import re
from typing import List, Optional, Set
from urllib.parse import urlparse

import requests
import trafilatura

logger = logging.getLogger(__name__)

# URL path segments that are unlikely to be articles
_SKIP_SEGMENTS = re.compile(
    r"(?:login|signup|register|logout|search|cart|checkout|admin|api|feed|rss|sitemap|tag|category|page/\d+|#)",
    re.IGNORECASE,
)

# File extensions that are not articles
_SKIP_EXTENSIONS = re.compile(
    r"\.(pdf|jpg|jpeg|png|gif|svg|css|js|xml|zip|gz|tar|mp3|mp4|ico|woff2?|ttf|eot)$",
    re.IGNORECASE,
)


def _is_article_url(href: str, root_domain: str) -> bool:
    """Heuristic: keep URLs that look like article pages on the same domain."""
    try:
        parsed = urlparse(href)
    except Exception:
        return False

    # Must be same domain
    if parsed.netloc and parsed.netloc.lower() != root_domain:
        return False

    # Skip anchors-only, empty, or non-http
    if not parsed.path or parsed.path == "/":
        return False

    # Skip known non-article patterns
    if _SKIP_SEGMENTS.search(parsed.path):
        return False

    if _SKIP_EXTENSIONS.search(parsed.path):
        return False

    return True


async def _discover_urls_async(
    root_url: str,
    max_depth: int = 2,
    max_pages: int = 100,
) -> List[str]:
    """Use crawl4ai BFS to discover article URLs from a root page."""
    from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
    from crawl4ai.deep_crawling import BFSDeepCrawlStrategy
    from crawl4ai.deep_crawling.filters import FilterChain, ContentTypeFilter

    root_domain = urlparse(root_url).netloc.lower()

    filter_chain = FilterChain([
        ContentTypeFilter(allowed_types=["text/html"]),
    ])

    strategy = BFSDeepCrawlStrategy(
        max_depth=max_depth,
        include_external=False,
        max_pages=max_pages,
        filter_chain=filter_chain,
    )

    config = CrawlerRunConfig(
        deep_crawl_strategy=strategy,
        stream=True,
    )

    discovered: Set[str] = set()

    async with AsyncWebCrawler() as crawler:
        async for result in await crawler.arun(root_url, config=config):
            if not result.success:
                continue

            # The crawled page itself
            if _is_article_url(result.url, root_domain):
                discovered.add(result.url)

            # Internal links found on this page
            for link in result.links.get("internal", []):
                href = link.get("href", "")
                if href and _is_article_url(href, root_domain):
                    discovered.add(href)

    urls = sorted(discovered)
    logger.info("Discovered %d article URLs from %s (depth=%d)", len(urls), root_url, max_depth)
    return urls


def discover_article_urls(
    root_url: str,
    max_depth: int = 2,
    max_pages: int = 100,
) -> List[str]:
    """Synchronous wrapper: discover article URLs from a root page.

    Uses crawl4ai's AsyncWebCrawler with BFS to crawl the site and
    extract internal links that look like article pages.
    """
    return asyncio.run(_discover_urls_async(root_url, max_depth, max_pages))


# ---------------------------------------------------------------------------
# Lightweight content hashing for update detection
# ---------------------------------------------------------------------------

def fetch_content_hash(url: str) -> Optional[str]:
    """Fetch a URL, extract main text via trafilatura, return its SHA-256 hash.

    Returns None if the fetch or extraction fails. The hash is computed
    on the extracted main content (not raw HTML) so that irrelevant
    changes (ads, timestamps, navigation) are ignored.
    """
    try:
        resp = requests.get(url, timeout=30, headers={"User-Agent": "CiteIndex/0.11"})
        resp.raise_for_status()
        html = resp.text
    except Exception:
        logger.warning("Failed to fetch %s for content hash", url)
        return None

    text = trafilatura.extract(html)
    if not text or not text.strip():
        text = html

    return hashlib.sha256(text.encode("utf-8")).hexdigest()
