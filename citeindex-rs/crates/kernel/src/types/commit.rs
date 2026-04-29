//! T3 — CommitState (I3 enforcement)
//!
//! Invariant I3: Every COMMIT must produce a deterministic `commit_hash`.
//! `commit_hash` is non-optional. Compiler enforces.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

use super::claim::VerifiedClaim;
use super::common::CslRecord;
use super::ids::{FrameId, MerkleHash};

/// The result of a successful COMMIT transition.
/// `commit_hash` is NOT `Option` — it must always be present.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CommitState {
    /// sha256 of all committed claims.
    pub commit_hash: MerkleHash,
    pub frame_id: FrameId,
    /// Only `VerifiedClaim` — enforced by I1.
    pub committed_claims: Vec<VerifiedClaim>,
    /// Persisted CSL-JSON records.
    pub csl_citations: Vec<CslRecord>,
    pub committed_at: DateTime<Utc>,
    /// Snapshot of index state at commit time.
    pub index_merkle_root: MerkleHash,
}

/// Errors that prevent COMMIT from completing.
#[derive(Debug, thiserror::Error)]
pub enum CommitError {
    #[error("no verified claims to commit")]
    NoClaims,
    #[error("failed to compute commit hash: {0}")]
    HashComputationFailed(String),
    #[error("failed to persist CSL citations: {0}")]
    PersistenceFailed(String),
    #[error("merkle index update failed: {0}")]
    MerkleUpdateFailed(String),
}
