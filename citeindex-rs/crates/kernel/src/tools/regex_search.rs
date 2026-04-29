//! Tool: regex_search — Regex search across document text.

use super::{ToolContext, ToolError};

pub fn execute(
    params: &serde_json::Value,
    ctx: &mut ToolContext,
) -> Result<serde_json::Value, ToolError> {
    use regex::Regex;

    let pattern = params
        .get("pattern")
        .and_then(|v| v.as_str())
        .ok_or_else(|| ToolError::InvalidParams {
            param: "pattern".into(),
            message: "required string parameter".into(),
        })?;
    let case_sensitive = params
        .get("case_sensitive")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    let max_matches = params
        .get("max_matches")
        .and_then(|v| v.as_u64())
        .unwrap_or(50) as usize;
    let context_chars = params
        .get("context_chars")
        .and_then(|v| v.as_u64())
        .unwrap_or(100) as usize;

    let regex_pattern = if case_sensitive {
        pattern.to_string()
    } else {
        format!("(?i){pattern}")
    };

    let re = Regex::new(&regex_pattern).map_err(|e| ToolError::InvalidParams {
        param: "pattern".into(),
        message: format!("invalid regex: {e}"),
    })?;

    let structured_dir = ctx.documents_dir.join("structured");
    let mut matches = Vec::new();

    if structured_dir.exists() {
        let entries = std::fs::read_dir(&structured_dir)
            .map_err(|e| ToolError::IoError(format!("failed to read structured dir: {e}")))?;

        for entry in entries {
            if matches.len() >= max_matches {
                break;
            }
            let entry = entry.map_err(|e| ToolError::IoError(e.to_string()))?;
            let path = entry.path();
            if path.extension().and_then(|e| e.to_str()) != Some("json") {
                continue;
            }

            let tree = match crate::types::tree::PageIndexTree::load(&path) {
                Ok(t) => t,
                Err(_) => continue,
            };

            let doc_id = tree.level_0.ci_doc_id.clone().unwrap_or_default();

            for (node_id, text) in tree.all_text() {
                if matches.len() >= max_matches {
                    break;
                }
                for m in re.find_iter(&text) {
                    if matches.len() >= max_matches {
                        break;
                    }
                    let start = m.start().saturating_sub(context_chars);
                    let end = (m.end() + context_chars).min(text.len());
                    let context_before = &text[start..m.start()];
                    let context_after = &text[m.end()..end];

                    matches.push(serde_json::json!({
                        "doc_id": doc_id,
                        "node_id": node_id,
                        "match_text": m.as_str(),
                        "context_before": context_before,
                        "context_after": context_after,
                    }));
                }
            }
        }
    }

    Ok(serde_json::json!({
        "total_matches": matches.len(),
        "matches": matches,
    }))
}
