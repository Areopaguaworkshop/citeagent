//! Tool: merkle_compute — Compute SHA-256 hash of input data.

use super::{ToolContext, ToolError};

pub fn execute(
    params: &serde_json::Value,
    _ctx: &mut ToolContext,
) -> Result<serde_json::Value, ToolError> {
    use sha2::{Digest, Sha256};

    let data =
        params
            .get("data")
            .and_then(|v| v.as_str())
            .ok_or_else(|| ToolError::InvalidParams {
                param: "data".into(),
                message: "required string parameter".into(),
            })?;

    let hash = Sha256::digest(data.as_bytes());
    let hash_hex = format!("sha256:{}", hex::encode(hash));

    Ok(serde_json::json!({
        "hash": hash_hex,
    }))
}
