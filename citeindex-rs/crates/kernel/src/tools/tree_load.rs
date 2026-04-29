//! Tool: tree_load — Load a PageIndex tree from disk.

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
            message: "required string parameter".into(),
        })?;

    let filename = if let Some(stripped) = doc_id.strip_prefix("sha256:") {
        format!("{stripped}.citeindex.json")
    } else {
        format!("{doc_id}.citeindex.json")
    };

    let path = ctx.documents_dir.join("structured").join(&filename);

    if !path.exists() {
        return Err(ToolError::NotFound {
            resource_type: "document tree".into(),
            id: doc_id.to_string(),
        });
    }

    let content = std::fs::read_to_string(&path)
        .map_err(|e| ToolError::IoError(format!("failed to read {}: {e}", path.display())))?;

    let tree: serde_json::Value = serde_json::from_str(&content)
        .map_err(|e| ToolError::IoError(format!("invalid JSON in {}: {e}", path.display())))?;

    Ok(tree)
}
