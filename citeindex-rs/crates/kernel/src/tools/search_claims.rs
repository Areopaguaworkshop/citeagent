//! Tool: search_claims — BM25 search over claim_index with score fusion.

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
        .claim_index
        .reader()
        .map_err(|e| ToolError::IndexError(format!("failed to get reader: {e}")))?;
    let searcher = reader.searcher();
    let schema = ctx.claim_index.schema();

    let field_name = format!("claim_text_{language}");
    let mut search_fields = Vec::new();
    if let Ok(f) = schema.get_field(&field_name) {
        search_fields.push(f);
    }

    if search_fields.is_empty() {
        return Ok(serde_json::json!({"total_hits": 0, "hits": []}));
    }

    let query_parser = QueryParser::for_index(&ctx.claim_index, search_fields);
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

    let mut hits = Vec::new();
    for (raw_score, doc_address) in &top_docs {
        let doc: tantivy::TantivyDocument = searcher
            .doc(*doc_address)
            .map_err(|e| ToolError::IndexError(format!("doc retrieve: {e}")))?;

        let mut fields = serde_json::Map::new();
        for fv in doc.field_values() {
            let name = schema.get_field_name(fv.field);
            match name {
                "claim_id" | "doc_id" | "section_ref" | "claim_text" | "polarity_tag"
                | "entities" | "quality_tier" | "merkle_hash" => {
                    if let Some(text) = (&fv.value).as_str() {
                        fields.insert(name.to_string(), serde_json::json!(text));
                    }
                }
                "verified" => {
                    if let Some(n) = (&fv.value).as_i64() {
                        fields.insert(name.to_string(), serde_json::json!(n != 0));
                    }
                }
                _ => {}
            }
        }

        let bm25_norm = crate::scoring::normalize_bm25(*raw_score, max_bm25);
        let claim_id = fields
            .get("claim_id")
            .and_then(|v| v.as_str())
            .unwrap_or("");

        hits.push(serde_json::json!({
            "id": claim_id,
            "score": bm25_norm,
            "score_breakdown": {"bm25": bm25_norm},
            "fields": fields,
        }));
    }

    Ok(serde_json::json!({
        "total_hits": hits.len(),
        "hits": hits,
    }))
}
