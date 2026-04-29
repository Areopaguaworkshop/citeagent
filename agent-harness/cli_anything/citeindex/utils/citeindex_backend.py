"""Backend wrapper for CiteIndex — single point of contact with the citeindex library."""
from __future__ import annotations

import os
import shutil
from typing import Any, Dict, List, Optional


class CiteIndexBackend:
    """Thin wrapper over the citeindex Python API."""

    @staticmethod
    def check_dependencies() -> Dict[str, Any]:
        """Check if citeindex and system tools are available."""
        result: Dict[str, Any] = {"available": True, "checks": {}}

        try:
            import citeindex
            result["checks"]["citeindex"] = {"available": True, "version": getattr(citeindex, "__version__", "unknown")}
        except ImportError:
            result["checks"]["citeindex"] = {
                "available": False,
                "message": "citeindex not installed. Run: pip install citeindex",
            }
            result["available"] = False

        for tool in ["tesseract", "ffmpeg", "ollama"]:
            path = shutil.which(tool)
            result["checks"][tool] = {"available": path is not None, "path": path}

        return result

    def ingest(self, input_ref: str, corpus_root: str = "corpus",
               llm_model: str = "ollama/qwen3",
               text_direction: str = "horizontal",
               vertical_lang: str = "ch",
               lang: str = "auto",
               page_range: str = "1-5, -3",
               doc_type_override: Optional[str] = None,
               use_layout_analysis: bool = True,
               is_primary: bool = False,
               use_pageindex: bool = False,
               pageindex_model: str = "ollama/qwen3.5:cloud",
               schema_version: str = "1.0.0",
               ) -> Dict[str, Any]:
        """Ingest a document into the corpus."""
        from citeindex.ingestion import CiteIndexIngestionOrchestrator
        from citeindex.ingestion.models import IngestionConfig

        config = IngestionConfig(
            llm_model=llm_model,
            text_direction=text_direction,
            vertical_lang=vertical_lang,
            lang=lang,
            page_range=page_range,
            doc_type_override=doc_type_override,
            use_layout_analysis=use_layout_analysis,
            is_primary=is_primary,
            use_pageindex=use_pageindex,
            pageindex_model=pageindex_model,
        )
        orchestrator = CiteIndexIngestionOrchestrator(
            corpus_root=corpus_root,
            schema_version=schema_version,
        )
        return orchestrator.ingest(input_ref, config=config)

    def ingest_all_urls(self, root_url: str, corpus_root: str = "corpus",
                        llm_model: str = "ollama/qwen3",
                        update: bool = False,
                        max_depth: int = 2,
                        max_pages: int = 100,
                        schema_version: str = "1.0.0",
                        **ingest_kwargs: Any,
                        ) -> Dict[str, Any]:
        """Crawl and ingest all article pages from a URL."""
        from citeindex.ingestion import CiteIndexIngestionOrchestrator
        from citeindex.ingestion.models import IngestionConfig

        config = IngestionConfig(llm_model=llm_model, **ingest_kwargs)
        orchestrator = CiteIndexIngestionOrchestrator(
            corpus_root=corpus_root,
            schema_version=schema_version,
        )
        return orchestrator.ingest_all_urls(
            root_url=root_url,
            config=config,
            update=update,
            max_depth=max_depth,
            max_pages=max_pages,
        )

    def search(self, query: str, corpus_root: str = "corpus",
               top_k: int = 20,
               cite_style: str = "chicago-author-date",
               retrieval: str = "auto",
               pageindex_model: str = "ollama/qwen3.5:cloud",
               schema_version: str = "1.0.0",
               ) -> Dict[str, Any]:
        """Search the corpus using BM25 or PageIndex retrieval."""
        from citeindex.agents.chat import SearchPipeline

        pipeline = SearchPipeline(
            corpus_root=corpus_root,
            schema_version=schema_version,
        )
        return pipeline.search(
            query=query,
            top_k=top_k,
            cite_style=cite_style,
            retrieval=retrieval,
            pageindex_model=pageindex_model,
        )

    def chat(self, prompt: str, corpus_root: str = "corpus",
             llm_model: str = "ollama/qwen3",
             thread_id: str = "default",
             schema_version: str = "1.0.0",
             ) -> Dict[str, Any]:
        """Chat with trace-bound citations."""
        from citeindex.agents.chat import ChatPipeline

        pipeline = ChatPipeline(
            corpus_root=corpus_root,
            llm_model=llm_model,
            schema_version=schema_version,
        )
        return pipeline.chat(prompt, thread_id=thread_id)

    def memory_search(self, query: str, corpus_root: str = "corpus",
                      thread_id: Optional[str] = None,
                      ) -> List[Dict[str, Any]]:
        """Search past chat memory."""
        from citeindex.agents.memory import MemoryStore

        store = MemoryStore(memory_dir=f"{corpus_root}/.memory")
        results = store.search(query, thread_id=thread_id)
        return [e.to_dict() for e in results[:20]]

    def memory_list_threads(self, corpus_root: str = "corpus") -> List[str]:
        """List all memory threads."""
        from citeindex.agents.memory import MemoryStore

        store = MemoryStore(memory_dir=f"{corpus_root}/.memory")
        return store._list_threads()

    def format_bibliography(self, csl_json_data: List[Dict[str, Any]],
                            style_name: str = "chicago-author-date",
                            ) -> Dict[str, Any]:
        """Format a bibliography from CSL-JSON data."""
        from citeindex.citation_style import format_bibliography as _format_bib

        bib_str, in_text_str = _format_bib(csl_json_data, style_name)
        return {"bibliography": bib_str, "in_text": in_text_str, "style": style_name}

    def corpus_info(self, corpus_root: str = "corpus") -> Dict[str, Any]:
        """Get information about a corpus."""
        if not os.path.isdir(corpus_root):
            return {"exists": False, "path": corpus_root}

        documents = []
        citeindex_dir = os.path.join(corpus_root, ".citeindex")
        legacy_dirs = []

        if os.path.isdir(citeindex_dir):
            structured_dir = os.path.join(citeindex_dir, "documents", "structured")
            if os.path.isdir(structured_dir):
                for f in os.listdir(structured_dir):
                    if f.endswith(".citeindex.json"):
                        documents.append(f.replace(".citeindex.json", ""))

        for entry in sorted(os.listdir(corpus_root)):
            entry_path = os.path.join(corpus_root, entry)
            if os.path.isdir(entry_path) and not entry.startswith("."):
                csl_path = os.path.join(entry_path, "csl.json")
                if os.path.isfile(csl_path):
                    legacy_dirs.append(entry)

        return {
            "exists": True,
            "path": os.path.abspath(corpus_root),
            "document_count": len(documents) + len(legacy_dirs),
            "v12_documents": documents,
            "legacy_documents": legacy_dirs,
            "has_citeindex_store": os.path.isdir(citeindex_dir),
        }

    def corpus_validate(self, corpus_root: str = "corpus") -> Dict[str, Any]:
        """Validate a corpus structure."""
        info = self.corpus_info(corpus_root)
        if not info.get("exists"):
            return {"valid": False, "errors": ["Corpus directory does not exist"]}

        errors = []
        warnings = []

        if info["document_count"] == 0:
            warnings.append("No documents in corpus")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "document_count": info["document_count"],
        }
