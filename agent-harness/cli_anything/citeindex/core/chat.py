"""Chat commands — ask, interactive."""
from __future__ import annotations

from typing import Any, Dict

from ..utils.citeindex_backend import CiteIndexBackend


_backend = CiteIndexBackend()


def chat_ask(
    prompt: str,
    corpus_root: str = "corpus",
    llm_model: str = "ollama/qwen3",
    thread_id: str = "default",
    schema_version: str = "1.0.0",
) -> Dict[str, Any]:
    """Single-shot chat with trace-bound citations."""
    return _backend.chat(
        prompt=prompt,
        corpus_root=corpus_root,
        llm_model=llm_model,
        thread_id=thread_id,
        schema_version=schema_version,
    )