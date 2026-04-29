"""Indexing Agent — build deterministic inverted index, section index,
and cross-source link candidates.

Matches ``.agent/agent/indexing.md`` and skills:
  - ``inverted-index-builder.yaml``
  - ``cross-source-linker.yaml``

No embeddings.  All outputs are reproducible given the same node set.
"""

import logging
import re
from collections import defaultdict
from typing import Any, Dict, List, Set, Tuple

from .models import IndexingOutput, IndexingReport, SCHEMA_VERSION

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tokenizer (versioned as "simple_v1")
# ---------------------------------------------------------------------------

_TOKENIZER_VERSION = "simple_v1"

# Basic stop-words kept minimal — we want recall in academic text
_STOP_WORDS: Set[str] = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "it", "as", "be", "was", "were",
    "are", "this", "that", "these", "those", "not", "no", "do", "does",
    "did", "has", "have", "had", "will", "would", "can", "could", "may",
    "might", "shall", "should", "its", "also", "than", "then", "so",
    "if", "we", "he", "she", "they", "you", "i", "me", "my", "our",
    "his", "her", "their", "your", "all", "each", "every", "both",
    "few", "more", "most", "other", "some", "such", "only", "own",
    "same", "very", "just", "about", "above", "after", "before",
    "between", "into", "through", "during", "up", "down", "out",
    "over", "under", "again", "further", "been", "being", "there",
    "here", "when", "where", "which", "who", "whom", "what", "how",
    "de", "des", "du", "la", "le", "les", "un", "une", "et", "en",
    "的", "了", "在", "是", "我", "他", "她", "它", "们", "这", "那",
    "有", "和", "与", "为", "以", "而", "之", "其", "也", "不", "所",
    "于", "中", "上", "下",
}

_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff\u3400-\u4dbf]+", re.UNICODE)


def tokenize(text: str) -> List[str]:
    """Fixed tokenizer: lowercase, unicode-aware, stop-word filtered."""
    raw = _TOKEN_RE.findall(text.lower())
    return [t for t in raw if t not in _STOP_WORDS and len(t) > 1]


# ---------------------------------------------------------------------------
# Indexing Agent
# ---------------------------------------------------------------------------

class IndexingAgent:
    """Build deterministic indexes from ingested nodes."""

    def __init__(self, schema_version: str = SCHEMA_VERSION) -> None:
        self.schema_version = schema_version

    def run(
        self,
        nodes: List[Dict[str, Any]],
        source_registry: List[Dict[str, Any]] | None = None,
    ) -> IndexingOutput:
        inverted_index = self._build_inverted_index(nodes)
        section_index = self._build_section_index(nodes)
        cross_source_links = self._build_cross_source_links(nodes)

        source_ids = {n.get("source_id") for n in nodes}
        total_tokens = sum(len(v) for v in inverted_index.values())

        report = IndexingReport(
            schema_version=self.schema_version,
            tokenizer_version=_TOKENIZER_VERSION,
            total_nodes=len(nodes),
            total_tokens=total_tokens,
            total_sources=len(source_ids),
            cross_source_links=len(cross_source_links),
        )

        return IndexingOutput(
            schema_version=self.schema_version,
            inverted_index=inverted_index,
            section_index=section_index,
            cross_source_links=cross_source_links,
            indexing_report=report.to_dict(),
        )

    # ------------------------------------------------------------------
    # Inverted index
    # ------------------------------------------------------------------

    def _build_inverted_index(
        self, nodes: List[Dict[str, Any]]
    ) -> Dict[str, List[str]]:
        """Token → sorted list of node_ids (posting lists)."""
        postings: Dict[str, Set[str]] = defaultdict(set)
        for node in nodes:
            text = node.get("text", "")
            node_id = node.get("node_id", "")
            if not text or not node_id:
                continue
            for token in tokenize(text):
                postings[token].add(node_id)

        # Sort posting lists by node_id for determinism
        return {
            token: sorted(node_ids) for token, node_ids in sorted(postings.items())
        }

    # ------------------------------------------------------------------
    # Section / title index
    # ------------------------------------------------------------------

    def _build_section_index(
        self, nodes: List[Dict[str, Any]]
    ) -> Dict[str, List[str]]:
        """section_path → sorted list of node_ids."""
        sections: Dict[str, Set[str]] = defaultdict(set)
        for node in nodes:
            section = node.get("section_path", "")
            node_id = node.get("node_id", "")
            if section and node_id:
                sections[section].add(node_id)

        return {
            section: sorted(node_ids)
            for section, node_ids in sorted(sections.items())
        }

    # ------------------------------------------------------------------
    # Cross-source link candidates
    # ------------------------------------------------------------------

    _OVERLAP_THRESHOLD = 0.25  # Minimum Jaccard overlap to propose a link

    def _build_cross_source_links(
        self, nodes: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Propose cross-source relations via lexical overlap.

        Only links nodes from *different* ``source_id`` values.
        Relation labels: supports, contradicts, extends, parallels.
        """
        # Group nodes by source
        by_source: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for node in nodes:
            by_source[node.get("source_id", "")].append(node)

        source_ids = sorted(by_source.keys())
        if len(source_ids) < 2:
            return []

        # Pre-tokenize
        node_tokens: Dict[str, Set[str]] = {}
        for node in nodes:
            node_tokens[node["node_id"]] = set(tokenize(node.get("text", "")))

        links: List[Dict[str, Any]] = []

        for i, sid_a in enumerate(source_ids):
            for sid_b in source_ids[i + 1:]:
                for node_a in by_source[sid_a]:
                    tokens_a = node_tokens[node_a["node_id"]]
                    if len(tokens_a) < 3:
                        continue
                    for node_b in by_source[sid_b]:
                        tokens_b = node_tokens[node_b["node_id"]]
                        if len(tokens_b) < 3:
                            continue
                        jaccard = self._jaccard(tokens_a, tokens_b)
                        if jaccard >= self._OVERLAP_THRESHOLD:
                            links.append({
                                "source_node": node_a["node_id"],
                                "target_node": node_b["node_id"],
                                "relation": "parallels",
                                "confidence": round(jaccard, 4),
                                "rationale": f"Jaccard overlap {jaccard:.2%} on {len(tokens_a & tokens_b)} shared tokens",
                            })

        # Sort for determinism
        links.sort(key=lambda lk: (lk["source_node"], lk["target_node"]))
        return links

    @staticmethod
    def _jaccard(a: Set[str], b: Set[str]) -> float:
        if not a and not b:
            return 0.0
        return len(a & b) / len(a | b)
