//! Tool: memory_save — save memory node to memory_index.

use std::fs;
use std::io::Write;

use super::{MemoryAccessEntry, ToolContext, ToolError};

#[derive(serde::Serialize)]
struct SessionMemoryEntry {
    entry_id: String,
    timestamp: String,
    thread_id: String,
    query: String,
    response: String,
    evidence_node_ids: Vec<String>,
    sha256: String,
}

fn default_timestamp() -> String {
    chrono::Utc::now()
        .format("%Y-%m-%dT%H:%M:%S+00:00")
        .to_string()
}

fn compute_session_hash(timestamp: &str, query: &str, response: &str) -> String {
    use sha2::{Digest, Sha256};

    let payload = format!("{timestamp}|{query}|{response}");
    let mut hasher = Sha256::new();
    hasher.update(payload.as_bytes());
    format!("{:x}", hasher.finalize())
}

fn safe_session_filename(session_id: &str) -> String {
    session_id
        .chars()
        .map(|ch| {
            if ch.is_alphanumeric() || ch == '-' || ch == '_' {
                ch
            } else {
                '_'
            }
        })
        .collect()
}

fn persist_session_entry(
    ctx: &ToolContext,
    memory_id: &str,
    session_id: &str,
    title: &str,
    content: &str,
    timestamp: &str,
    evidence_node_ids: Vec<String>,
    sha256: &str,
) -> Result<(), ToolError> {
    let Some(session_dir) = ctx.memory_sessions_dir.as_ref() else {
        return Ok(());
    };

    fs::create_dir_all(session_dir)
        .map_err(|e| ToolError::IoError(format!("create session dir: {e}")))?;
    let session_path = session_dir.join(format!("{}.jsonl", safe_session_filename(session_id)));

    let mut retained_lines = Vec::new();
    if session_path.exists() {
        let existing = fs::read_to_string(&session_path)
            .map_err(|e| ToolError::IoError(format!("read {}: {e}", session_path.display())))?;
        for line in existing.lines() {
            let trimmed = line.trim();
            if trimmed.is_empty() {
                continue;
            }

            let existing_entry_id = serde_json::from_str::<serde_json::Value>(trimmed)
                .ok()
                .and_then(|value| {
                    value
                        .get("entry_id")
                        .and_then(|value| value.as_str())
                        .map(str::to_string)
                });
            if existing_entry_id.as_deref() == Some(memory_id) {
                continue;
            }

            retained_lines.push(trimmed.to_string());
        }
    }

    let entry = SessionMemoryEntry {
        entry_id: memory_id.to_string(),
        timestamp: timestamp.to_string(),
        thread_id: session_id.to_string(),
        query: title.to_string(),
        response: content.to_string(),
        evidence_node_ids,
        sha256: sha256.to_string(),
    };
    retained_lines.push(
        serde_json::to_string(&entry)
            .map_err(|e| ToolError::IoError(format!("serialize session entry: {e}")))?,
    );

    let mut file = fs::File::create(&session_path)
        .map_err(|e| ToolError::IoError(format!("write {}: {e}", session_path.display())))?;
    for line in retained_lines {
        writeln!(file, "{line}")
            .map_err(|e| ToolError::IoError(format!("write {}: {e}", session_path.display())))?;
    }

    Ok(())
}

pub fn execute(
    params: &serde_json::Value,
    ctx: &mut ToolContext,
) -> Result<serde_json::Value, ToolError> {
    use tantivy::schema::Facet;

    let schema = ctx.memory_index.schema();

    let memory_id = params
        .get("memory_id")
        .and_then(|v| v.as_str())
        .ok_or_else(|| ToolError::InvalidParams {
            param: "memory_id".into(),
            message: "required".into(),
        })?;
    let session_id = params
        .get("session_id")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let title = params.get("title").and_then(|v| v.as_str()).unwrap_or("");
    let description = params
        .get("description")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let content = params.get("content").and_then(|v| v.as_str()).unwrap_or("");
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
    let timestamp = params
        .get("timestamp")
        .and_then(|v| v.as_str())
        .filter(|value| !value.is_empty())
        .map(str::to_string)
        .unwrap_or_else(default_timestamp);
    let evidence_node_ids = params
        .get("evidence_node_ids")
        .and_then(|v| v.as_array())
        .map(|items| {
            items
                .iter()
                .filter_map(|item| item.as_str().map(str::to_string))
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    let sha256 = params
        .get("sha256")
        .and_then(|v| v.as_str())
        .filter(|value| !value.is_empty())
        .map(str::to_string)
        .unwrap_or_else(|| compute_session_hash(&timestamp, title, content));

    let mut tantivy_doc = tantivy::TantivyDocument::new();

    macro_rules! add {
        ($name:expr, $val:expr) => {
            if let Ok(f) = schema.get_field($name) {
                tantivy_doc.add_text(f, $val);
            }
        };
    }

    add!("memory_id", memory_id);
    add!("session_id", session_id);
    add!("title", title);
    add!("description", description);
    add!("content", content);
    add!("merkle_hash", merkle_hash);
    add!(&format!("title_{language}"), title);
    add!(&format!("description_{language}"), description);
    add!(&format!("content_{language}"), content);

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

    if let Ok(f) = schema.get_field("created_at") {
        tantivy_doc.add_date(
            f,
            tantivy::DateTime::from_timestamp_secs(chrono::Utc::now().timestamp()),
        );
    }

    let mut writer = ctx
        .memory_writer
        .lock()
        .map_err(|e| ToolError::IndexError(format!("lock: {e}")))?;

    // Upsert so legacy bootstrap or repeated chat saves do not accumulate
    // duplicate rows for the same logical memory node.
    if let Ok(f) = schema.get_field("memory_id") {
        writer.delete_term(tantivy::Term::from_field_text(f, memory_id));
    }

    writer
        .add_document(tantivy_doc)
        .map_err(|e| ToolError::IndexError(format!("add: {e}")))?;
    writer
        .commit()
        .map_err(|e| ToolError::IndexError(format!("commit: {e}")))?;

    persist_session_entry(
        ctx,
        memory_id,
        session_id,
        title,
        content,
        &timestamp,
        evidence_node_ids,
        &sha256,
    )?;

    let now = chrono::Utc::now().to_rfc3339();
    ctx.memory_access_cache.insert(
        memory_id.to_string(),
        MemoryAccessEntry {
            access_count: 0,
            last_accessed: now.clone(),
        },
    );

    Ok(serde_json::json!({"status": "ok", "memory_id": memory_id, "indexed_at": now}))
}

#[cfg(test)]
mod tests {
    use std::env;
    use std::path::PathBuf;

    use super::*;
    use crate::storage::StorageLayout;

    #[test]
    fn test_memory_save_upserts_existing_memory_id() {
        let mut ctx = crate::tools::in_memory_context(PathBuf::from("unused-documents")).unwrap();
        let params = serde_json::json!({
            "memory_id": "mem-1",
            "session_id": "thread-1",
            "title": "Church History",
            "description": "Earlier answer",
            "content": "Church history spans several centuries.",
            "language": "en",
        });

        execute(&params, &mut ctx).unwrap();
        execute(&params, &mut ctx).unwrap();

        let result = crate::tools::search_memory::execute(
            &serde_json::json!({
                "query": "church history",
                "language": "en",
                "limit": 10,
            }),
            &mut ctx,
        )
        .unwrap();

        assert_eq!(result["total_hits"], 1);
    }

    #[test]
    fn test_memory_save_persists_session_log() {
        let root = env::temp_dir().join(format!("citeindex-memory-save-{}", uuid::Uuid::new_v4()));
        let layout = StorageLayout::new(root.clone());
        let mut ctx = crate::tools::persistent_context(&layout).unwrap();
        let params = serde_json::json!({
            "memory_id": "mem-2",
            "session_id": "thread-2",
            "title": "Query",
            "description": "desc",
            "content": "Answer",
            "language": "en",
            "timestamp": "2026-04-03T12:00:00+00:00",
            "evidence_node_ids": ["doc-1:node-1"],
            "sha256": "legacy-sha",
        });

        execute(&params, &mut ctx).unwrap();

        let session_path = layout.sessions_dir.join("thread-2.jsonl");
        let content = fs::read_to_string(&session_path).unwrap();
        let line = content.lines().next().unwrap();
        let value: serde_json::Value = serde_json::from_str(line).unwrap();

        assert_eq!(value["entry_id"], "mem-2");
        assert_eq!(value["thread_id"], "thread-2");
        assert_eq!(value["query"], "Query");
        assert_eq!(value["response"], "Answer");
        assert_eq!(value["evidence_node_ids"][0], "doc-1:node-1");
        assert_eq!(value["sha256"], "legacy-sha");

        fs::remove_dir_all(root).unwrap();
    }
}
