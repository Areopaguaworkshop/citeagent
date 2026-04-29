//! Tool: csl_render — Render a formatted citation string from CSL-JSON.

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
    let locator = params.get("locator").and_then(|v| v.as_str());

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

    let tree = crate::types::tree::PageIndexTree::load(&path)
        .map_err(|e| ToolError::IoError(format!("failed to load tree: {e}")))?;

    let l0 = &tree.level_0;
    let authors = tree.authors_display();
    let year = tree.year().map(|y| y.to_string()).unwrap_or_default();
    let title = &l0.title;
    let venue = l0.container_title.as_deref().unwrap_or("");
    let doi = l0.doi.as_deref().unwrap_or("");

    let mut citation = format!("{authors} ({year}). \"{title}.\"");
    if !venue.is_empty() {
        citation.push_str(&format!(" {venue}."));
    }
    if !doi.is_empty() {
        citation.push_str(&format!(" DOI: {doi}."));
    }
    if let Some(loc) = locator {
        citation.push_str(&format!(" {loc}."));
    }

    Ok(serde_json::json!({
        "citation": citation,
        "doc_id": doc_id,
    }))
}
