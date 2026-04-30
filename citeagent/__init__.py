"""
CiteAgent — AI research agent for academic scholars.

Ingestion is handled by the separate `citeindex` package (pip install citeindex).
This package provides search, retrieval, chat, integrity verification,
memory, and agent runtime capabilities.
"""

__version__ = "0.4.0"
__all__ = [
    "SearchPipeline",
    "ChatPipeline",
    "IntegrityVerifier",
]


def __getattr__(name):
    if name == "SearchPipeline":
        from .agents.chat import SearchPipeline
        return SearchPipeline
    if name == "ChatPipeline":
        from .agents.chat import ChatPipeline
        return ChatPipeline
    if name == "IntegrityVerifier":
        from .agents.integrity import IntegrityVerifier
        return IntegrityVerifier
    raise AttributeError(f"module 'citeagent' has no attribute {name!r}")