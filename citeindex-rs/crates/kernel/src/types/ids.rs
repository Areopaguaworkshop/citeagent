//! Strongly-typed IDs prevent accidental mixing of different ID domains.
//!
//! T_type_contracts.md — Common ID Types

use serde::{Deserialize, Serialize};
use std::fmt;
use uuid::Uuid;

/// SHA-256 hash used for document identification.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct DocId(pub [u8; 32]);

/// SHA-256 hash used for claim identification.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct ClaimId(pub [u8; 32]);

/// SHA-256 hash used for Merkle tree nodes.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct MerkleHash(pub [u8; 32]);

/// UUID for execution frames.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct FrameId(pub Uuid);

/// UUID for traces (groups multiple spans).
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct TraceId(pub Uuid);

/// UUID for query plans.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct PlanId(pub Uuid);

/// UUID for individual query nodes within a plan.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct QueryNodeId(pub Uuid);

/// UUID for projects.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct ProjectId(pub Uuid);

/// CSL-JSON record identifier (typically DOI or generated ID).
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct CslId(pub String);

/// Identifier for a context slot.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct SlotId(pub Uuid);

/// Identifier for a LoRA adapter version.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct LoraAdapterId(pub String);

/// Agent name (string-typed for registry flexibility).
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct AgentName(pub String);

/// Skill name.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct SkillName(pub String);

/// Model identifier (provider/model format, e.g., "anthropic/claude-sonnet-4-20250514").
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct ModelId(pub String);

/// Document/claim quality tier. Assigned at ingest, propagates to all derived data.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum QualityTier {
    /// Born-digital, high OCR confidence, DOI resolved.
    Gold,
    /// Moderate OCR confidence, partial reference extraction.
    Silver,
    /// Low confidence, blocked by default.
    Bronze,
}

// ── Display impls ──────────────────────────────────────────────

impl fmt::Display for DocId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "sha256:{}", hex::encode(self.0))
    }
}

impl fmt::Display for ClaimId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "sha256:{}", hex::encode(self.0))
    }
}

impl fmt::Display for MerkleHash {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "sha256:{}", hex::encode(self.0))
    }
}

impl fmt::Display for FrameId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl fmt::Display for AgentName {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl fmt::Display for SkillName {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl fmt::Display for ModelId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl fmt::Display for CslId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

// ── Constructor helpers ────────────────────────────────────────

impl MerkleHash {
    /// Compute a MerkleHash from raw bytes via SHA-256.
    pub fn from_bytes(data: &[u8]) -> Self {
        use sha2::{Digest, Sha256};
        let hash = Sha256::digest(data);
        let mut arr = [0u8; 32];
        arr.copy_from_slice(&hash);
        Self(arr)
    }

    /// Compute a MerkleHash from a UTF-8 string.
    pub fn from_str_content(s: &str) -> Self {
        Self::from_bytes(s.as_bytes())
    }

    /// All-zero hash (sentinel for "not yet computed").
    pub const ZERO: Self = Self([0u8; 32]);
}

impl FrameId {
    pub fn new() -> Self {
        Self(Uuid::new_v4())
    }
}

impl TraceId {
    pub fn new() -> Self {
        Self(Uuid::new_v4())
    }
}

impl PlanId {
    pub fn new() -> Self {
        Self(Uuid::new_v4())
    }
}

impl QueryNodeId {
    pub fn new() -> Self {
        Self(Uuid::new_v4())
    }
}

impl SlotId {
    pub fn new() -> Self {
        Self(Uuid::new_v4())
    }
}
