//! Tool: ag_write_edge — insert contradiction edge into SQLite.

use super::{ToolContext, ToolError};

pub fn execute(
    params: &serde_json::Value,
    ctx: &mut ToolContext,
) -> Result<serde_json::Value, ToolError> {
    let conn = ctx
        .argument_graph_db
        .lock()
        .map_err(|e| ToolError::DatabaseError(format!("db lock: {e}")))?;

    let edge_id = params
        .get("edge_id")
        .and_then(|v| v.as_str())
        .ok_or_else(|| ToolError::InvalidParams {
            param: "edge_id".into(),
            message: "required".into(),
        })?;
    let claim_a_id = params
        .get("claim_a_id")
        .and_then(|v| v.as_str())
        .ok_or_else(|| ToolError::InvalidParams {
            param: "claim_a_id".into(),
            message: "required".into(),
        })?;
    let claim_b_id = params
        .get("claim_b_id")
        .and_then(|v| v.as_str())
        .ok_or_else(|| ToolError::InvalidParams {
            param: "claim_b_id".into(),
            message: "required".into(),
        })?;
    let explanation = params
        .get("explanation")
        .and_then(|v| v.as_str())
        .ok_or_else(|| ToolError::InvalidParams {
            param: "explanation".into(),
            message: "required".into(),
        })?;
    let confidence = params.get("confidence").and_then(|v| v.as_f64());
    let frame_id = params.get("frame_id").and_then(|v| v.as_str());

    crate::argument_graph::insert_edge(
        &conn,
        edge_id,
        claim_a_id,
        claim_b_id,
        explanation,
        confidence,
        frame_id,
    )
    .map_err(|e| ToolError::DatabaseError(format!("insert: {e}")))?;

    Ok(serde_json::json!({"status": "ok", "edge_id": edge_id}))
}
