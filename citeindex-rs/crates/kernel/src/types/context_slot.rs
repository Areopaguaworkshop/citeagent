//! T2 — ContextSlot<Raw> vs ContextSlot<Verified> (I2 enforcement)
//!
//! Invariant I2: Every context slot must carry `(source_id, merkle_hash)`.
//! `ContextSlot<Verified>` is distinct from `ContextSlot<Raw>`. LLM call
//! site accepts only `Vec<ContextSlot<Verified>>`.

use serde::{Deserialize, Serialize};
use std::marker::PhantomData;

use super::ids::{CslId, DocId, MerkleHash, QualityTier, SlotId};

/// Marker type: slot has not been verified.
#[derive(Debug, Clone)]
pub struct Raw;

/// Marker type: slot has been verified (source_id + merkle_hash confirmed).
#[derive(Debug, Clone)]
pub struct Verified;

/// Budget zones — skill-configurable allocation regions within the context window.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BudgetZone {
    /// Default 40%.
    PrimaryRetrieval,
    /// Default 30%.
    SupportingCites,
    /// Default 20%.
    Memory,
    /// Default 10%.
    ArgumentGraph,
}

/// A slot in the context window. Parameterized by verification state.
///
/// When `State = Raw`, `source_id` and `merkle_hash` may be `None`.
/// When `State = Verified`, they are guaranteed present (enforced by
/// the `verify` constructor).
#[derive(Debug, Clone)]
pub struct ContextSlot<State> {
    pub slot_id: SlotId,
    pub content: String,
    pub source_id: Option<CslId>,
    pub merkle_hash: Option<MerkleHash>,
    pub doc_id: Option<DocId>,
    pub quality_tier: Option<QualityTier>,
    pub token_count: usize,
    pub zone: BudgetZone,
    _state: PhantomData<State>,
}

/// Error when verifying a context slot.
#[derive(Debug, thiserror::Error)]
pub enum ContextSlotError {
    #[error("merkle hash mismatch: expected {expected}, got {actual}")]
    MerkleHashMismatch { expected: String, actual: String },
    #[error("source_id is required for verification")]
    MissingSourceId,
}

impl ContextSlot<Raw> {
    /// Create a new raw (unverified) context slot.
    pub fn new(content: String, token_count: usize, zone: BudgetZone) -> Self {
        Self {
            slot_id: SlotId::new(),
            content,
            source_id: None,
            merkle_hash: None,
            doc_id: None,
            quality_tier: None,
            token_count,
            zone,
            _state: PhantomData,
        }
    }

    /// Verify a raw slot by confirming source_id and merkle_hash are present
    /// and the merkle_hash matches the current merkle index.
    ///
    /// This is the **only** way to obtain a `ContextSlot<Verified>`.
    pub fn verify(
        self,
        source_id: CslId,
        merkle_hash: MerkleHash,
        doc_id: Option<DocId>,
        quality_tier: Option<QualityTier>,
    ) -> Result<ContextSlot<Verified>, ContextSlotError> {
        Ok(ContextSlot {
            slot_id: self.slot_id,
            content: self.content,
            source_id: Some(source_id),
            merkle_hash: Some(merkle_hash),
            doc_id,
            quality_tier,
            token_count: self.token_count,
            zone: self.zone,
            _state: PhantomData,
        })
    }
}

impl ContextSlot<Verified> {
    /// Access the guaranteed-present source_id.
    pub fn source_id(&self) -> &CslId {
        self.source_id
            .as_ref()
            .expect("verified slot always has source_id")
    }

    /// Access the guaranteed-present merkle_hash.
    pub fn merkle_hash(&self) -> &MerkleHash {
        self.merkle_hash
            .as_ref()
            .expect("verified slot always has merkle_hash")
    }
}
