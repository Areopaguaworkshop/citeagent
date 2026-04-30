"""Query Planner Agent — convert user intent into deterministic retrieval plans.

Matches ``.agent/agent/query-planner.md`` and skill ``query-plan-builder.yaml``.

No external knowledge expansion.  Quoted phrases are kept exact.
Named entities preserved as-is.
"""

import hashlib
import logging
import re
from typing import Any, Dict, List, Optional

from .models import QueryPlan, SCHEMA_VERSION

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Intent detection heuristics
# ---------------------------------------------------------------------------

_COMPARISON_SIGNALS = re.compile(
    r"\b(compare|contrast|differ|difference|versus|vs\.?|similarities|distinguish)\b",
    re.IGNORECASE,
)
_TIMELINE_SIGNALS = re.compile(
    r"\b(when|timeline|chronolog|history|evolution|develop|period|century|decade|year)\b",
    re.IGNORECASE,
)
_DEFINITION_SIGNALS = re.compile(
    r"\b(what is|define|definition|meaning|concept|term)\b",
    re.IGNORECASE,
)
_CITATION_LOOKUP_SIGNALS = re.compile(
    r"\b(cite|citation|reference|bibliography|who wrote|author of|published by)\b",
    re.IGNORECASE,
)
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_FILTER_PREFIX_RE = re.compile(r"\b(?:author|year|type|source):\s*\S+", re.IGNORECASE)


def _detect_intent(query: str) -> str:
    if _COMPARISON_SIGNALS.search(query):
        return "comparison"
    if _TIMELINE_SIGNALS.search(query):
        return "timeline"
    if _DEFINITION_SIGNALS.search(query):
        return "definition"
    if _CITATION_LOOKUP_SIGNALS.search(query):
        return "citation_lookup"
    return "fact"


# ---------------------------------------------------------------------------
# Query Plan Builder
# ---------------------------------------------------------------------------

class QueryPlanner:
    """Parse user query and emit a deterministic ``QueryPlan``."""

    def __init__(self, schema_version: str = SCHEMA_VERSION) -> None:
        self.schema_version = schema_version

    def plan(
        self,
        query_text: str,
        session_context: Optional[Dict[str, Any]] = None,
        source_registry: Optional[List[Dict[str, Any]]] = None,
        csl_registry: Optional[List[Dict[str, Any]]] = None,
    ) -> QueryPlan:
        query_id = self._make_query_id(query_text)
        intent_type = _detect_intent(query_text)

        exact_phrases = self._extract_exact_phrases(query_text)
        search_terms = self._extract_search_terms(query_text, exact_phrases)
        must_filters = self._build_must_filters(query_text, csl_registry)
        should_filters = self._build_should_filters(query_text, csl_registry)
        section_targets = self._extract_section_targets(query_text)

        # Detect blocking ambiguity
        clarification_required = False
        clarification_questions: List[str] = []
        if not search_terms and not exact_phrases:
            clarification_required = True
            clarification_questions.append(
                "Your query appears empty or too vague. Could you specify search terms or a topic?"
            )

        return QueryPlan(
            schema_version=self.schema_version,
            query_id=query_id,
            intent_type=intent_type,
            must_filters=must_filters,
            should_filters=should_filters,
            search_terms=search_terms,
            exact_phrases=exact_phrases,
            section_targets=section_targets,
            retrieval_policy=self._select_retrieval_policy(intent_type),
            clarification_required=clarification_required,
            clarification_questions=clarification_questions,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_query_id(query_text: str) -> str:
        return "q-" + hashlib.sha256(query_text.strip().lower().encode()).hexdigest()[:12]

    @staticmethod
    def _extract_exact_phrases(query: str) -> List[str]:
        """Extract explicit quoted phrases or infer a single exact phrase for CJK queries."""
        explicit_phrases = re.findall(r'"([^"]+)"', query)
        if explicit_phrases:
            return explicit_phrases

        # For unquoted CJK queries, keep the cleaned query as an exact phrase target.
        # This helps match OCR text when token boundaries differ around digits/punctuation.
        cleaned = _FILTER_PREFIX_RE.sub(" ", query).strip()
        if cleaned and _CJK_RE.search(cleaned):
            return [cleaned]

        return []

    @staticmethod
    def _extract_search_terms(query: str, exact_phrases: List[str]) -> List[str]:
        """Extract individual search terms (non-stop, non-phrase tokens)."""
        from .indexing import tokenize

        # Remove quoted phrases from query before tokenizing
        cleaned = query
        for phrase in exact_phrases:
            cleaned = cleaned.replace(f'"{phrase}"', "")
        return tokenize(cleaned)

    @staticmethod
    def _build_must_filters(
        query: str, csl_registry: Optional[List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """Build metadata must-filters from explicit constraints in query."""
        filters: List[Dict[str, Any]] = []

        # Detect author: prefix
        author_match = re.search(r"author:\s*(\S+)", query, re.IGNORECASE)
        if author_match:
            filters.append({"field": "author", "value": author_match.group(1)})

        # Detect year: prefix
        year_match = re.search(r"year:\s*(\d{4})", query, re.IGNORECASE)
        if year_match:
            filters.append({"field": "issued.date-parts", "value": year_match.group(1)})

        # Detect type: prefix
        type_match = re.search(r"type:\s*(\S+)", query, re.IGNORECASE)
        if type_match:
            filters.append({"field": "type", "value": type_match.group(1)})

        # Detect source: prefix
        source_match = re.search(r"source:\s*(\S+)", query, re.IGNORECASE)
        if source_match:
            filters.append({"field": "source_id", "value": source_match.group(1)})

        return filters

    @staticmethod
    def _build_should_filters(
        query: str, csl_registry: Optional[List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """Build soft metadata filters (boost but don't exclude)."""
        filters: List[Dict[str, Any]] = []

        # If query mentions a specific title from registry, boost it
        if csl_registry:
            lower_query = query.lower()
            for csl in csl_registry:
                title = csl.get("title", "")
                if title and len(title) > 5 and title.lower() in lower_query:
                    filters.append({
                        "field": "title",
                        "value": title,
                        "boost": 2.0,
                    })
        return filters

    @staticmethod
    def _extract_section_targets(query: str) -> List[str]:
        """Detect section/page references like 'page 5' or 'p3'."""
        targets: List[str] = []
        page_refs = re.findall(r"\bp(?:age)?\s*(\d+)\b", query, re.IGNORECASE)
        for ref in page_refs:
            targets.append(f"p{ref}")
        return targets

    @staticmethod
    def _select_retrieval_policy(intent_type: str) -> str:
        """Select retrieval policy based on query intent.

        - Keyword-centric intents (fact, definition, citation_lookup):
          Use BM25 deterministic pipeline.
        - Reasoning-centric intents (comparison, timeline):
          Use PageIndex tree-search (LLM reasoning), fall back to BM25.
        """
        if intent_type in ("comparison", "timeline"):
            return "pageindex_tree_search -> bm25_fallback"
        return "metadata_filter -> bm25 -> trace_filter"
