"""Generation Agent — trace-bound answer generation with Chicago citations.

Matches ``.agent/agent/generation.md`` and skills:
  - ``chicago-formatter.yaml``
  - ``trace-json-assembler.yaml``

Every claim maps to at least one ``node_id``.
Machine mode includes Merkle proofs.  Human mode uses Chicago author-date.
"""

import logging
from typing import Any, Dict, List, Optional

from .models import AnswerMachine, EvidenceItem, GenerationOutput, SCHEMA_VERSION

logger = logging.getLogger(__name__)


class GenerationAgent:
    """Produce answers strictly from retrieved evidence nodes."""

    def __init__(self, schema_version: str = SCHEMA_VERSION) -> None:
        self.schema_version = schema_version

    def generate(
        self,
        query_id: str,
        user_query: str,
        retrieval_result: Dict[str, Any],
        csl_registry: List[Dict[str, Any]],
        merkle_registry: Dict[str, Dict[str, Any]],
        citation_style: str = "chicago-author-date",
        llm_model: Optional[str] = None,
    ) -> GenerationOutput:
        ranked_nodes = retrieval_result.get("ranked_nodes", [])

        if not ranked_nodes:
            return GenerationOutput(
                schema_version=self.schema_version,
                answer_machine=AnswerMachine(
                    schema_version=self.schema_version,
                    query_id=query_id,
                    answer="",
                    evidence=[],
                ).to_dict(),
                answer_human="No evidence found for the query.",
            )

        # Build evidence items with Merkle proofs and citations
        evidence_items = self._build_evidence(
            ranked_nodes, csl_registry, merkle_registry, citation_style
        )

        # Generate answer text
        answer_text, human_text = self._compose_answer(
            user_query, ranked_nodes, evidence_items, csl_registry, llm_model
        )

        machine = AnswerMachine(
            schema_version=self.schema_version,
            query_id=query_id,
            answer=answer_text,
            evidence=[e.to_dict() for e in evidence_items],
        )

        return GenerationOutput(
            schema_version=self.schema_version,
            answer_machine=machine.to_dict(),
            answer_human=human_text,
        )

    # ------------------------------------------------------------------
    # Evidence assembly
    # ------------------------------------------------------------------

    def _build_evidence(
        self,
        ranked_nodes: List[Dict[str, Any]],
        csl_registry: List[Dict[str, Any]],
        merkle_registry: Dict[str, Dict[str, Any]],
        citation_style: str,
    ) -> List[EvidenceItem]:
        csl_by_source: Dict[str, Dict[str, Any]] = {}
        for csl in csl_registry:
            sid = csl.get("_source_id") or csl.get("id", "")
            csl_by_source[sid] = csl

        items: List[EvidenceItem] = []
        for node in ranked_nodes:
            source_id = node.get("source_id", "")
            csl = csl_by_source.get(source_id, {})
            merkle = merkle_registry.get(source_id, {})

            citation_key = self._make_citation_key(csl)
            citation_rendered = self._render_citation(csl, citation_style)
            merkle_root = merkle.get("root", "")
            merkle_proof = self._get_merkle_proof(node, merkle)

            items.append(EvidenceItem(
                node_id=node.get("node_id", ""),
                source_id=source_id,
                sha256=node.get("sha256", ""),
                document_merkle_root=merkle_root,
                merkle_proof=merkle_proof,
                citation_key=citation_key,
                citation_rendered=citation_rendered,
                section_path=node.get("section_path", ""),
                text=node.get("text", ""),
            ))

        return items

    # ------------------------------------------------------------------
    # Answer composition
    # ------------------------------------------------------------------

    def _compose_answer(
        self,
        user_query: str,
        ranked_nodes: List[Dict[str, Any]],
        evidence_items: List[EvidenceItem],
        csl_registry: List[Dict[str, Any]],
        llm_model: Optional[str] = None,
    ) -> tuple:
        """Compose answer from evidence.

        If an LLM model is specified, delegates to the LLM for synthesis.
        Otherwise, produces a deterministic extractive answer.
        """
        if llm_model:
            return self._compose_with_llm(
                user_query, ranked_nodes, evidence_items, llm_model
            )

        return self._compose_extractive(
            user_query, ranked_nodes, evidence_items
        )

    def _compose_extractive(
        self,
        user_query: str,
        ranked_nodes: List[Dict[str, Any]],
        evidence_items: List[EvidenceItem],
    ) -> tuple:
        """Deterministic extractive answer — no LLM needed."""
        # Group evidence by source
        by_source: Dict[str, List[EvidenceItem]] = {}
        for item in evidence_items:
            by_source.setdefault(item.source_id, []).append(item)

        # Machine answer: concatenate evidence texts
        answer_parts: List[str] = []
        for item in evidence_items:
            answer_parts.append(item.text)
        answer_text = "\n\n".join(answer_parts)

        # Human answer: markdown with inline citations
        human_parts: List[str] = [f"## Query: {user_query}\n"]
        for source_id, items in by_source.items():
            for item in items:
                citation = item.citation_rendered or item.citation_key
                human_parts.append(
                    f"> {item.text}\n> — [{citation}] (node: `{item.node_id}`)\n"
                )

        # Evidence appendix
        human_parts.append("\n---\n### Evidence Appendix\n")
        for i, item in enumerate(evidence_items, 1):
            human_parts.append(
                f"{i}. **{item.node_id}** ({item.section_path}) — "
                f"SHA256: `{item.sha256[:16]}…`"
            )

        human_text = "\n".join(human_parts)
        return answer_text, human_text

    def _compose_with_llm(
        self,
        user_query: str,
        ranked_nodes: List[Dict[str, Any]],
        evidence_items: List[EvidenceItem],
        llm_model: str,
    ) -> tuple:
        """Generate answer using LLM with evidence context."""
        try:
            from ..llm import get_llm_model
            import dspy
        except ImportError:
            logger.warning("dspy not available, falling back to extractive answer")
            return self._compose_extractive(user_query, ranked_nodes, evidence_items)

        # Build context from evidence
        context_parts: List[str] = []
        for item in evidence_items:
            citation = item.citation_rendered or item.citation_key
            context_parts.append(
                f"[{item.node_id}] ({citation}):\n{item.text}"
            )
        context = "\n\n---\n\n".join(context_parts)

        # Build prompt
        prompt = (
            f"Based ONLY on the following evidence passages, answer the question.\n"
            f"For every claim, cite the evidence using [Author, Year] format.\n"
            f"If the evidence is insufficient, say so.\n\n"
            f"Evidence:\n{context}\n\n"
            f"Question: {user_query}\n\n"
            f"Answer:"
        )

        try:
            lm = get_llm_model(llm_model, temperature=0.1)
            with dspy.context(lm=lm):
                response = lm(prompt)
                if isinstance(response, list):
                    llm_answer = response[0] if response else ""
                else:
                    llm_answer = str(response)
        except Exception:
            logger.warning("LLM generation failed, falling back to extractive", exc_info=True)
            return self._compose_extractive(user_query, ranked_nodes, evidence_items)

        # Build human-readable output
        human_parts = [
            f"## Query: {user_query}\n",
            llm_answer,
            "\n---\n### Evidence Appendix\n",
        ]
        for i, item in enumerate(evidence_items, 1):
            citation = item.citation_rendered or item.citation_key
            human_parts.append(
                f"{i}. **{item.node_id}** ({item.section_path}) — "
                f"[{citation}] SHA256: `{item.sha256[:16]}…`"
            )

        return llm_answer, "\n".join(human_parts)

    # ------------------------------------------------------------------
    # Citation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_citation_key(csl: Dict[str, Any]) -> str:
        """Build a citation key like 'AuthorYear' from CSL data."""
        authors = csl.get("author", [])
        first_author = ""
        if authors:
            first_author = authors[0].get("family", "") or authors[0].get("given", "")

        issued = csl.get("issued", {})
        date_parts = issued.get("date-parts", [[]])
        year = ""
        if date_parts and date_parts[0]:
            year = str(date_parts[0][0])

        if first_author and year:
            return f"{first_author}{year}"
        if first_author:
            return first_author
        title = csl.get("title", "")
        if title:
            return title[:30]
        return csl.get("id", "unknown")

    @staticmethod
    def _render_citation(csl: Dict[str, Any], style_name: str) -> str:
        """Render a single CSL record using citeproc-py."""
        if not csl.get("title"):
            return ""
        try:
            from ..citation_style import format_bibliography
            csl_copy = dict(csl)
            # Remove internal fields
            csl_copy.pop("_source_id", None)
            csl_copy.pop("_extraction_method", None)
            csl_copy.pop("content_hash", None)
            csl_copy.pop("merkle_root", None)
            csl_copy.pop("source_type", None)
            csl_copy.pop("ingestion_timestamp", None)

            # Ensure id is present
            if "id" not in csl_copy:
                csl_copy["id"] = "item1"
            if "type" not in csl_copy:
                csl_copy["type"] = "article"

            bib, inline = format_bibliography([csl_copy], style_name)
            if inline:
                return inline
            if bib and not bib.startswith("Error"):
                return bib.strip()
        except Exception:
            logger.debug("citeproc rendering failed", exc_info=True)

        # Fallback: manual Chicago author-date
        authors = csl.get("author", [])
        author_str = ""
        if authors:
            first = authors[0]
            author_str = first.get("family", first.get("given", ""))
        issued = csl.get("issued", {})
        date_parts = issued.get("date-parts", [[]])
        year = ""
        if date_parts and date_parts[0]:
            year = str(date_parts[0][0])

        if author_str and year:
            return f"({author_str} {year})"
        if author_str:
            return f"({author_str})"
        return f"({csl.get('title', 'Unknown')[:40]})"

    @staticmethod
    def _get_merkle_proof(
        node: Dict[str, Any], merkle: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """Extract or build Merkle proof for a node."""
        levels = merkle.get("levels")
        if not levels:
            return []

        node_hash = node.get("sha256", "")
        if not node_hash:
            return []

        # Find leaf index
        leaves = levels[0] if levels else []
        try:
            leaf_index = leaves.index(node_hash)
        except ValueError:
            return []

        # Build proof path
        from ..ingestion.deterministic import build_merkle_proof
        return build_merkle_proof(merkle, leaf_index)
