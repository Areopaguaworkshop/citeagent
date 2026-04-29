"""Chat Pipeline — deterministic retrieval + LLM generation + memory.

Matches ``.agent/pipeline/chat_mode.yaml``.

Flow: receive prompt → deterministic retrieval → assemble context →
      call LLM → save memory → output response.
"""

import logging
from typing import Any, Dict, List, Optional

from .models import SCHEMA_VERSION

logger = logging.getLogger(__name__)


class ChatPipeline:
    """End-to-end chat pipeline with retrieval-augmented generation."""

    def __init__(
        self,
        corpus_root: str = "corpus",
        llm_model: str = "ollama/qwen3",
        schema_version: str = SCHEMA_VERSION,
    ) -> None:
        self.corpus_root = corpus_root
        self.llm_model = llm_model
        self.schema_version = schema_version

    def chat(
        self,
        prompt: str,
        thread_id: str = "default",
    ) -> Dict[str, Any]:
        """Run the full chat pipeline for a single prompt."""
        from .corpus_loader import CorpusLoader
        from .indexing import IndexingAgent
        from .query_planner import QueryPlanner
        from .retrieval import RetrievalAgent
        from .clarification import ClarificationAgent
        from .generation import GenerationAgent
        from .integrity import IntegrityVerifier
        from .memory import MemoryStore

        # Step 1: Load corpus
        loader = CorpusLoader(self.corpus_root)
        loader.load()

        if not loader.all_nodes:
            return {
                "status": "no_corpus",
                "message": "No ingested documents found in corpus. Run `citeindex ingest` first.",
                "thread": thread_id,
            }

        # Step 2: Build indexes
        indexer = IndexingAgent(self.schema_version)
        index_output = indexer.run(loader.all_nodes)

        # Step 3: Plan query
        planner = QueryPlanner(self.schema_version)
        query_plan = planner.plan(
            prompt,
            csl_registry=loader.csl_registry,
        )

        # Step 4: Check clarification
        clarifier = ClarificationAgent(self.schema_version)
        clarification = clarifier.check(query_plan.to_dict())

        if clarification.needs_user_input:
            return {
                "status": "needs_clarification",
                "query_id": query_plan.query_id,
                "questions": clarification.questions,
                "thread": thread_id,
            }

        resolved_plan = clarification.resolved_plan or query_plan.to_dict()

        # Step 5: Retrieve evidence
        retriever = RetrievalAgent(self.schema_version)
        retrieval_result = retriever.run(
            resolved_plan,
            loader.all_nodes,
            index_output.inverted_index,
            loader.csl_registry,
        )

        # Step 6: Generate answer
        generator = GenerationAgent(self.schema_version)
        gen_output = generator.generate(
            query_id=query_plan.query_id,
            user_query=prompt,
            retrieval_result=retrieval_result.to_dict(),
            csl_registry=loader.csl_registry,
            merkle_registry=loader.merkle_registry,
            llm_model=self.llm_model,
        )

        # Step 7: Integrity check
        verifier = IntegrityVerifier(self.schema_version)
        integrity = verifier.verify(
            gen_output.answer_machine,
            loader.all_nodes,
            loader.merkle_registry,
            loader.csl_registry,
        )

        # Step 8: Save memory
        memory = MemoryStore(memory_dir=f"{self.corpus_root}/.memory")
        evidence_ids = [
            e.get("node_id", "") for e in gen_output.answer_machine.get("evidence", [])
        ]
        memory.save(
            thread_id=thread_id,
            query=prompt,
            response=gen_output.answer_human,
            evidence_node_ids=evidence_ids,
        )

        return {
            "status": "ok",
            "thread": thread_id,
            "query_id": query_plan.query_id,
            "answer_human": gen_output.answer_human,
            "answer_machine": gen_output.answer_machine,
            "integrity": integrity.to_dict(),
            "retrieval_debug": retrieval_result.retrieval_debug,
        }


class SearchPipeline:
    """Standalone search pipeline (no LLM, no memory) for ``citeindex search``."""

    def __init__(
        self,
        corpus_root: str = "corpus",
        schema_version: str = SCHEMA_VERSION,
    ) -> None:
        self.corpus_root = corpus_root
        self.schema_version = schema_version

    def search(
        self,
        query: str,
        top_k: int = 20,
        cite_style: str = "chicago-author-date",
        retrieval: str = "auto",
        pageindex_model: str = "ollama/qwen3.5:cloud",
    ) -> Dict[str, Any]:
        from .corpus_loader import CorpusLoader
        from .indexing import IndexingAgent
        from .query_planner import QueryPlanner
        from .retrieval import RetrievalAgent

        # Load corpus
        loader = CorpusLoader(self.corpus_root)
        loader.load()

        if not loader.all_nodes:
            return {
                "status": "no_corpus",
                "message": "No ingested documents found in corpus. Run `citeindex ingest` first.",
                "query": query,
            }

        # Plan query
        planner = QueryPlanner(self.schema_version)
        query_plan = planner.plan(query, csl_registry=loader.csl_registry)

        if query_plan.clarification_required:
            return {
                "status": "needs_clarification",
                "query_id": query_plan.query_id,
                "questions": query_plan.clarification_questions,
                "query": query,
            }

        # Decide retrieval method
        use_pageindex = (
            retrieval == "pageindex"
            or (retrieval == "auto" and "pageindex_tree_search" in query_plan.retrieval_policy)
        )

        if use_pageindex:
            result = self._pageindex_search(query, top_k, pageindex_model)
        else:
            # Build indexes and use BM25
            indexer = IndexingAgent(self.schema_version)
            index_output = indexer.run(loader.all_nodes)

            retriever = RetrievalAgent(self.schema_version, top_k=top_k)
            result = retriever.run(
                query_plan.to_dict(),
                loader.all_nodes,
                index_output.inverted_index,
                loader.csl_registry,
            )

        # Enrich results with citation info
        csl_by_source: Dict[str, Dict[str, Any]] = {}
        for csl in loader.csl_registry:
            sid = csl.get("_source_id") or csl.get("id", "")
            csl_by_source[sid] = csl

        enriched_nodes: List[Dict[str, Any]] = []
        for node in result.ranked_nodes:
            source_id = node.get("source_id", "")
            csl = csl_by_source.get(source_id, {})
            node_copy = dict(node)
            node_copy["title"] = csl.get("title", "")
            authors = csl.get("author", [])
            if authors:
                first = authors[0]
                node_copy["author"] = f"{first.get('family', '')} {first.get('given', '')}".strip()
            # Generate formatted citation from CSL data
            if csl:
                try:
                    from citeindex.citation_style import format_bibliography
                    bib, _in_text = format_bibliography([csl], cite_style)
                    node_copy["formatted_citation"] = bib.strip() if bib and not bib.startswith("Error") else ""
                except Exception:
                    node_copy["formatted_citation"] = ""
            else:
                node_copy["formatted_citation"] = ""
            enriched_nodes.append(node_copy)

        return {
            "status": "ok",
            "query_id": query_plan.query_id,
            "intent_type": query_plan.intent_type,
            "retrieval_method": "pageindex" if use_pageindex else "bm25",
            "total_results": len(enriched_nodes),
            "results": enriched_nodes,
            "retrieval_debug": result.retrieval_debug,
        }

    def _pageindex_search(
        self, query: str, top_k: int, model: str
    ) -> "RetrievalResult":
        """Run PageIndex reasoning-based retrieval."""
        from .pageindex_retrieval import PageIndexRetrievalAgent
        from .models import RetrievalResult

        agent = PageIndexRetrievalAgent(
            corpus_root=self.corpus_root,
            model=model,
            top_k=top_k,
        )
        return agent.run(query=query)
