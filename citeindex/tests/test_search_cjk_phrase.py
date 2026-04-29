from citeindex.agents.indexing import IndexingAgent
from citeindex.agents.query_planner import QueryPlanner
from citeindex.agents.retrieval import RetrievalAgent


def _make_node(node_id: str, text: str, page: int = 1) -> dict:
    return {
        "node_id": node_id,
        "source_id": "src-1",
        "section_path": f"p{page}",
        "sha256": f"sha-{node_id}",
        "text": text,
        "page": page,
    }


def test_query_planner_infers_exact_phrase_for_unquoted_cjk_query() -> None:
    plan = QueryPlanner().plan("科学发掘之前的历次盗掘")

    assert plan.exact_phrases == ["科学发掘之前的历次盗掘"]


def test_retrieval_uses_phrase_fallback_for_unquoted_cjk_query() -> None:
    nodes = [
        _make_node(
            "n-match",
            "在2021 年科学发掘之前的历次盗掘中，值得注意的是1905 年6 月第二支德国吐鲁番考察队的盗掘。",
            page=75,
        ),
        _make_node("n-other", "本段落讨论考古发掘与遗址建筑布局。", page=76),
    ]
    inverted_index = IndexingAgent().run(nodes).inverted_index
    plan = QueryPlanner().plan("科学发掘之前的历次盗掘").to_dict()

    result = RetrievalAgent(top_k=10).run(plan, nodes, inverted_index)

    assert [node["node_id"] for node in result.ranked_nodes] == ["n-match"]
    assert result.ranked_nodes[0]["score_breakdown"]["phrase_boost"] == 5.0
    assert result.retrieval_debug["returned"] == 1


def test_retrieval_does_not_return_zero_score_fillers() -> None:
    nodes = [
        _make_node("n1", "甲文内容", page=1),
        _make_node("n2", "乙文内容", page=2),
    ]
    inverted_index = IndexingAgent().run(nodes).inverted_index
    query_plan = {
        "query_id": "q-test",
        "must_filters": [],
        "search_terms": ["完全不存在的词"],
        "exact_phrases": [],
        "section_targets": [],
    }

    result = RetrievalAgent(top_k=10).run(query_plan, nodes, inverted_index)

    assert result.ranked_nodes == []
    assert result.retrieval_debug["after_bm25"] == 0
    assert result.retrieval_debug["returned"] == 0
