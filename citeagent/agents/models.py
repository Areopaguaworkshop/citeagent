"""Dataclasses for Tier 2 agent I/O boundaries."""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


SCHEMA_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Query Planner
# ---------------------------------------------------------------------------

@dataclass
class QueryPlan:
    schema_version: str = SCHEMA_VERSION
    query_id: str = ""
    intent_type: str = "fact"  # fact | comparison | timeline | definition | citation_lookup
    must_filters: List[Dict[str, Any]] = field(default_factory=list)
    should_filters: List[Dict[str, Any]] = field(default_factory=list)
    search_terms: List[str] = field(default_factory=list)
    exact_phrases: List[str] = field(default_factory=list)
    section_targets: List[str] = field(default_factory=list)
    retrieval_policy: str = "metadata_filter -> bm25 -> trace_filter"
    clarification_required: bool = False
    clarification_questions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------

@dataclass
class IndexingReport:
    schema_version: str = SCHEMA_VERSION
    tokenizer_version: str = "simple_v1"
    total_nodes: int = 0
    total_tokens: int = 0
    total_sources: int = 0
    cross_source_links: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class IndexingOutput:
    schema_version: str = SCHEMA_VERSION
    inverted_index: Dict[str, Any] = field(default_factory=dict)
    section_index: Dict[str, Any] = field(default_factory=dict)
    cross_source_links: List[Dict[str, Any]] = field(default_factory=list)
    indexing_report: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

@dataclass
class ScoredNode:
    node_id: str = ""
    source_id: str = ""
    section_path: str = ""
    sha256: str = ""
    text: str = ""
    page: Optional[int] = None
    score_breakdown: Dict[str, float] = field(default_factory=dict)
    total_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RetrievalResult:
    schema_version: str = SCHEMA_VERSION
    query_id: str = ""
    ranked_nodes: List[Dict[str, Any]] = field(default_factory=list)
    candidate_relations: List[Dict[str, Any]] = field(default_factory=list)
    retrieval_debug: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Clarification
# ---------------------------------------------------------------------------

@dataclass
class ClarificationPacket:
    schema_version: str = SCHEMA_VERSION
    query_id: str = ""
    needs_user_input: bool = False
    questions: List[str] = field(default_factory=list)
    constraint_updates: Dict[str, Any] = field(default_factory=dict)
    resolved_plan: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

@dataclass
class EvidenceItem:
    node_id: str = ""
    source_id: str = ""
    sha256: str = ""
    document_merkle_root: str = ""
    merkle_proof: List[Dict[str, str]] = field(default_factory=list)
    citation_key: str = ""
    citation_rendered: str = ""
    section_path: str = ""
    text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AnswerMachine:
    schema_version: str = SCHEMA_VERSION
    query_id: str = ""
    answer: str = ""
    evidence: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GenerationOutput:
    schema_version: str = SCHEMA_VERSION
    answer_machine: Dict[str, Any] = field(default_factory=dict)
    answer_human: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Integrity
# ---------------------------------------------------------------------------

@dataclass
class IntegrityCheck:
    check_type: str = ""
    node_id: str = ""
    passed: bool = False
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class IntegrityReport:
    schema_version: str = SCHEMA_VERSION
    status: str = "rejected"  # approved | rejected | needs_clarification
    checks: List[Dict[str, Any]] = field(default_factory=list)
    violations: List[str] = field(default_factory=list)
    approved_answer_ref: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

@dataclass
class MemoryEntry:
    entry_id: str = ""
    timestamp: str = ""
    thread_id: str = "default"
    query: str = ""
    response: str = ""
    evidence_node_ids: List[str] = field(default_factory=list)
    sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
