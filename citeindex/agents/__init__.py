"""CiteIndex Agent & Retrieval Layer (Tier 2).

Deterministic 7-agent pipeline: indexing → query planning → retrieval →
clarification → generation → integrity verification.
"""

__all__ = [
    "CorpusLoader",
    "IndexingAgent",
    "QueryPlanner",
    "RetrievalAgent",
    "ClarificationAgent",
    "GenerationAgent",
    "IntegrityVerifier",
    "ChatPipeline",
]


def __getattr__(name):
    if name == "CorpusLoader":
        from .corpus_loader import CorpusLoader
        return CorpusLoader
    if name == "IndexingAgent":
        from .indexing import IndexingAgent
        return IndexingAgent
    if name == "QueryPlanner":
        from .query_planner import QueryPlanner
        return QueryPlanner
    if name == "RetrievalAgent":
        from .retrieval import RetrievalAgent
        return RetrievalAgent
    if name == "ClarificationAgent":
        from .clarification import ClarificationAgent
        return ClarificationAgent
    if name == "GenerationAgent":
        from .generation import GenerationAgent
        return GenerationAgent
    if name == "IntegrityVerifier":
        from .integrity import IntegrityVerifier
        return IntegrityVerifier
    if name == "ChatPipeline":
        from .chat import ChatPipeline
        return ChatPipeline
    raise AttributeError(f"module 'citeindex.agents' has no attribute {name!r}")
