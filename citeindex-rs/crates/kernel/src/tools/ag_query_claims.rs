//! Tool: ag_query_claims — query claims from SQLite ArgumentGraph.

use super::{ToolContext, ToolError};

pub fn execute(
    params: &serde_json::Value,
    ctx: &mut ToolContext,
) -> Result<serde_json::Value, ToolError> {
    let conn = ctx
        .argument_graph_db
        .lock()
        .map_err(|e| ToolError::DatabaseError(format!("db lock: {e}")))?;

    if let Some(claim_id) = params.get("claim_id").and_then(|v| v.as_str()) {
        let mut stmt = conn
            .prepare(
                "SELECT claim_id, doc_id, claim_text, verbatim_passage, polarity_tag,
                    hierarchy_path, quality_tier, verified, section_ref, source_csl_id
             FROM claims WHERE claim_id = ?1",
            )
            .map_err(|e| ToolError::DatabaseError(format!("prepare: {e}")))?;

        let rows: Vec<serde_json::Value> = stmt
            .query_map(rusqlite::params![claim_id], |row| {
                Ok(serde_json::json!({
                    "claim_id": row.get::<_, String>(0)?,
                    "doc_id": row.get::<_, String>(1)?,
                    "claim_text": row.get::<_, String>(2)?,
                    "verbatim_passage": row.get::<_, String>(3)?,
                    "polarity_tag": row.get::<_, String>(4)?,
                    "hierarchy_path": row.get::<_, String>(5)?,
                    "quality_tier": row.get::<_, String>(6)?,
                    "verified": row.get::<_, i32>(7)? != 0,
                    "section_ref": row.get::<_, Option<String>>(8)?,
                    "source_csl_id": row.get::<_, Option<String>>(9)?,
                }))
            })
            .map_err(|e| ToolError::DatabaseError(format!("query: {e}")))?
            .filter_map(|r| r.ok())
            .collect();

        return Ok(serde_json::json!({"total": rows.len(), "claims": rows}));
    }

    if let Some(doc_id) = params.get("doc_id").and_then(|v| v.as_str()) {
        let mut stmt = conn
            .prepare(
                "SELECT claim_id, doc_id, claim_text, polarity_tag, quality_tier, verified
             FROM claims WHERE doc_id = ?1",
            )
            .map_err(|e| ToolError::DatabaseError(format!("prepare: {e}")))?;

        let rows: Vec<serde_json::Value> = stmt
            .query_map(rusqlite::params![doc_id], |row| {
                Ok(serde_json::json!({
                    "claim_id": row.get::<_, String>(0)?,
                    "doc_id": row.get::<_, String>(1)?,
                    "claim_text": row.get::<_, String>(2)?,
                    "polarity_tag": row.get::<_, String>(3)?,
                    "quality_tier": row.get::<_, String>(4)?,
                    "verified": row.get::<_, i32>(5)? != 0,
                }))
            })
            .map_err(|e| ToolError::DatabaseError(format!("query: {e}")))?
            .filter_map(|r| r.ok())
            .collect();

        return Ok(serde_json::json!({"total": rows.len(), "claims": rows}));
    }

    Err(ToolError::InvalidParams {
        param: "claim_id or doc_id".into(),
        message: "at least one query parameter required".into(),
    })
}
