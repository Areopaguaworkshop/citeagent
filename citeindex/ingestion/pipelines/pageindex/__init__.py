"""
Vendored PageIndex (VectifyAI/PageIndex) — local-only, no external API.

Configured to use ollama/qwen3.5:cloud via litellm.
"""
from .page_index import page_index_main, page_index
from .page_index_md import md_to_tree
from .retrieve import get_document, get_document_structure, get_page_content
