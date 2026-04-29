//! Tool: delete_document — remove document from document_index.

use super::{ToolContext, ToolError};

pub fn execute(
    params: &serde_json::Value,
    ctx: &mut ToolContext,
) -> Result<serde_json::Value, ToolError> {
    let doc_id = params
        .get("doc_id")
        .and_then(|v| v.as_str())
        .ok_or_else(|| ToolError::InvalidParams {
            param: "doc_id".into(),
            message: "required".into(),
        })?;

    let schema = ctx.document_index.schema();
    let field = schema
        .get_field("doc_id")
        .map_err(|_| ToolError::IndexError("doc_id field not in schema".into()))?;

    let mut writer = ctx
        .document_writer
        .lock()
        .map_err(|e| ToolError::IndexError(format!("lock: {e}")))?;
    writer.delete_term(tantivy::Term::from_field_text(field, doc_id));
    writer
        .commit()
        .map_err(|e| ToolError::IndexError(format!("commit: {e}")))?;

    Ok(serde_json::json!({"status": "ok", "doc_id": doc_id, "deleted": true}))
}
