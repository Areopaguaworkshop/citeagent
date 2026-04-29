//! Tool: ag_query_contradictions — query contradiction edges from SQLite.

use super::{ToolContext, ToolError};

pub fn execute(
    params: &serde_json::Value,
    ctx: &mut ToolContext,
) -> Result<serde_json::Value, ToolError> {
    let conn = ctx
        .argument_graph_db
        .lock()
        .map_err(|e| ToolError::DatabaseError(format!("db lock: {e}")))?;

    let claim_id = params
        .get("claim_id")
        .and_then(|v| v.as_str())
        .ok_or_else(|| ToolError::InvalidParams {
            param: "claim_id".into(),
            message: "required string parameter".into(),
        })?;

    let edges = crate::argument_graph::query_contradictions(&conn, claim_id)
        .map_err(|e| ToolError::DatabaseError(format!("query: {e}")))?;

    let edge_values: Vec<serde_json::Value> = edges
        .iter()
        .map(|e| {
            serde_json::json!({
                "edge_id": e.edge_id,
                "claim_a_id": e.claim_a_id,
                "claim_b_id": e.claim_b_id,
                "explanation": e.explanation,
                "confidence": e.confidence,
                "detected_at": e.detected_at,
            })
        })
        .collect();

    Ok(serde_json::json!({
        "claim_id": claim_id,
        "total": edge_values.len(),
        "edges": edge_values,
    }))
}
