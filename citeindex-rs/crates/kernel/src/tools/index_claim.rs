//! Tool: index_claim — add claim to claim_index.

use super::{ToolContext, ToolError};

pub fn execute(
    params: &serde_json::Value,
    ctx: &mut ToolContext,
) -> Result<serde_json::Value, ToolError> {
    use tantivy::schema::Facet;

    let schema = ctx.claim_index.schema();

    let claim_id = params
        .get("claim_id")
        .and_then(|v| v.as_str())
        .ok_or_else(|| ToolError::InvalidParams {
            param: "claim_id".into(),
            message: "required".into(),
        })?;
    let doc_id = params
        .get("doc_id")
        .and_then(|v| v.as_str())
        .ok_or_else(|| ToolError::InvalidParams {
            param: "doc_id".into(),
            message: "required".into(),
        })?;
    let claim_text = params
        .get("claim_text")
        .and_then(|v| v.as_str())
        .ok_or_else(|| ToolError::InvalidParams {
            param: "claim_text".into(),
            message: "required".into(),
        })?;
    let section_ref = params
        .get("section_ref")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let polarity_tag = params
        .get("polarity_tag")
        .and_then(|v| v.as_str())
        .unwrap_or("neutral");
    let quality_tier = params
        .get("quality_tier")
        .and_then(|v| v.as_str())
        .unwrap_or("silver");
    let hierarchy_path = params
        .get("hierarchy_path")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let verified = params
        .get("verified")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    let merkle_hash = params
        .get("merkle_hash")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let language = params
        .get("language")
        .and_then(|v| v.as_str())
        .unwrap_or("en");

    let mut tantivy_doc = tantivy::TantivyDocument::new();

    macro_rules! add {
        ($name:expr, $val:expr) => {
            if let Ok(f) = schema.get_field($name) {
                tantivy_doc.add_text(f, $val);
            }
        };
    }

    add!("claim_id", claim_id);
    add!("doc_id", doc_id);
    add!("section_ref", section_ref);
    add!("claim_text", claim_text);
    add!("polarity_tag", polarity_tag);
    add!("quality_tier", quality_tier);
    add!("merkle_hash", merkle_hash);
    add!(&format!("claim_text_{language}"), claim_text);

    if let Some(entities) = params.get("entities").and_then(|v| v.as_array()) {
        for entity in entities {
            if let Some(e) = entity.as_str() {
                add!("entities", e);
            }
        }
    }

    if !hierarchy_path.is_empty() {
        if let Ok(f) = schema.get_field("hierarchy_path") {
            let fp = if hierarchy_path.starts_with('/') {
                hierarchy_path.to_string()
            } else {
                format!("/{hierarchy_path}")
            };
            tantivy_doc.add_facet(f, Facet::from(&fp));
        }
    }

    if let Ok(f) = schema.get_field("verified") {
        tantivy_doc.add_i64(f, if verified { 1 } else { 0 });
    }
    if let Ok(f) = schema.get_field("created_at") {
        tantivy_doc.add_date(
            f,
            tantivy::DateTime::from_timestamp_secs(chrono::Utc::now().timestamp()),
        );
    }

    let mut writer = ctx
        .claim_writer
        .lock()
        .map_err(|e| ToolError::IndexError(format!("lock: {e}")))?;
    writer
        .add_document(tantivy_doc)
        .map_err(|e| ToolError::IndexError(format!("add: {e}")))?;
    writer
        .commit()
        .map_err(|e| ToolError::IndexError(format!("commit: {e}")))?;

    Ok(serde_json::json!({"status": "ok", "claim_id": claim_id}))
}
