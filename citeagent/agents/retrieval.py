"""Retrieval Agent — deterministic BM25-based evidence retrieval.

Matches ``.agent/agent/retrieval.md`` and skill ``bm25-ranker.yaml``.

Three-stage retrieval policy (fixed):
  1. CSL metadata filters
  2. BM25 over indexed node text
  3. Strict trace filter (drop nodes with incomplete provenance)

Tie-break order:
  - exact phrase hits
  - section-title match
  - depth priority (page number ascending)
  - node_id lexical order

No embeddings.
"""

import logging
import math
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

from .models import RetrievalResult, ScoredNode, SCHEMA_VERSION

logger = logging.getLogger(__name__)


class RetrievalAgent:
    """Execute deterministic retrieval against the inverted index."""

    def __init__(
        self,
        schema_version: str = SCHEMA_VERSION,
        top_k: int = 20,
    ) -> None:
        self.schema_version = schema_version
        self.top_k = top_k

    def run(
        self,
        query_plan: Dict[str, Any],
        nodes: List[Dict[str, Any]],
        inverted_index: Dict[str, List[str]],
        csl_registry: Optional[List[Dict[str, Any]]] = None,
    ) -> RetrievalResult:
        query_id = query_plan.get("query_id", "")

        # Build lookup tables
        node_map: Dict[str, Dict[str, Any]] = {n["node_id"]: n for n in nodes}

        # Stage 1: CSL metadata filters
        candidate_ids = self._apply_metadata_filters(
            query_plan, nodes, csl_registry or []
        )
        logger.info("Stage 1 (metadata filter): %d candidates", len(candidate_ids))

        # Stage 2: BM25 scoring
        search_terms = query_plan.get("search_terms", [])
        exact_phrases = query_plan.get("exact_phrases", [])
        section_targets = query_plan.get("section_targets", [])

        scored = self._bm25_score(
            search_terms, candidate_ids, inverted_index, node_map, len(nodes)
        )
        bm25_hit_count = len(scored)

        if not scored and (exact_phrases or section_targets):
            scored = {
                node_id: {"bm25": 0.0, "total": 0.0}
                for node_id in candidate_ids
            }

        # Apply phrase boosts
        for node_id in scored:
            phrase_boost = self._phrase_boost(exact_phrases, node_map.get(node_id, {}))
            scored[node_id]["phrase_boost"] = phrase_boost
            scored[node_id]["total"] += phrase_boost

        # Apply section target boosts
        for node_id in scored:
            section_boost = self._section_boost(section_targets, node_map.get(node_id, {}))
            scored[node_id]["section_boost"] = section_boost
            scored[node_id]["total"] += section_boost

        scored = self._keep_positive_scores(scored)

        logger.info(
            "Stage 2 (BM25 + boosts): %d scored nodes (%d BM25 hits)",
            len(scored),
            bm25_hit_count,
        )

        # Stage 3: Strict trace filter — drop nodes missing provenance
        traced = self._trace_filter(scored, node_map)
        logger.info("Stage 3 (trace filter): %d traced nodes", len(traced))

        # Rank with deterministic tie-breaking
        ranked = self._rank_and_tiebreak(traced, node_map)

        # Build output
        ranked_nodes = []
        for node_id, score_data in ranked[: self.top_k]:
            node = node_map.get(node_id, {})
            ranked_nodes.append(
                ScoredNode(
                    node_id=node_id,
                    source_id=node.get("source_id", ""),
                    section_path=node.get("section_path", ""),
                    sha256=node.get("sha256", ""),
                    text=node.get("text", ""),
                    page=node.get("page"),
                    score_breakdown=score_data,
                    total_score=score_data.get("total", 0.0),
                ).to_dict()
            )

        return RetrievalResult(
            schema_version=self.schema_version,
            query_id=query_id,
            ranked_nodes=ranked_nodes,
            candidate_relations=[],
            retrieval_debug={
                "total_nodes": len(nodes),
                "after_metadata_filter": len(candidate_ids),
                "after_bm25": bm25_hit_count,
                "after_boosts": len(scored),
                "after_trace_filter": len(traced),
                "returned": len(ranked_nodes),
            },
        )

    # ------------------------------------------------------------------
    # Stage 1: Metadata filters
    # ------------------------------------------------------------------

    def _apply_metadata_filters(
        self,
        query_plan: Dict[str, Any],
        nodes: List[Dict[str, Any]],
        csl_registry: List[Dict[str, Any]],
    ) -> Set[str]:
        must_filters = query_plan.get("must_filters", [])
        if not must_filters:
            return {n["node_id"] for n in nodes}

        # Build CSL lookup by source_id
        csl_by_source: Dict[str, Dict[str, Any]] = {}
        for csl in csl_registry:
            sid = csl.get("_source_id") or csl.get("id", "")
            csl_by_source[sid] = csl

        # Determine which source_ids pass all must-filters
        passing_sources: Optional[Set[str]] = None
        source_ids = {n.get("source_id", "") for n in nodes}

        for filt in must_filters:
            field = filt.get("field", "")
            value = str(filt.get("value", "")).lower()
            matching: Set[str] = set()

            if field == "source_id":
                for sid in source_ids:
                    if value in sid.lower():
                        matching.add(sid)
            else:
                for sid in source_ids:
                    csl = csl_by_source.get(sid, {})
                    if self._csl_field_matches(csl, field, value):
                        matching.add(sid)

            if passing_sources is None:
                passing_sources = matching
            else:
                passing_sources &= matching

        if passing_sources is None:
            passing_sources = source_ids

        return {
            n["node_id"] for n in nodes if n.get("source_id", "") in passing_sources
        }

    @staticmethod
    def _csl_field_matches(csl: Dict[str, Any], field: str, value: str) -> bool:
        if field == "author":
            authors = csl.get("author", [])
            for author in authors:
                name = f"{author.get('given', '')} {author.get('family', '')}".lower()
                if value in name:
                    return True
            return False
        if field == "issued.date-parts":
            issued = csl.get("issued", {})
            date_parts = issued.get("date-parts", [[]])
            if date_parts and date_parts[0]:
                return str(date_parts[0][0]) == value
            return False
        # Generic field match
        csl_value = csl.get(field, "")
        if isinstance(csl_value, str):
            return value in csl_value.lower()
        return str(csl_value).lower() == value

    # ------------------------------------------------------------------
    # Stage 2: BM25 scoring
    # ------------------------------------------------------------------

    # BM25 parameters
    _K1 = 1.2
    _B = 0.75

    def _bm25_score(
        self,
        terms: List[str],
        candidate_ids: Set[str],
        inverted_index: Dict[str, List[str]],
        node_map: Dict[str, Dict[str, Any]],
        total_docs: int,
    ) -> Dict[str, Dict[str, float]]:
        """Compute BM25 score for each candidate node."""
        if not terms:
            return {}

        # Average document length
        doc_lengths: Dict[str, int] = {}
        for nid in candidate_ids:
            node = node_map.get(nid)
            if node:
                from .indexing import tokenize
                doc_lengths[nid] = len(tokenize(node.get("text", "")))
            else:
                doc_lengths[nid] = 0

        avgdl = sum(doc_lengths.values()) / max(len(doc_lengths), 1)

        scores: Dict[str, Dict[str, float]] = defaultdict(
            lambda: {"bm25": 0.0, "total": 0.0}
        )

        for term in terms:
            posting_list = inverted_index.get(term, [])
            # Filter to candidates only
            relevant = [nid for nid in posting_list if nid in candidate_ids]
            df = len(relevant)
            if df == 0:
                continue

            # IDF
            idf = math.log((total_docs - df + 0.5) / (df + 0.5) + 1.0)

            for nid in relevant:
                # Term frequency in this document
                node = node_map.get(nid)
                if not node:
                    continue
                from .indexing import tokenize
                tokens = tokenize(node.get("text", ""))
                tf = tokens.count(term)
                dl = doc_lengths.get(nid, 0)

                # BM25 formula
                numerator = tf * (self._K1 + 1)
                denominator = tf + self._K1 * (1 - self._B + self._B * dl / max(avgdl, 1))
                term_score = idf * numerator / max(denominator, 0.001)

                scores[nid]["bm25"] += term_score
                scores[nid]["total"] += term_score

        return dict(scores)

    @staticmethod
    def _keep_positive_scores(
        scored: Dict[str, Dict[str, float]],
    ) -> Dict[str, Dict[str, float]]:
        return {
            node_id: score_data
            for node_id, score_data in scored.items()
            if score_data.get("total", 0.0) > 0.0
        }

    # ------------------------------------------------------------------
    # Boosts
    # ------------------------------------------------------------------

    @staticmethod
    def _phrase_boost(exact_phrases: List[str], node: Dict[str, Any]) -> float:
        if not exact_phrases or not node:
            return 0.0
        text = node.get("text", "").lower()
        boost = 0.0
        for phrase in exact_phrases:
            if phrase.lower() in text:
                boost += 5.0
        return boost

    @staticmethod
    def _section_boost(section_targets: List[str], node: Dict[str, Any]) -> float:
        if not section_targets or not node:
            return 0.0
        section = node.get("section_path", "")
        if section in section_targets:
            return 3.0
        return 0.0

    # ------------------------------------------------------------------
    # Stage 3: Trace filter
    # ------------------------------------------------------------------

    @staticmethod
    def _trace_filter(
        scored: Dict[str, Dict[str, float]],
        node_map: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Dict[str, float]]:
        """Drop nodes with incomplete provenance (missing sha256 or source_id)."""
        traced: Dict[str, Dict[str, float]] = {}
        for node_id, score_data in scored.items():
            node = node_map.get(node_id, {})
            if not node.get("sha256") or not node.get("source_id"):
                continue
            traced[node_id] = score_data
        return traced

    # ------------------------------------------------------------------
    # Ranking with deterministic tie-breaking
    # ------------------------------------------------------------------

    @staticmethod
    def _rank_and_tiebreak(
        scored: Dict[str, Dict[str, float]],
        node_map: Dict[str, Dict[str, Any]],
    ) -> List[tuple]:
        """Rank nodes with deterministic tie-breaking:
        1. Total score (descending)
        2. Exact phrase hits (descending)
        3. Section-title match (descending)
        4. Depth priority — page number (ascending)
        5. node_id lexical order (ascending)
        """
        items = []
        for node_id, score_data in scored.items():
            node = node_map.get(node_id, {})
            items.append((
                node_id,
                score_data,
                -score_data.get("total", 0.0),
                -score_data.get("phrase_boost", 0.0),
                -score_data.get("section_boost", 0.0),
                node.get("page", 9999),
                node_id,
            ))

        items.sort(key=lambda x: (x[2], x[3], x[4], x[5], x[6]))
        return [(item[0], item[1]) for item in items]
