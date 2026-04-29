"""PageIndex Retrieval Agent — reasoning-based tree-search retrieval.

Complements the deterministic BM25 ``RetrievalAgent`` with LLM-driven
reasoning over PageIndex tree structures.  Instead of keyword matching,
the LLM navigates the document's hierarchical index to locate relevant
sections, then fetches specific page content.

Designed for complex, multi-step queries where BM25 falls short
(e.g. "compare the two authors' arguments on free will").

Uses ``ollama/qwen3.5:cloud`` via litellm — independent of the dspy-based
CiteIndex LLM pipeline.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import RetrievalResult, ScoredNode, SCHEMA_VERSION

logger = logging.getLogger(__name__)

PAGEINDEX_MODEL = "ollama/qwen3.5:cloud"

# Maximum pages to fetch per retrieval (avoid flooding context)
MAX_PAGES_PER_RETRIEVAL = 10


class PageIndexRetrievalAgent:
    """Reasoning-based retrieval over CiteIndex PageIndexTree structures."""

    def __init__(
        self,
        corpus_root: str = "corpus",
        model: str = PAGEINDEX_MODEL,
        top_k: int = 20,
    ) -> None:
        self.corpus_root = os.path.abspath(corpus_root)
        self.model = model
        self.top_k = top_k

    def run(
        self,
        query: str,
        doc_id: Optional[str] = None,
    ) -> RetrievalResult:
        """Run reasoning-based retrieval.

        Parameters
        ----------
        query : str
            User query.
        doc_id : str, optional
            If given, search only this document.  Otherwise search all
            documents in the corpus.

        Returns
        -------
        RetrievalResult
            Same schema as the BM25 ``RetrievalAgent`` output.
        """
        trees = self._load_trees(doc_id)
        if not trees:
            logger.warning("No PageIndex trees found in corpus")
            return RetrievalResult(
                query_id=query,
                ranked_nodes=[],
                retrieval_debug={"error": "no_trees_found"},
            )

        all_ranked: List[Dict[str, Any]] = []
        for tree_doc_id, tree in trees.items():
            ranked = self._search_single_tree(query, tree_doc_id, tree)
            all_ranked.extend(ranked)

        # Sort by relevance score descending, then by page ascending
        all_ranked.sort(
            key=lambda n: (-n.get("total_score", 0), n.get("page") or 9999)
        )
        all_ranked = all_ranked[: self.top_k]

        return RetrievalResult(
            query_id=query,
            ranked_nodes=all_ranked,
            retrieval_debug={
                "method": "pageindex_tree_search",
                "model": self.model,
                "trees_searched": len(trees),
                "returned": len(all_ranked),
            },
        )

    def _search_single_tree(
        self,
        query: str,
        doc_id: str,
        tree: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """LLM-driven tree search on a single document."""
        from citeindex.ingestion.pipelines.pageindex.utils import (
            llm_completion, extract_json,
        )

        # Build a compact tree summary for the LLM (no text, just structure)
        structure_summary = self._tree_to_summary(tree)

        # Step 1: Ask LLM to identify relevant sections
        relevant_sections = self._identify_relevant_sections(
            query, structure_summary, doc_id
        )

        if not relevant_sections:
            return []

        # Step 2: Build ranked evidence from identified sections
        ranked = []
        for section in relevant_sections:
            node_id = section.get("node_id", "")
            relevance = float(section.get("relevance_score", 0.5))
            reasoning = section.get("reasoning", "")

            # Find the actual tree node to get text/page info
            node_data = self._find_node_in_tree(tree, node_id)
            if not node_data:
                continue

            text = self._extract_node_text(node_data)
            page = self._extract_node_page(node_data)

            scored = ScoredNode(
                node_id=node_id,
                source_id=doc_id,
                section_path=node_data.get("heading", ""),
                sha256="",
                text=text,
                page=page,
                score_breakdown={
                    "pageindex_relevance": relevance,
                    "reasoning": reasoning,
                },
                total_score=relevance,
            )
            ranked.append(scored.to_dict())

        return ranked

    def _identify_relevant_sections(
        self,
        query: str,
        structure_summary: str,
        doc_id: str,
    ) -> List[Dict[str, Any]]:
        """Ask the LLM to reason about which sections are relevant."""
        from citeindex.ingestion.pipelines.pageindex.utils import (
            llm_completion, extract_json,
        )

        prompt = f"""You are a document retrieval expert. Given a user query and a document's hierarchical structure, identify the most relevant sections.

Document ID: {doc_id}

Document Structure:
{structure_summary}

User Query: {query}

Analyze the document structure and identify sections most likely to contain information relevant to the query. For each relevant section, explain your reasoning.

Reply in JSON format:
{{
    "sections": [
        {{
            "node_id": "<exact node_id from the structure>",
            "heading": "<section heading>",
            "relevance_score": <0.0 to 1.0>,
            "reasoning": "<brief explanation of why this section is relevant>"
        }}
    ]
}}

Rules:
- Only include sections that are genuinely relevant to the query.
- Rank by relevance_score (1.0 = highly relevant, 0.0 = not relevant).
- Return at most {MAX_PAGES_PER_RETRIEVAL} sections.
- If no sections are relevant, return {{"sections": []}}.

Directly return the JSON. Do not output anything else."""

        try:
            response = llm_completion(model=self.model, prompt=prompt)
            parsed = extract_json(response)
            sections = parsed.get("sections", [])
            if not isinstance(sections, list):
                return []
            return sections[: MAX_PAGES_PER_RETRIEVAL]
        except Exception:
            logger.warning("PageIndex LLM reasoning failed", exc_info=True)
            return []

    def _tree_to_summary(self, tree: Dict[str, Any]) -> str:
        """Convert a CiteIndex PageIndexTree to a compact text summary for LLM."""
        lines = []
        level_0 = tree.get("level_0", {})
        title = level_0.get("title", "Unknown")
        authors = level_0.get("author", [])
        author_str = ", ".join(
            a.get("literal") or f"{a.get('family', '')} {a.get('given', '')}".strip()
            for a in authors[:3]
        ) if authors else "Unknown"
        lines.append(f"Document: {title} by {author_str}")
        lines.append("")

        for section in tree.get("level_1", []):
            self._format_node(section, lines, indent=0)

        return "\n".join(lines)

    def _format_node(
        self, node: Dict[str, Any], lines: List[str], indent: int
    ) -> None:
        prefix = "  " * indent
        node_id = node.get("node_id", "")
        heading = node.get("heading", "")
        page_range = node.get("page_range", "")
        summary = node.get("summary", "")

        label = f"{prefix}[{node_id}] {heading}"
        if page_range:
            label += f" (pages {page_range})"
        lines.append(label)

        if summary:
            lines.append(f"{prefix}  Summary: {summary[:120]}")

        for child in node.get("children", []):
            # Check if it's a locator (has page_number) or a subsection (has heading)
            if child.get("heading"):
                self._format_node(child, lines, indent + 1)

    def _find_node_in_tree(
        self, tree: Dict[str, Any], target_id: str
    ) -> Optional[Dict[str, Any]]:
        """Find a node by node_id in the tree."""
        for section in tree.get("level_1", []):
            found = self._find_in_subtree(section, target_id)
            if found is not None:
                return found
        return None

    def _find_in_subtree(
        self, node: Dict[str, Any], target_id: str
    ) -> Optional[Dict[str, Any]]:
        if node.get("node_id") == target_id:
            return node
        for child in node.get("children", []):
            found = self._find_in_subtree(child, target_id)
            if found is not None:
                return found
        return None

    def _extract_node_text(self, node: Dict[str, Any]) -> str:
        """Extract text from a tree node (check text_blocks, text, summary)."""
        # Try text_blocks first (LocatorNode)
        blocks = node.get("text_blocks", [])
        if blocks:
            return "\n".join(b.get("text", "") for b in blocks if b.get("text"))

        # Try direct text
        text = node.get("text")
        if text:
            return text

        # Try summary
        summary = node.get("summary")
        if summary:
            return summary

        # Recurse into children
        parts = []
        for child in node.get("children", []):
            child_text = self._extract_node_text(child)
            if child_text:
                parts.append(child_text)
        return "\n".join(parts)

    def _extract_node_page(self, node: Dict[str, Any]) -> Optional[int]:
        """Extract page number from a tree node."""
        page = node.get("page_number")
        if page is not None:
            return page

        # Try page_range string
        pr = node.get("page_range", "")
        if pr:
            try:
                return int(pr.split("-")[0])
            except (ValueError, IndexError):
                pass

        # Check children
        for child in node.get("children", []):
            page = self._extract_node_page(child)
            if page is not None:
                return page
        return None

    def _load_trees(self, doc_id: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """Load PageIndex trees from corpus/.citeindex/documents/structured/."""
        structured_dir = Path(self.corpus_root) / ".citeindex" / "documents" / "structured"
        trees: Dict[str, Dict[str, Any]] = {}

        if not structured_dir.is_dir():
            # Try legacy corpus layout
            return self._load_trees_legacy(doc_id)

        for tree_file in structured_dir.glob("*.citeindex.json"):
            file_doc_id = tree_file.stem.replace(".citeindex", "")
            if doc_id and file_doc_id != doc_id:
                continue
            try:
                with open(tree_file, "r", encoding="utf-8") as f:
                    tree = json.load(f)
                trees[file_doc_id] = tree
            except Exception:
                logger.warning("Failed to load tree: %s", tree_file, exc_info=True)

        return trees

    def _load_trees_legacy(self, doc_id: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """Try loading from legacy corpus layout."""
        trees: Dict[str, Dict[str, Any]] = {}
        corpus = Path(self.corpus_root)
        for tree_file in corpus.rglob("*.citeindex.json"):
            file_doc_id = tree_file.stem.replace(".citeindex", "")
            if doc_id and file_doc_id != doc_id:
                continue
            try:
                with open(tree_file, "r", encoding="utf-8") as f:
                    tree = json.load(f)
                trees[file_doc_id] = tree
            except Exception:
                logger.warning("Failed to load tree: %s", tree_file, exc_info=True)
        return trees


def handle_pageindex_retrieval(
    inputs: Dict[str, Any],
    _call_tool=None,
) -> Dict[str, Any]:
    """V12 runtime handler for PageIndex retrieval."""
    query = ""
    for key in ("query", "sub_query", "user_query", "prompt"):
        val = inputs.get(key)
        if isinstance(val, str) and val.strip():
            query = val.strip()
            break

    corpus_root = (
        inputs.get("corpus_root")
        or os.environ.get("CITEINDEX_CORPUS_ROOT")
        or "corpus"
    )
    doc_id = inputs.get("doc_id")
    model = inputs.get("pageindex_model", PAGEINDEX_MODEL)
    top_k = int(inputs.get("top_k", 20))

    agent = PageIndexRetrievalAgent(
        corpus_root=corpus_root,
        model=model,
        top_k=top_k,
    )
    result = agent.run(query=query, doc_id=doc_id)

    output = result.to_dict()
    output["agent"] = "PageIndexRetrievalAgent"
    return output
