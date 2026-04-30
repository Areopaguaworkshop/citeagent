"""Load ingested corpus artifacts for the agent pipeline.

Walks ``corpus/`` and loads all ``csl.json``, ``document.json``,
``merkle.json``, and ``index.json`` files that were produced by Tier 1
ingestion.  Provides a unified view consumed by the indexing, retrieval,
and generation agents.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class CorpusLoader:
    """Scan a corpus root and materialise registries for the agent layer."""

    def __init__(self, corpus_root: str = "corpus") -> None:
        self.corpus_root = os.path.abspath(corpus_root)
        # Populated by load()
        self.sources: List[Dict[str, Any]] = []
        self.all_nodes: List[Dict[str, Any]] = []
        self.csl_registry: List[Dict[str, Any]] = []
        self.merkle_registry: Dict[str, Dict[str, Any]] = {}  # source_id → merkle
        self.retrieval_indices: Dict[str, Dict[str, Any]] = {}  # source_id → index

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Walk corpus root and load all ingested sources."""
        if not os.path.isdir(self.corpus_root):
            logger.warning("Corpus root does not exist: %s", self.corpus_root)
            return

        for entry in sorted(os.listdir(self.corpus_root)):
            doc_dir = os.path.join(self.corpus_root, entry)
            if not os.path.isdir(doc_dir):
                continue
            self._load_source(doc_dir, entry)

        logger.info(
            "Corpus loaded: %d sources, %d nodes, %d CSL records",
            len(self.sources),
            len(self.all_nodes),
            len(self.csl_registry),
        )

    def get_nodes_by_source(self, source_id: str) -> List[Dict[str, Any]]:
        return [n for n in self.all_nodes if n.get("source_id") == source_id]

    def get_csl_by_id(self, csl_id: str) -> Optional[Dict[str, Any]]:
        for csl in self.csl_registry:
            if csl.get("id") == csl_id:
                return csl
        return None

    def get_csl_by_source(self, source_id: str) -> Optional[Dict[str, Any]]:
        for csl in self.csl_registry:
            if csl.get("_source_id") == source_id:
                return csl
        return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_source(self, doc_dir: str, doc_hash: str) -> None:
        csl = self._read_json(os.path.join(doc_dir, "csl.json"))
        document = self._read_json(os.path.join(doc_dir, "document.json"))
        merkle = self._read_json(os.path.join(doc_dir, "merkle.json"))
        index = self._read_json(os.path.join(doc_dir, "index.json"))

        if csl is None:
            return

        source_id = csl.get("id", doc_hash)

        source_record = {
            "source_id": source_id,
            "doc_hash": doc_hash,
            "doc_dir": doc_dir,
            "csl": csl,
        }
        self.sources.append(source_record)

        # CSL registry — tag with source_id for lookups
        csl_copy = dict(csl)
        csl_copy["_source_id"] = source_id
        self.csl_registry.append(csl_copy)

        # Nodes from document structure
        if document:
            nodes = self._extract_nodes_from_document(document, source_id)
            self.all_nodes.extend(nodes)

        # Merkle tree
        if merkle:
            self.merkle_registry[source_id] = merkle

        # Retrieval index
        if index:
            self.retrieval_indices[source_id] = index

    def _extract_nodes_from_document(
        self, document: Dict[str, Any], source_id: str
    ) -> List[Dict[str, Any]]:
        """Extract flat node list from the hierarchical document structure."""
        # Check for pre-built nodes (from URL ingestion or digital_pdf pipeline)
        if document.get("nodes"):
            return document["nodes"]

        nodes: List[Dict[str, Any]] = []
        for page in document.get("pages", []):
            page_number = page.get("page_number", 0)

            # Handle layout-based structure (columns)
            columns = page.get("columns", [])
            if columns:
                for col in columns:
                    for para in col.get("paragraphs", []):
                        self._add_paragraph_node(nodes, para, source_id, page_number)
            # Handle flat paragraph structure
            else:
                for para in page.get("paragraphs", []):
                    self._add_paragraph_node(nodes, para, source_id, page_number)

            # Footnotes
            for fn in page.get("footnotes", []):
                if isinstance(fn, dict) and fn.get("text"):
                    from ..ingestion.deterministic import canonicalize_text, sha256_hex
                    text = canonicalize_text(fn["text"])
                    text_hash = sha256_hex(text)
                    nodes.append({
                        "node_id": f"{source_id}:p{page_number}:fn:{text_hash[:8]}",
                        "source_id": source_id,
                        "section_path": f"p{page_number}",
                        "text": text,
                        "sha256": text_hash,
                        "page": page_number,
                        "is_footnote": True,
                    })

        return nodes

    def _add_paragraph_node(
        self,
        nodes: List[Dict[str, Any]],
        para: Dict[str, Any],
        source_id: str,
        page_number: int,
    ) -> None:
        from ..ingestion.deterministic import canonicalize_text, sha256_hex

        text = para.get("text", "")
        if not text.strip():
            return
        text = canonicalize_text(text)
        text_hash = sha256_hex(text)
        para_id = para.get("paragraph_id", f"p{page_number}_unk")
        node_id = f"{source_id}:p{page_number}:{para_id}:{text_hash[:8]}"
        nodes.append({
            "node_id": node_id,
            "source_id": source_id,
            "section_path": f"p{page_number}",
            "text": text,
            "sha256": text_hash,
            "page": page_number,
        })

    @staticmethod
    def _read_json(path: str) -> Optional[Dict[str, Any]]:
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            logger.warning("Failed to read %s", path, exc_info=True)
            return None
