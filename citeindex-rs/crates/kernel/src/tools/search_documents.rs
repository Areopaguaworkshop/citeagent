//! Tool: search_documents — BM25 search over document_index with score fusion.

use super::{ToolContext, ToolError};

pub fn execute(
    params: &serde_json::Value,
    ctx: &mut ToolContext,
) -> Result<serde_json::Value, ToolError> {
    use tantivy::collector::TopDocs;
    use tantivy::query::QueryParser;
    use tantivy::schema::Value;

    let query_text = params
        .get("query")
        .and_then(|v| v.as_str())
        .ok_or_else(|| ToolError::InvalidParams {
            param: "query".into(),
            message: "required string parameter".into(),
        })?;
    let language = params
        .get("language")
        .and_then(|v| v.as_str())
        .unwrap_or("en");
    let limit = params.get("limit").and_then(|v| v.as_u64()).unwrap_or(20) as usize;

    let reader = ctx
        .document_index
        .reader()
        .map_err(|e| ToolError::IndexError(format!("failed to get reader: {e}")))?;
    let searcher = reader.searcher();
    let schema = ctx.document_index.schema();

    let title_field = format!("title_{language}");
    let abstract_field = format!("abstract_text_{language}");

    let mut search_fields = Vec::new();
    if let Ok(f) = schema.get_field(&title_field) {
        search_fields.push(f);
    }
    if let Ok(f) = schema.get_field(&abstract_field) {
        search_fields.push(f);
    }
    if let Ok(f) = schema.get_field("authors_en") {
        search_fields.push(f);
    }
    if let Ok(f) = schema.get_field("keywords") {
        search_fields.push(f);
    }

    if search_fields.is_empty() {
        return Ok(serde_json::json!({"total_hits": 0, "hits": []}));
    }

    let query_parser = QueryParser::for_index(&ctx.document_index, search_fields);
    let query = query_parser
        .parse_query(query_text)
        .map_err(|e| ToolError::InvalidParams {
            param: "query".into(),
            message: format!("parse error: {e}"),
        })?;

    let top_docs = searcher
        .search(&query, &TopDocs::with_limit(limit))
        .map_err(|e| ToolError::IndexError(format!("search failed: {e}")))?;

    let max_bm25 = top_docs.iter().map(|(s, _)| *s).fold(0.0f32, f32::max);
    let query_hierarchy = params.get("hierarchy_prefix").and_then(|v| v.as_str());

    let mut hits = Vec::new();
    for (raw_score, doc_address) in &top_docs {
        let doc: tantivy::TantivyDocument = searcher
            .doc(*doc_address)
            .map_err(|e| ToolError::IndexError(format!("doc retrieve: {e}")))?;

        let mut fields = serde_json::Map::new();
        for fv in doc.field_values() {
            let name = schema.get_field_name(fv.field);
            match name {
                "doc_id" | "title" | "authors" | "doi" | "abstract_text" | "venue" | "doc_type"
                | "quality_tier" | "language" | "merkle_hash" => {
                    if let Some(text) = (&fv.value).as_str() {
                        fields.insert(name.to_string(), serde_json::json!(text));
                    }
                }
                "year" => {
                    if let Some(n) = (&fv.value).as_i64() {
                        fields.insert(name.to_string(), serde_json::json!(n));
                    }
                }
                _ => {}
            }
        }

        let result_year = fields.get("year").and_then(|v| v.as_i64()).unwrap_or(2000);

        let (fused, breakdown) = crate::scoring::fuse_score(
            *raw_score,
            max_bm25,
            query_hierarchy,
            "",
            result_year,
            2026,
            0,
            0,
            0,
            0,
            &ctx.score_fusion_weights,
        );

        let doc_id = fields.get("doc_id").and_then(|v| v.as_str()).unwrap_or("");
        hits.push(serde_json::json!({
            "id": doc_id,
            "score": fused,
            "score_breakdown": {
                "bm25": breakdown.bm25,
                "hierarchy": breakdown.hierarchy,
                "citation_degree": breakdown.citation_degree,
                "recency": breakdown.recency,
                "claim_density": breakdown.claim_density,
            },
            "fields": fields,
        }));
    }

    Ok(serde_json::json!({
        "total_hits": hits.len(),
        "hits": hits,
    }))
}
