"""Thin v12 agent adapter runtime.

These adapters provide the Python entrypoints expected by the Rust v12
manifests. They intentionally keep behavior small and deterministic for now,
wrapping the existing Python pipeline where practical.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import traceback
import uuid
from typing import Any, Callable, Dict, List, Optional


PROTOCOL_VERSION = "12.0"
ToolCaller = Callable[[str, Dict[str, Any]], Dict[str, Any]]


def _configure_logging(agent_name: str) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format=f"%(asctime)s {agent_name} %(levelname)s %(message)s",
        stream=sys.stderr,
    )


def _emit(message: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False, sort_keys=True) + "\n")
    sys.stdout.flush()


def _hash_output(output: Dict[str, Any]) -> str:
    payload = json.dumps(output, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _resource_usage() -> Dict[str, Any]:
    return {
        "llm_calls": 0,
        "tool_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "wall_time_ms": 0,
    }


def _get_corpus_root(inputs: Dict[str, Any]) -> str:
    return (
        inputs.get("corpus_root")
        or os.environ.get("CITEINDEX_CORPUS_ROOT")
        or "corpus"
    )


def _extract_query(inputs: Dict[str, Any]) -> str:
    for key in ("query", "sub_query", "user_query", "prompt", "goal", "topic"):
        value = inputs.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    goal_aspect = inputs.get("goal_aspect")
    if isinstance(goal_aspect, dict):
        value = goal_aspect.get("sub_query")
        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def _extract_text(inputs: Dict[str, Any]) -> str:
    for key in ("text", "document_text", "content", "passage"):
        value = inputs.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _split_sentences(text: str) -> List[str]:
    return [
        part.strip()
        for part in re.split(r"(?<=[.!?。！？])\s+", text)
        if part.strip()
    ]


def _detect_language(text: str) -> str:
    if re.search(r"[\u3040-\u30ff]", text):
        return "ja"
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh"
    return "en"


def _format_citation(fields: Dict[str, Any]) -> str:
    title = str(fields.get("title") or "").strip()
    authors = str(fields.get("authors") or "").strip()
    venue = str(fields.get("venue") or "").strip()
    year = fields.get("year")

    parts = []
    if authors:
        parts.append(authors)
    if year is not None:
        parts.append(f"({year})")
    if title:
        parts.append(title)
    if venue:
        parts.append(venue)
    return ". ".join(parts)


def _extract_year(issued: Any) -> int:
    if not isinstance(issued, dict):
        return 0
    date_parts = issued.get("date-parts")
    if not isinstance(date_parts, list) or not date_parts:
        return 0
    first = date_parts[0]
    if not isinstance(first, list) or not first:
        return 0
    year = first[0]
    return int(year) if isinstance(year, int) else 0


def _authors_text(authors: Any) -> str:
    if not isinstance(authors, list):
        return ""

    names: List[str] = []
    for author in authors[:3]:
        if not isinstance(author, dict):
            continue
        literal = author.get("literal")
        family = author.get("family")
        given = author.get("given")
        if isinstance(literal, str) and literal.strip():
            names.append(literal.strip())
            continue
        if isinstance(family, str) and family.strip() and isinstance(given, str) and given.strip():
            names.append(f"{family.strip()} {given.strip()}")
            continue
        if isinstance(family, str) and family.strip():
            names.append(family.strip())
            continue
        if isinstance(given, str) and given.strip():
            names.append(given.strip())
    return ", ".join(names)


def _first_document_text(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, list):
        for item in value:
            text = _first_document_text(item)
            if text:
                return text
        return ""
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
        for nested in value.values():
            candidate = _first_document_text(nested)
            if candidate:
                return candidate
    return ""


def _index_ingested_document(result: Dict[str, Any], call_tool: ToolCaller) -> Dict[str, Any]:
    csl = result.get("standardized_csl_json") if isinstance(result.get("standardized_csl_json"), dict) else {}
    sub_outputs = result.get("sub_pipeline_outputs") if isinstance(result.get("sub_pipeline_outputs"), dict) else {}
    document_json = sub_outputs.get("document_json") if isinstance(sub_outputs.get("document_json"), dict) else {}
    transcript_json = sub_outputs.get("transcript_json") if isinstance(sub_outputs.get("transcript_json"), dict) else {}
    merkle_tree = sub_outputs.get("merkle_tree") if isinstance(sub_outputs.get("merkle_tree"), dict) else {}
    ingestion_log_entry = result.get("ingestion_log_entry") if isinstance(result.get("ingestion_log_entry"), dict) else {}
    source_snapshot_path = str(sub_outputs.get("source_snapshot_path") or "")
    cleanup_source_snapshot = bool(sub_outputs.get("cleanup_source_snapshot"))

    doc_id = str(csl.get("id") or csl.get("content_hash") or "")
    title = str(csl.get("title") or document_json.get("metadata", {}).get("title") or doc_id)
    authors = _authors_text(csl.get("author"))
    abstract_text = str(csl.get("abstract") or csl.get("abstract_text") or _first_document_text(document_json))
    language = str(csl.get("language") or _detect_language(f"{title} {abstract_text}"))

    params = {
        "doc_id": doc_id,
        "title": title,
        "authors": authors,
        "year": _extract_year(csl.get("issued")),
        "doi": str(csl.get("DOI") or csl.get("doi") or ""),
        "abstract_text": abstract_text,
        "venue": str(csl.get("container-title") or csl.get("container_title") or ""),
        "doc_type": str(csl.get("type") or csl.get("source_type") or "article-journal"),
        "quality_tier": str(csl.get("ci_quality_tier") or "silver"),
        "hierarchy_path": str(csl.get("ci_hierarchy_path") or ""),
        "merkle_hash": str(merkle_tree.get("root") or csl.get("merkle_root") or ""),
        "language": language,
        "standardized_csl_json": csl,
        "document_json": document_json,
        "transcript_json": transcript_json,
        "merkle_tree": merkle_tree,
        "input_ref": str(ingestion_log_entry.get("input_ref") or ""),
        "resource_type": str(ingestion_log_entry.get("resource_type") or sub_outputs.get("resource_type") or ""),
        "source_snapshot_path": source_snapshot_path,
        "cleanup_source_snapshot": cleanup_source_snapshot,
    }

    return call_tool("tantivy_index", params)


def _normalize_librarian_hits(tool_result: Dict[str, Any], query: str) -> Dict[str, Any]:
    hits = tool_result.get("hits") if isinstance(tool_result.get("hits"), list) else []
    results = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        fields = hit.get("fields") if isinstance(hit.get("fields"), dict) else {}
        doc_id = str(hit.get("id") or "")
        title = str(fields.get("title") or "")
        author = str(fields.get("authors") or "")
        text = str(fields.get("abstract_text") or title)
        results.append(
            {
                "node_id": doc_id,
                "doc_id": doc_id,
                "text": text,
                "total_score": float(hit.get("score") or 0.0),
                "title": title,
                "author": author,
                "formatted_citation": _format_citation(fields),
            }
        )

    return {
        "agent": "LibrarianAgent",
        "status": "ok",
        "query": query,
        "total_results": len(results),
        "results": results,
        "retrieval_debug": {
            "backend": "kernel_tantivy",
            "total_hits": int(tool_result.get("total_hits") or len(results)),
        },
    }


def _normalize_memory_hits(tool_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    hits = tool_result.get("hits") if isinstance(tool_result.get("hits"), list) else []
    normalized = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        fields = hit.get("fields") if isinstance(hit.get("fields"), dict) else {}
        normalized.append(
            {
                "memory_id": str(hit.get("id") or ""),
                "session_id": str(fields.get("session_id") or ""),
                "title": str(fields.get("title") or ""),
                "content": str(fields.get("content") or ""),
                "score": float(hit.get("score") or 0.0),
            }
        )
    return normalized


def _query_terms(query: str) -> List[str]:
    cleaned = query.strip().lower()
    terms = [token for token in re.findall(r"\w+", cleaned) if len(token) > 1]
    if terms:
        return terms
    return [cleaned] if cleaned else []


def _node_text(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    for key in ("text", "transcript_text"):
        text = value.get(key)
        if isinstance(text, str) and text.strip():
            return text.strip()

    blocks = value.get("text_blocks")
    if isinstance(blocks, list):
        joined = " ".join(
            block.get("text", "").strip()
            for block in blocks
            if isinstance(block, dict) and isinstance(block.get("text"), str) and block.get("text", "").strip()
        ).strip()
        if joined:
            return joined

    children = value.get("children")
    if isinstance(children, list):
        joined = " ".join(_node_text(child) for child in children).strip()
        if joined:
            return joined

    return ""


def _locator_string(value: Dict[str, Any]) -> str:
    page_number = value.get("page_number")
    if isinstance(page_number, int) and page_number > 0:
        return f"p. {page_number}"
    paragraph_number = value.get("paragraph_number")
    if isinstance(paragraph_number, int) and paragraph_number >= 0:
        return f"para. {paragraph_number}"
    start_time = value.get("start_time")
    if isinstance(start_time, str) and start_time:
        return start_time
    return ""


def _tree_candidates(tree: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for section in tree.get("level_1", []):
        if not isinstance(section, dict):
            continue
        section_heading = str(section.get("heading") or section.get("node_id") or "")
        for subsection in section.get("children", []):
            if not isinstance(subsection, dict):
                continue
            subsection_heading = str(subsection.get("heading") or subsection.get("node_id") or "")
            for locator in subsection.get("children", []):
                if not isinstance(locator, dict):
                    continue
                text = _node_text(locator)
                if not text:
                    continue
                section_path = " / ".join(part for part in (section_heading, subsection_heading) if part)
                candidates.append(
                    {
                        "node_id": str(locator.get("node_id") or ""),
                        "text": text,
                        "section_path": section_path,
                        "locator": _locator_string(locator),
                        "sha256": str(locator.get("sha256") or ""),
                        "document_merkle_root": str(locator.get("document_merkle_root") or ""),
                        "merkle_proof": locator.get("merkle_proof") if isinstance(locator.get("merkle_proof"), list) else [],
                    }
                )
    return candidates


def _select_best_candidate(prompt: str, tree: Dict[str, Any]) -> Dict[str, Any]:
    candidates = _tree_candidates(tree)
    if not candidates:
        return {}

    terms = _query_terms(prompt)

    def score(candidate: Dict[str, Any]) -> tuple[int, int, int]:
        text_lower = candidate.get("text", "").lower()
        exact = 1 if prompt.strip().lower() and prompt.strip().lower() in text_lower else 0
        overlaps = sum(text_lower.count(term) for term in terms)
        return (exact, overlaps, -len(text_lower))

    return max(candidates, key=score)


def _enrich_chat_hit(hit: Dict[str, Any], prompt: str, call_tool: ToolCaller) -> Dict[str, Any]:
    fields = hit.get("fields") if isinstance(hit.get("fields"), dict) else {}
    doc_id = str(hit.get("id") or "")
    fallback_text = str(fields.get("abstract_text") or fields.get("title") or "")
    fallback_citation = _format_citation(fields)
    evidence = {
        "node_id": doc_id,
        "source_id": doc_id,
        "sha256": str(fields.get("merkle_hash") or ""),
        "document_merkle_root": str(fields.get("merkle_hash") or ""),
        "merkle_proof": [],
        "citation_key": doc_id,
        "citation_rendered": fallback_citation,
        "section_path": "",
        "text": fallback_text,
    }

    try:
        tree = call_tool("tree_load", {"doc_id": doc_id})
        candidate = _select_best_candidate(prompt, tree)
        if candidate:
            evidence["node_id"] = candidate.get("node_id") or doc_id
            evidence["section_path"] = candidate.get("section_path") or ""
            evidence["text"] = candidate.get("text") or fallback_text
            evidence["sha256"] = str(candidate.get("sha256") or evidence["sha256"])
            evidence["document_merkle_root"] = str(
                candidate.get("document_merkle_root") or evidence["document_merkle_root"]
            )
            evidence["merkle_proof"] = (
                candidate.get("merkle_proof")
                if isinstance(candidate.get("merkle_proof"), list)
                else evidence["merkle_proof"]
            )

            traversed = call_tool(
                "tree_traverse",
                {"doc_id": doc_id, "node_id": evidence["node_id"]},
            )
            traversed_text = _node_text(traversed)
            if traversed_text:
                evidence["text"] = traversed_text

            locator = _locator_string(traversed if isinstance(traversed, dict) else {}) or candidate.get("locator", "")
            citation_result = call_tool(
                "csl_render",
                {"doc_id": doc_id, **({"locator": locator} if locator else {})},
            )
            if isinstance(citation_result, dict) and isinstance(citation_result.get("citation"), str):
                evidence["citation_rendered"] = citation_result["citation"]
    except Exception as exc:
        logging.warning("tree-aware enrichment failed for %s: %s", doc_id, exc)

    return evidence


def _build_chat_response(
    prompt: str,
    query_id: str,
    evidence_items: List[Dict[str, Any]],
    memory_hits: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if not evidence_items:
        return {
            "status": "no_corpus",
            "query_id": query_id,
            "answer_human": "No evidence found for the query.",
            "answer_machine": {
                "schema_version": "1.0.0",
                "query_id": query_id,
                "answer": "",
                "evidence": [],
            },
            "integrity": {
                "schema_version": "1.0.0",
                "status": "rejected",
                "checks": [],
                "violations": ["No evidence items in answer"],
                "approved_answer_ref": "",
            },
            "retrieval_debug": {
                "backend": "kernel_tantivy",
                "memory_hits": len(memory_hits),
                "returned": 0,
            },
        }

    answer_parts = []
    human_parts = [f"## Query: {prompt}\n"]

    if memory_hits:
        human_parts.append("### Related Memory\n")
        for item in memory_hits[:3]:
            snippet = item["content"][:240].strip()
            if len(item["content"]) > 240:
                snippet += "..."
            human_parts.append(f"- {item['title'] or item['memory_id']}: {snippet}")
        human_parts.append("")

    for item in evidence_items:
        text = str(item.get("text") or "")
        citation = str(item.get("citation_rendered") or item.get("citation_key") or "")
        node_id = str(item.get("node_id") or item.get("source_id") or "")
        answer_parts.append(text)
        human_parts.append(f"> {text}\n> — [{citation}] (node: `{node_id}`)\n")

    human_parts.append("\n---\n### Evidence Appendix\n")
    for index, item in enumerate(evidence_items, start=1):
        human_parts.append(
            f"{index}. **{item['node_id']}** ({item.get('section_path', '')}) — [{item['citation_rendered']}]"
        )

    return {
        "status": "ok",
        "query_id": query_id,
        "answer_human": "\n".join(human_parts),
        "answer_machine": {
            "schema_version": "1.0.0",
            "query_id": query_id,
            "answer": "\n\n".join(answer_parts),
            "evidence": evidence_items,
        },
        "integrity": {
            "schema_version": "1.0.0",
            "status": "approved",
            "checks": [],
            "violations": [],
            "approved_answer_ref": "",
        },
        "retrieval_debug": {
            "backend": "kernel_tantivy",
            "memory_hits": len(memory_hits),
            "returned": len(evidence_items),
        },
    }


def _save_chat_memory(
    prompt: str,
    thread_id: str,
    response: Dict[str, Any],
    call_tool: ToolCaller,
) -> Dict[str, Any]:
    answer_human = str(response.get("answer_human") or "")
    memory_id = hashlib.sha256(
        f"{thread_id}|{prompt}|{answer_human}".encode("utf-8")
    ).hexdigest()[:16]
    evidence_ids = [
        item.get("node_id", "")
        for item in response.get("answer_machine", {}).get("evidence", [])
        if isinstance(item, dict)
    ]
    return call_tool(
        "memory_save",
        {
            "memory_id": memory_id,
            "session_id": thread_id,
            "title": prompt,
            "description": f"Chat response for {thread_id}",
            "content": answer_human,
            "evidence_node_ids": evidence_ids,
            "merkle_hash": _hash_output({"thread_id": thread_id, "prompt": prompt, "evidence": evidence_ids}),
            "language": _detect_language(f"{prompt} {answer_human}"),
        },
    )


def _chat_via_tools(inputs: Dict[str, Any], call_tool: ToolCaller) -> Dict[str, Any]:
    from .query_planner import QueryPlanner

    prompt = _extract_query(inputs)
    thread_id = str(inputs.get("thread_id") or "default")
    planner = QueryPlanner()
    plan = planner.plan(prompt)

    if plan.clarification_required:
        return {
            "status": "needs_clarification",
            "query_id": plan.query_id,
            "questions": plan.clarification_questions,
            "thread": thread_id,
        }

    language = _detect_language(prompt)
    memory_tool_result = call_tool(
        "search_memory",
        {"query": prompt, "limit": 3, "language": language},
    )
    document_tool_result = call_tool(
        "tantivy_search",
        {
            "query": prompt,
            "index": "documents",
            "limit": int(inputs.get("top_k", 5)),
            "language": language,
        },
    )

    memory_hits = _normalize_memory_hits(memory_tool_result)
    doc_hits = (
        document_tool_result.get("hits")
        if isinstance(document_tool_result.get("hits"), list)
        else []
    )
    evidence_items = [
        _enrich_chat_hit(hit, prompt, call_tool)
        for hit in doc_hits[: int(inputs.get("top_k", 5))]
        if isinstance(hit, dict)
    ]
    response = _build_chat_response(prompt, plan.query_id, evidence_items, memory_hits)
    response["thread"] = thread_id

    try:
        response["kernel_memory_save"] = _save_chat_memory(prompt, thread_id, response, call_tool)
    except Exception as exc:
        logging.warning("kernel memory save after chat failed: %s", exc)
        response["kernel_memory_warning"] = str(exc)

    return response


def handle_coordinator(inputs: Dict[str, Any], _call_tool: Optional[ToolCaller] = None) -> Dict[str, Any]:
    if inputs.get("operation") == "chat":
        if _call_tool is not None:
            result = _chat_via_tools(inputs, _call_tool)
        else:
            from .chat import ChatPipeline

            prompt = _extract_query(inputs)
            pipeline = ChatPipeline(
                corpus_root=_get_corpus_root(inputs),
                llm_model=str(inputs.get("llm_model") or "ollama/qwen3"),
            )
            result = pipeline.chat(prompt, thread_id=str(inputs.get("thread_id") or "default"))
        return {"agent": "CoordinatorAgent", **result}

    from .query_planner import QueryPlanner

    query = _extract_query(inputs)
    planner = QueryPlanner()
    plan = planner.plan(query)
    return {
        "agent": "CoordinatorAgent",
        "query_plan": plan.to_dict(),
    }


def handle_librarian(
    inputs: Dict[str, Any],
    call_tool: Optional[ToolCaller] = None,
) -> Dict[str, Any]:
    query = _extract_query(inputs)
    if call_tool is not None and query:
        tool_result = call_tool(
            "tantivy_search",
            {
                "query": query,
                "index": "documents",
                "limit": int(inputs.get("top_k", 10)),
                "language": _detect_language(query),
            },
        )
        return _normalize_librarian_hits(tool_result, query)

    from .chat import SearchPipeline

    pipeline = SearchPipeline(corpus_root=_get_corpus_root(inputs))
    result = pipeline.search(
        query,
        top_k=int(inputs.get("top_k", 10)),
        cite_style=str(inputs.get("cite_style") or "chicago-author-date"),
    )
    return {"agent": "LibrarianAgent", **result}


def handle_ingest(inputs: Dict[str, Any], _call_tool: Optional[ToolCaller] = None) -> Dict[str, Any]:
    from ..ingestion import CiteIndexIngestionOrchestrator
    from ..ingestion.models import IngestionConfig

    input_ref = inputs.get("input_ref") or inputs.get("path") or inputs.get("url")
    if not isinstance(input_ref, str) or not input_ref.strip():
        raise ValueError("missing input_ref/path/url")

    orchestrator = CiteIndexIngestionOrchestrator(corpus_root=_get_corpus_root(inputs))
    config = IngestionConfig(doc_type_override=inputs.get("doc_type_override"))
    result = orchestrator.ingest(input_ref, config=config)
    if _call_tool is not None and result.get("status") == "ok":
        try:
            result["kernel_index"] = _index_ingested_document(result, _call_tool)
        except Exception as exc:
            logging.warning("kernel indexing after ingest failed: %s", exc)
            result["kernel_index_warning"] = str(exc)
    return {"agent": "IngestAgent", **result}


def handle_claim_extraction(
    inputs: Dict[str, Any], _call_tool: Optional[ToolCaller] = None
) -> Dict[str, Any]:
    text = _extract_text(inputs)
    claims = []
    for idx, sentence in enumerate(_split_sentences(text)[:20], start=1):
        if len(sentence) < 20:
            continue
        entities = sorted(set(re.findall(r"\b[A-Z][a-zA-Z0-9_-]+\b", sentence)))
        claims.append(
            {
                "claim_id": f"claim-{idx}",
                "claim_text": sentence,
                "section_ref": inputs.get("section_ref", ""),
                "verbatim_passage": sentence,
                "polarity_tag": "neutral",
                "entities": entities,
                "hierarchy_path": inputs.get("hierarchy_path", "/"),
            }
        )

    return {
        "agent": "ClaimExtractionAgent",
        "claims": claims,
    }


def handle_contradiction(
    inputs: Dict[str, Any], _call_tool: Optional[ToolCaller] = None
) -> Dict[str, Any]:
    claims = inputs.get("claims") or []
    if not isinstance(claims, list):
        claims = []

    edges = []
    seen = {}
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        text = claim.get("claim_text", "")
        key = text.strip().lower()
        if not key:
            continue
        if key in seen:
            edges.append(
                {
                    "claim_a_id": seen[key],
                    "claim_b_id": claim.get("claim_id", ""),
                    "explanation": "duplicate claim text detected by adapter",
                }
            )
        else:
            seen[key] = claim.get("claim_id", "")

    return {
        "agent": "ContradictionAgent",
        "edges": edges,
    }


def handle_gap_identification(
    inputs: Dict[str, Any], _call_tool: Optional[ToolCaller] = None
) -> Dict[str, Any]:
    goal_state = inputs.get("goal_state") if isinstance(inputs.get("goal_state"), dict) else {}
    required = inputs.get("required_aspects") or goal_state.get("required_aspects") or []
    coverage = inputs.get("coverage_scores") or goal_state.get("aspect_coverage") or {}
    threshold = float(inputs.get("coverage_threshold") or goal_state.get("coverage_threshold") or 0.6)

    gaps = []
    for aspect in required:
        score = float(coverage.get(aspect, 0.0)) if isinstance(coverage, dict) else 0.0
        if score < threshold:
            gaps.append(
                {
                    "aspect": aspect,
                    "coverage": score,
                    "suggested_terms": [term for term in re.split(r"\W+", aspect.lower()) if term],
                }
            )

    return {
        "agent": "GapIdentificationAgent",
        "gaps": gaps,
    }


def handle_literature_review(
    inputs: Dict[str, Any], _call_tool: Optional[ToolCaller] = None
) -> Dict[str, Any]:
    from .chat import SearchPipeline

    query = _extract_query(inputs)
    pipeline = SearchPipeline(corpus_root=_get_corpus_root(inputs))
    result = pipeline.search(query, top_k=int(inputs.get("top_k", 20)))
    return {
        "agent": "LiteratureReviewAgent",
        "review": result,
    }


def handle_hierarchy_classification(
    inputs: Dict[str, Any], _call_tool: Optional[ToolCaller] = None
) -> Dict[str, Any]:
    query = (_extract_query(inputs) + " " + _extract_text(inputs)).lower()
    if any(term in query for term in ("transformer", "attention", "rnn", "nlp")):
        path = "/cs/nlp"
    elif any(term in query for term in ("church", "bible", "orthodox", "theology", "christian")):
        path = "/religion/christianity"
    else:
        path = "/general"

    return {
        "agent": "HierarchyClassificationAgent",
        "hierarchy_path": path,
        "confidence": 0.7,
    }


def handle_structure(
    inputs: Dict[str, Any], _call_tool: Optional[ToolCaller] = None
) -> Dict[str, Any]:
    claims = inputs.get("claims") or []
    if not isinstance(claims, list):
        claims = []

    nodes = []
    for idx, claim in enumerate(claims[:10], start=1):
        if not isinstance(claim, dict):
            continue
        nodes.append(
            {
                "id": f"node-{idx}",
                "heading_suggestion": claim.get("section_ref") or f"Section {idx}",
                "supporting_claims": [claim.get("claim_id", f"claim-{idx}")],
                "dependency_ids": [],
                "coverage": "Partial",
                "comparable_section_refs": [],
            }
        )

    return {
        "agent": "StructureAgent",
        "nodes": nodes,
    }


def _handle_pageindex_retrieval(
    inputs: Dict[str, Any], _call_tool: Optional[ToolCaller] = None
) -> Dict[str, Any]:
    from .pageindex_retrieval import handle_pageindex_retrieval
    return handle_pageindex_retrieval(inputs, _call_tool)


HANDLERS: Dict[str, Callable[[Dict[str, Any], Optional[ToolCaller]], Dict[str, Any]]] = {
    "CoordinatorAgent": handle_coordinator,
    "LibrarianAgent": handle_librarian,
    "IngestAgent": handle_ingest,
    "ClaimExtractionAgent": handle_claim_extraction,
    "ContradictionAgent": handle_contradiction,
    "GapIdentificationAgent": handle_gap_identification,
    "LiteratureReviewAgent": handle_literature_review,
    "HierarchyClassificationAgent": handle_hierarchy_classification,
    "StructureAgent": handle_structure,
    "PageIndexRetrievalAgent": _handle_pageindex_retrieval,
}


def serve(agent_name: str) -> None:
    _configure_logging(agent_name)
    handler = HANDLERS[agent_name]
    logging.info("starting adapter runtime for %s", agent_name)

    while True:
        line = sys.stdin.readline()
        if line == "":
            break
        if not line.strip():
            continue

        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            logging.warning("invalid JSON input ignored")
            continue

        msg_type = message.get("type")
        if msg_type == "init":
            _emit(
                {
                    "type": "init_ack",
                    "agent_name": agent_name,
                    "protocol_version": PROTOCOL_VERSION,
                    "status": "ok",
                    "error": None,
                }
            )
            continue

        if msg_type == "shutdown":
            _emit({"type": "shutdown_ack", "agent_name": agent_name})
            break

        if msg_type == "tool_response":
            # Thin adapters do not drive tool loops yet. Ignore responses.
            continue

        if msg_type != "request":
            logging.info("ignoring message type %s", msg_type)
            continue

        task_id = message.get("task_id", "unknown")
        inputs = message.get("inputs") if isinstance(message.get("inputs"), dict) else {}

        def call_tool(tool: str, params: Dict[str, Any]) -> Dict[str, Any]:
            call_id = f"{agent_name}:{uuid.uuid4()}"
            _emit({"type": "tool_call", "call_id": call_id, "tool": tool, "params": params})

            while True:
                response_line = sys.stdin.readline()
                if response_line == "":
                    raise RuntimeError(f"EOF while waiting for tool response {call_id}")
                if not response_line.strip():
                    continue

                response = json.loads(response_line)
                if response.get("type") != "tool_response":
                    logging.info(
                        "ignoring message type %s while waiting for tool response",
                        response.get("type"),
                    )
                    continue
                if response.get("call_id") != call_id:
                    logging.warning(
                        "ignoring tool_response for %s while waiting for %s",
                        response.get("call_id"),
                        call_id,
                    )
                    continue

                error = response.get("error")
                if isinstance(error, dict) and error.get("message"):
                    raise RuntimeError(str(error["message"]))
                result = response.get("result")
                if isinstance(result, dict):
                    return result
                return {"value": result}

        try:
            _emit(
                {
                    "type": "progress",
                    "task_id": task_id,
                    "stage": "PLAN",
                    "iteration": 1,
                    "detail": f"{agent_name} adapter handling request",
                    "tool_calls_so_far": 0,
                    "llm_calls_so_far": 0,
                }
            )
            output = handler(inputs, call_tool)
            _emit(
                {
                    "type": "result",
                    "task_id": task_id,
                    "status": "ok",
                    "output": output,
                    "output_hash": _hash_output(output),
                    "resource_usage": _resource_usage(),
                }
            )
        except Exception as exc:  # pragma: no cover - defensive runtime path
            logging.error("agent adapter failed: %s", exc)
            logging.debug(traceback.format_exc())
            _emit(
                {
                    "type": "error",
                    "task_id": task_id,
                    "error_type": exc.__class__.__name__,
                    "message": str(exc),
                    "recoverable": True,
                    "partial_output": None,
                }
            )


def main(agent_name: str) -> None:
    serve(agent_name)
