//! Tool: tree_traverse — Navigate to a specific node in a tree.

use super::{ToolContext, ToolError};

pub fn execute(
    params: &serde_json::Value,
    ctx: &mut ToolContext,
) -> Result<serde_json::Value, ToolError> {
    use crate::types::tree::PageIndexTree;

    let doc_id = params
        .get("doc_id")
        .and_then(|v| v.as_str())
        .ok_or_else(|| ToolError::InvalidParams {
            param: "doc_id".into(),
            message: "required string parameter".into(),
        })?;
    let node_id = params
        .get("node_id")
        .and_then(|v| v.as_str())
        .ok_or_else(|| ToolError::InvalidParams {
            param: "node_id".into(),
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

    let tree = PageIndexTree::load(&path)
        .map_err(|e| ToolError::IoError(format!("failed to load tree: {e}")))?;

    let found = tree.find_node(node_id).ok_or_else(|| ToolError::NotFound {
        resource_type: "tree node".into(),
        id: node_id.to_string(),
    })?;

    let node_json = match found {
        crate::types::tree::FoundNode::Section(n) => serde_json::to_value(n),
        crate::types::tree::FoundNode::Subsection(n) => serde_json::to_value(n),
        crate::types::tree::FoundNode::Locator(n) => serde_json::to_value(n),
        crate::types::tree::FoundNode::Line(n) => serde_json::to_value(n),
    }
    .map_err(|e| ToolError::IoError(format!("serialization error: {e}")))?;

    Ok(node_json)
}
