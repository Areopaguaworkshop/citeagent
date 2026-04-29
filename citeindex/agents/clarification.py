"""Clarification Agent — resolve blocking ambiguity before retrieval.

Matches ``.agent/agent/clarification.md`` and skill ``clarification-handler.yaml``.

Max 3 questions.  Only asks when ambiguity blocks deterministic retrieval.
"""

import logging
from typing import Any, Dict, List, Optional

from .models import ClarificationPacket, SCHEMA_VERSION

logger = logging.getLogger(__name__)


class ClarificationAgent:
    """Convert planner uncertainty into concise clarification questions."""

    def __init__(self, schema_version: str = SCHEMA_VERSION) -> None:
        self.schema_version = schema_version

    def check(
        self,
        query_plan: Dict[str, Any],
        dialog_state: Optional[Dict[str, Any]] = None,
    ) -> ClarificationPacket:
        """Check if clarification is needed and produce questions if so."""
        query_id = query_plan.get("query_id", "")
        clarification_required = query_plan.get("clarification_required", False)
        existing_questions = query_plan.get("clarification_questions", [])

        if not clarification_required:
            return ClarificationPacket(
                schema_version=self.schema_version,
                query_id=query_id,
                needs_user_input=False,
                resolved_plan=query_plan,
            )

        # Generate clarification questions (max 3)
        questions = existing_questions[:3] if existing_questions else []

        if not questions:
            questions = self._generate_questions(query_plan)

        return ClarificationPacket(
            schema_version=self.schema_version,
            query_id=query_id,
            needs_user_input=True,
            questions=questions[:3],
            resolved_plan=None,
        )

    def resolve(
        self,
        query_plan: Dict[str, Any],
        user_answers: Dict[str, str],
    ) -> ClarificationPacket:
        """Apply user answers to the query plan and resolve ambiguity."""
        query_id = query_plan.get("query_id", "")
        resolved = dict(query_plan)
        constraint_updates: Dict[str, Any] = {}

        for question_key, answer in user_answers.items():
            answer_stripped = answer.strip()
            if not answer_stripped:
                continue

            # Apply answer as additional search terms or filters
            if question_key == "scope":
                resolved.setdefault("must_filters", []).append({
                    "field": "source_id",
                    "value": answer_stripped,
                })
                constraint_updates["scope"] = answer_stripped
            elif question_key == "time_range":
                resolved.setdefault("must_filters", []).append({
                    "field": "issued.date-parts",
                    "value": answer_stripped,
                })
                constraint_updates["time_range"] = answer_stripped
            else:
                # Default: treat as additional search terms
                from .indexing import tokenize
                extra_terms = tokenize(answer_stripped)
                resolved.setdefault("search_terms", []).extend(extra_terms)
                constraint_updates[question_key] = answer_stripped

        resolved["clarification_required"] = False
        resolved["clarification_questions"] = []

        return ClarificationPacket(
            schema_version=self.schema_version,
            query_id=query_id,
            needs_user_input=False,
            constraint_updates=constraint_updates,
            resolved_plan=resolved,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_questions(query_plan: Dict[str, Any]) -> List[str]:
        """Generate clarification questions based on missing constraints."""
        questions: List[str] = []

        search_terms = query_plan.get("search_terms", [])
        exact_phrases = query_plan.get("exact_phrases", [])

        if not search_terms and not exact_phrases:
            questions.append(
                "Your query has no identifiable search terms. "
                "Could you provide specific keywords or a topic?"
            )

        must_filters = query_plan.get("must_filters", [])
        has_scope = any(f.get("field") == "source_id" for f in must_filters)
        if not has_scope and len(search_terms) < 2:
            questions.append(
                "Would you like to restrict the search to a specific source or document?"
            )

        has_time = any(f.get("field") == "issued.date-parts" for f in must_filters)
        if not has_time:
            questions.append(
                "Do you want to restrict results to a particular time period?"
            )

        return questions[:3]
