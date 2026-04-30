"""Tantivy full-text indexes for CiteAgent (document, claim, memory).

Follows the v12 contract: instruction/contracts/S4_tantivy_index_schemas.md
"""

import os
from typing import Any

import tantivy


def _document_schema() -> tantivy.Schema:
    builder = tantivy.SchemaBuilder()
    builder.add_text_field("doc_id", stored=True, tokenizer_name="raw")
    builder.add_text_field("title", stored=True, tokenizer_name="default")
    builder.add_text_field("author", stored=True, tokenizer_name="default")
    builder.add_text_field("body", stored=False, tokenizer_name="default")
    builder.add_text_field("source_type", stored=True, tokenizer_name="raw")
    builder.add_text_field("language", stored=True, tokenizer_name="raw")
    builder.add_text_field("merkle_root", stored=True, tokenizer_name="raw")
    builder.add_text_field("citation_key", stored=True, tokenizer_name="raw")
    builder.add_text_field("doi", stored=True, tokenizer_name="raw")
    builder.add_text_field("abstract", stored=False, tokenizer_name="default")
    return builder.build()


def _claim_schema() -> tantivy.Schema:
    builder = tantivy.SchemaBuilder()
    builder.add_text_field("claim_id", stored=True, tokenizer_name="raw")
    builder.add_text_field("doc_id", stored=True, tokenizer_name="raw")
    builder.add_text_field("claim_text", stored=True, tokenizer_name="default")
    builder.add_text_field("polarity_tag", stored=True, tokenizer_name="raw")
    builder.add_text_field("hierarchy_path", stored=True, tokenizer_name="raw")
    return builder.build()


def _memory_schema() -> tantivy.Schema:
    builder = tantivy.SchemaBuilder()
    builder.add_text_field("memory_id", stored=True, tokenizer_name="raw")
    builder.add_text_field("content", stored=True, tokenizer_name="default")
    builder.add_text_field("thread_id", stored=True, tokenizer_name="raw")
    builder.add_text_field("tier", stored=True, tokenizer_name="raw")
    builder.add_text_field("sha256", stored=True, tokenizer_name="raw")
    return builder.build()


class TantivyManager:
    """Manages the 3 Tantivy indexes for CiteAgent."""

    def __init__(self, corpus_root: str):
        self.corpus_root = corpus_root
        index_dir = os.path.join(corpus_root, ".citeindex", "indexes")
        doc_index_path = os.path.join(index_dir, "document_index")
        claim_index_path = os.path.join(index_dir, "claim_index")
        memory_index_path = os.path.join(index_dir, "memory_index")
        os.makedirs(doc_index_path, exist_ok=True)
        os.makedirs(claim_index_path, exist_ok=True)
        os.makedirs(memory_index_path, exist_ok=True)

        self.doc_index = tantivy.Index(_document_schema(), doc_index_path)
        self.claim_index = tantivy.Index(_claim_schema(), claim_index_path)
        self.memory_index = tantivy.Index(_memory_schema(), memory_index_path)

    def _get_writer(self, idx: tantivy.Index) -> tantivy.IndexWriter:
        return idx.writer()

    def index_document(self, doc_data: dict[str, Any]) -> str:
        """Add a document to the document index."""
        writer = self._get_writer(self.doc_index)
        try:
            doc = tantivy.Document()
            doc.add_text("doc_id", str(doc_data.get("id", "")))
            doc.add_text("title", str(doc_data.get("title", "")))
            author_str = " ".join(
                f"{a.get('given', '')} {a.get('family', '')}".strip()
                for a in doc_data.get("author", [])
                if isinstance(a, dict)
            ) if doc_data.get("author") else ""
            doc.add_text("author", author_str)
            doc.add_text("abstract", str(doc_data.get("abstract", "")))
            doc.add_text("source_type", str(doc_data.get("ci_source_type", "")))
            doc.add_text("language", str(doc_data.get("language", "en")))
            doc.add_text("merkle_root", str(doc_data.get("ci_merkle_root", "")))
            doc.add_text("citation_key", str(doc_data.get("id", "")))
            doc.add_text("doi", str(doc_data.get("DOI", "")))
            writer.add_document(doc)
            writer.commit()
            return str(doc_data.get("id", ""))
        finally:
            writer.wait_merging_threads()

    def index_claim(self, claim_data: dict[str, Any]) -> str:
        """Add a claim to the claim index."""
        writer = self._get_writer(self.claim_index)
        try:
            doc = tantivy.Document()
            doc.add_text("claim_id", str(claim_data.get("claim_id", "")))
            doc.add_text("doc_id", str(claim_data.get("source_id", "")))
            doc.add_text("claim_text", str(claim_data.get("claim_text", "")))
            doc.add_text("polarity_tag", str(claim_data.get("polarity_tag", "neutral")))
            doc.add_text("hierarchy_path", str(claim_data.get("hierarchy_path", "/")))
            writer.add_document(doc)
            writer.commit()
            return str(claim_data.get("claim_id", ""))
        finally:
            writer.wait_merging_threads()

    def index_memory(self, memory_data: dict[str, Any]) -> str:
        """Add a memory entry to the memory index."""
        writer = self._get_writer(self.memory_index)
        try:
            doc = tantivy.Document()
            doc.add_text("memory_id", str(memory_data.get("entry_id", "")))
            doc.add_text("content", str(memory_data.get("content", "")))
            doc.add_text("thread_id", str(memory_data.get("thread_id", "default")))
            doc.add_text("tier", str(memory_data.get("tier", "episodic")))
            doc.add_text("sha256", str(memory_data.get("sha256", "")))
            writer.add_document(doc)
            writer.commit()
            return str(memory_data.get("entry_id", ""))
        finally:
            writer.wait_merging_threads()

    def search_documents(self, query: str, limit: int = 10) -> list[dict]:
        """Search the document index."""
        self.doc_index.reload()
        searcher = self.doc_index.searcher()
        query_obj = self.doc_index.parse_query(query, ["title", "abstract", "body", "author"])
        results = searcher.search(query_obj, limit)
        hits = []
        for score, doc_addr in results.hits:
            doc = searcher.doc(doc_addr)
            hits.append({
                "doc_id": doc.get_first("doc_id") or "",
                "title": doc.get_first("title") or "",
                "author": doc.get_first("author") or "",
                "score": score,
            })
        return hits

    def search_claims(self, query: str, limit: int = 10) -> list[dict]:
        """Search the claim index."""
        self.claim_index.reload()
        searcher = self.claim_index.searcher()
        query_obj = self.claim_index.parse_query(query, ["claim_text"])
        results = searcher.search(query_obj, limit)
        hits = []
        for score, doc_addr in results.hits:
            doc = searcher.doc(doc_addr)
            hits.append({
                "claim_id": doc.get_first("claim_id") or "",
                "claim_text": doc.get_first("claim_text") or "",
                "doc_id": doc.get_first("doc_id") or "",
                "score": score,
            })
        return hits

    def search_memory(self, query: str, limit: int = 10) -> list[dict]:
        """Search the memory index."""
        self.memory_index.reload()
        searcher = self.memory_index.searcher()
        query_obj = self.memory_index.parse_query(query, ["content"])
        results = searcher.search(query_obj, limit)
        hits = []
        for score, doc_addr in results.hits:
            doc = searcher.doc(doc_addr)
            hits.append({
                "memory_id": doc.get_first("memory_id") or "",
                "content": doc.get_first("content") or "",
                "score": score,
            })
        return hits

    def rebuild_from_corpus(self) -> dict[str, int]:
        """Rebuild all indexes from corpus directory. Returns counts."""
        from citeagent.agents.corpus_loader import CorpusLoader
        loader = CorpusLoader(corpus_root=self.corpus_root)
        loader.load()

        doc_count = 0
        claim_count = 0

        for source_id, csl in loader.csl_registry.items():
            self.index_document(csl)
            doc_count += 1

        for node in loader.all_nodes:
            self.index_claim({
                "claim_id": node.get("node_id", ""),
                "source_id": node.get("source_id", ""),
                "claim_text": node.get("text", ""),
                "polarity_tag": "neutral",
            })
            claim_count += 1

        return {"documents_indexed": doc_count, "claims_indexed": claim_count}