//! Tool: merkle_verify — Verify a hash matches data.

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
    let expected = params
        .get("expected_hash")
        .and_then(|v| v.as_str())
        .ok_or_else(|| ToolError::InvalidParams {
            param: "expected_hash".into(),
            message: "required string parameter".into(),
        })?;

    let hash = Sha256::digest(data.as_bytes());
    let computed = format!("sha256:{}", hex::encode(hash));
    let valid = computed == expected;

    Ok(serde_json::json!({
        "valid": valid,
        "computed_hash": computed,
        "expected_hash": expected,
    }))
}
