//! Tool: index_document — add/update document in document_index.

use super::{ToolContext, ToolError};

pub fn execute(
    params: &serde_json::Value,
    ctx: &mut ToolContext,
) -> Result<serde_json::Value, ToolError> {
    use tantivy::schema::Facet;

    let schema = ctx.document_index.schema();

    let doc_id = params
        .get("doc_id")
        .and_then(|v| v.as_str())
        .ok_or_else(|| ToolError::InvalidParams {
            param: "doc_id".into(),
            message: "required".into(),
        })?;
    let title = params.get("title").and_then(|v| v.as_str()).unwrap_or("");
    let authors = params.get("authors").and_then(|v| v.as_str()).unwrap_or("");
    let year = params.get("year").and_then(|v| v.as_i64()).unwrap_or(0);
    let doi = params.get("doi").and_then(|v| v.as_str()).unwrap_or("");
    let abstract_text = params
        .get("abstract_text")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let venue = params.get("venue").and_then(|v| v.as_str()).unwrap_or("");
    let doc_type = params
        .get("doc_type")
        .and_then(|v| v.as_str())
        .unwrap_or("article-journal");
    let quality_tier = params
        .get("quality_tier")
        .and_then(|v| v.as_str())
        .unwrap_or("silver");
    let hierarchy_path = params
        .get("hierarchy_path")
        .and_then(|v| v.as_str())
        .unwrap_or("");
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

    add!("doc_id", doc_id);
    add!("title", title);
    add!("authors", authors);
    add!("doi", doi);
    add!("abstract_text", abstract_text);
    add!("venue", venue);
    add!("doc_type", doc_type);
    add!("quality_tier", quality_tier);
    add!("merkle_hash", merkle_hash);
    add!("language", language);

    // Language-suffixed fields
    add!(&format!("title_{language}"), title);
    add!(&format!("abstract_text_{language}"), abstract_text);
    add!("authors_en", authors);

    if let Ok(f) = schema.get_field("year") {
        tantivy_doc.add_i64(f, year);
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

    if let Ok(f) = schema.get_field("indexed_at") {
        tantivy_doc.add_date(
            f,
            tantivy::DateTime::from_timestamp_secs(chrono::Utc::now().timestamp()),
        );
    }

    let mut writer = ctx
        .document_writer
        .lock()
        .map_err(|e| ToolError::IndexError(format!("lock: {e}")))?;

    // Upsert: delete existing doc with same doc_id first
    if let Ok(f) = schema.get_field("doc_id") {
        writer.delete_term(tantivy::Term::from_field_text(f, doc_id));
    }

    writer
        .add_document(tantivy_doc)
        .map_err(|e| ToolError::IndexError(format!("add: {e}")))?;
    writer
        .commit()
        .map_err(|e| ToolError::IndexError(format!("commit: {e}")))?;

    Ok(serde_json::json!({"status": "ok", "doc_id": doc_id}))
}
