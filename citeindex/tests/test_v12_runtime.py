import hashlib
import json

from citeindex.agents.v12_runtime import (
    _hash_output,
    _index_ingested_document,
    _chat_via_tools,
    handle_coordinator,
    handle_librarian,
)


def test_hash_output_uses_contract_prefix() -> None:
    output = {"b": 2, "a": 1}
    expected = "sha256:" + hashlib.sha256(
        json.dumps(output, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()

    assert _hash_output(output) == expected


def test_handle_coordinator_keeps_query_plan_mode() -> None:
    result = handle_coordinator({"query": "attention in neural translation"})

    assert result["agent"] == "CoordinatorAgent"
    assert "query_plan" in result


def test_handle_librarian_uses_kernel_tool_shape() -> None:
    seen = {}

    def fake_tool(tool: str, params: dict) -> dict:
        seen["tool"] = tool
        seen["params"] = params
        return {
            "total_hits": 1,
            "hits": [
                {
                    "id": "doc-1",
                    "score": 0.75,
                    "fields": {
                        "title": "Church History",
                        "authors": "Aji Ap",
                        "abstract_text": "A study of church history.",
                        "year": 2024,
                        "venue": "Journal of History",
                    },
                }
            ],
        }

    result = handle_librarian({"query": "church history", "top_k": 5}, fake_tool)

    assert seen["tool"] == "tantivy_search"
    assert seen["params"]["index"] == "documents"
    assert result["agent"] == "LibrarianAgent"
    assert result["results"][0]["node_id"] == "doc-1"
    assert "Church History" in result["results"][0]["formatted_citation"]


def test_index_ingested_document_builds_tantivy_index_payload() -> None:
    seen = {}

    def fake_tool(tool: str, params: dict) -> dict:
        seen["tool"] = tool
        seen["params"] = params
        return {"status": "ok", "doc_id": params["doc_id"]}

    result = _index_ingested_document(
        {
            "status": "ok",
            "ingestion_log_entry": {
                "input_ref": "/tmp/document.pdf",
                "resource_type": "digital_pdf",
            },
            "standardized_csl_json": {
                "id": "doc-1",
                "title": "从新英格兰到英格兰",
                "issued": {"date-parts": [[2021]]},
                "type": "webpage",
                "merkle_root": "root-hash",
            },
            "sub_pipeline_outputs": {
                "document_json": {
                    "nodes": [{"text": "正文内容"}],
                },
                "transcript_json": {"segments": [{"text": "音频转写"}]},
                "merkle_tree": {"root": "root-hash"},
                "source_snapshot_path": "/tmp/url-article.html",
                "cleanup_source_snapshot": True,
            },
        },
        fake_tool,
    )

    assert seen["tool"] == "tantivy_index"
    assert seen["params"]["doc_id"] == "doc-1"
    assert seen["params"]["title"] == "从新英格兰到英格兰"
    assert seen["params"]["abstract_text"] == "正文内容"
    assert seen["params"]["language"] == "zh"
    assert seen["params"]["standardized_csl_json"]["id"] == "doc-1"
    assert seen["params"]["document_json"]["nodes"][0]["text"] == "正文内容"
    assert seen["params"]["transcript_json"]["segments"][0]["text"] == "音频转写"
    assert seen["params"]["merkle_tree"]["root"] == "root-hash"
    assert seen["params"]["input_ref"] == "/tmp/document.pdf"
    assert seen["params"]["resource_type"] == "digital_pdf"
    assert seen["params"]["source_snapshot_path"] == "/tmp/url-article.html"
    assert seen["params"]["cleanup_source_snapshot"] is True
    assert result["status"] == "ok"


def test_chat_via_tools_uses_search_and_memory_tools() -> None:
    calls = []

    def fake_tool(tool: str, params: dict) -> dict:
        calls.append((tool, params))
        if tool == "search_memory":
            return {
                "total_hits": 1,
                "hits": [
                    {
                        "id": "mem-1",
                        "score": 0.4,
                        "fields": {
                            "session_id": "thread-1",
                            "title": "Earlier note",
                            "content": "Earlier answer about church history.",
                        },
                    }
                ],
            }
        if tool == "tantivy_search":
            return {
                "total_hits": 1,
                "hits": [
                    {
                        "id": "doc-1",
                        "score": 0.9,
                        "fields": {
                            "title": "Church History",
                            "authors": "Aji Ap",
                            "abstract_text": "A survey of church history.",
                            "year": 2024,
                            "venue": "Journal of History",
                            "merkle_hash": "sha256:abc",
                        },
                    }
                ],
            }
        if tool == "tree_load":
            return {
                "level_1": [
                    {
                        "heading": "Section 1",
                        "children": [
                            {
                                "heading": "Overview",
                                "children": [
                                    {
                                        "node_id": "doc-1:node-1",
                                        "paragraph_number": 3,
                                        "text": "A survey of church history with specific passages.",
                                        "sha256": "leaf-hash-1",
                                        "document_merkle_root": "root-hash-1",
                                        "merkle_proof": [{"position": "right", "hash": "sibling-hash"}],
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        if tool == "tree_traverse":
            return {
                "node_id": "doc-1:node-1",
                "paragraph_number": 3,
                "text": "A survey of church history with specific passages.",
            }
        if tool == "csl_render":
            return {"citation": "Aji Ap (2024). Church History. Journal of History. para. 3."}
        if tool == "memory_save":
            return {"status": "ok", "memory_id": params["memory_id"]}
        raise AssertionError(f"unexpected tool {tool}")

    result = _chat_via_tools(
        {"prompt": "church history", "thread_id": "thread-1", "top_k": 2},
        fake_tool,
    )

    assert [tool for tool, _params in calls] == [
        "search_memory",
        "tantivy_search",
        "tree_load",
        "tree_traverse",
        "csl_render",
        "memory_save",
    ]
    assert result["status"] == "ok"
    assert result["thread"] == "thread-1"
    assert result["answer_machine"]["evidence"][0]["node_id"] == "doc-1:node-1"
    assert result["answer_machine"]["evidence"][0]["section_path"] == "Section 1 / Overview"
    assert result["answer_machine"]["evidence"][0]["sha256"] == "leaf-hash-1"
    assert result["answer_machine"]["evidence"][0]["document_merkle_root"] == "root-hash-1"
    assert result["answer_machine"]["evidence"][0]["merkle_proof"][0]["hash"] == "sibling-hash"
    assert "Related Memory" in result["answer_human"]
    assert "para. 3" in result["answer_human"]
    assert result["kernel_memory_save"]["status"] == "ok"
    assert calls[-1][1]["evidence_node_ids"] == ["doc-1:node-1"]
