"""
CiteIndex — AI research knowledge infrastructure.
"""

__version__ = "0.11.0"
__all__ = [
    "CiteIndexIngestionOrchestrator",
    "CitationExtractor",
    "CitationLLM",
    "format_bibliography",
]


def __getattr__(name):
    if name == "CiteIndexIngestionOrchestrator":
        from .ingestion import CiteIndexIngestionOrchestrator

        return CiteIndexIngestionOrchestrator
    if name == "CitationExtractor":
        from .main import CitationExtractor

        return CitationExtractor
    if name == "CitationLLM":
        from .model import CitationLLM

        return CitationLLM
    if name == "format_bibliography":
        from .citation_style import format_bibliography

        return format_bibliography
    raise AttributeError(f"module 'citeindex' has no attribute {name!r}")
