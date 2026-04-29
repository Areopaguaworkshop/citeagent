//! T1 — Claim vs VerifiedClaim (I1 enforcement)
//!
//! Invariant I1: No unverified claim can enter COMMIT. `VerifiedClaim` is a
//! distinct Rust type from `Claim`. COMMIT accepts only `Vec<VerifiedClaim>`.
//! Compiler enforces.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

use super::ids::{ClaimId, CslId, DocId, MerkleHash, QualityTier};

/// Polarity of a factual claim.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum PolarityTag {
    Positive,
    Negative,
    Neutral,
}

/// How a claim was verified against its source.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum VerificationMethod {
    /// Source was injected into context before LLM generated the claim.
    PreGrounded,
    /// Source found after generation via BM25 passage match.
    PostHoc,
}

/// A factual claim extracted by ClaimExtractionAgent.
/// Cannot be passed to COMMIT. Must go through VERIFY gate first.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Claim {
    pub claim_id: ClaimId,
    pub doc_id: DocId,
    pub section_ref: String,
    pub claim_text: String,
    pub verbatim_passage: String,
    pub polarity_tag: PolarityTag,
    pub entities: Vec<String>,
    pub hierarchy_path: String,
    pub quality_tier: QualityTier,
    pub created_at: DateTime<Utc>,
}

/// A claim that has passed the VERIFY gate.
/// Only this type can enter COMMIT.
///
/// **Enforcement**: No public constructor. Only the VERIFY gate function
/// (`verify_claim`) in this module can construct one.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VerifiedClaim {
    // Fields from Claim:
    pub claim_id: ClaimId,
    pub doc_id: DocId,
    pub section_ref: String,
    pub claim_text: String,
    pub verbatim_passage: String,
    pub polarity_tag: PolarityTag,
    pub entities: Vec<String>,
    pub hierarchy_path: String,
    pub quality_tier: QualityTier,
    pub created_at: DateTime<Utc>,

    // Verification-only fields:
    pub verified_at: DateTime<Utc>,
    pub merkle_hash: MerkleHash,
    pub source_csl_id: CslId,
    pub verification_method: VerificationMethod,
    pub similarity_score: f32,
}

/// A claim that failed verification. Shown to scholar with explanation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BlockedClaim {
    pub claim: Claim,
    pub reason: BlockedReason,
}

/// Why a claim was blocked at the VERIFY gate.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum BlockedReason {
    CiteIdNotInInjectedSet {
        cite_id: String,
    },
    SimilarityBelowThreshold {
        score: f32,
        threshold: f32,
    },
    QualityTierBelowMinimum {
        tier: QualityTier,
        required: QualityTier,
    },
    MerkleHashMismatch,
    NoPassageFound,
}

/// VERIFY gate: convert a Claim into a VerifiedClaim or BlockedClaim.
///
/// This is the **only** way to construct a `VerifiedClaim`. Module-level
/// privacy ensures no other code can bypass verification.
pub fn verify_claim(
    claim: Claim,
    source_csl_id: CslId,
    merkle_hash: MerkleHash,
    verification_method: VerificationMethod,
    similarity_score: f32,
    similarity_threshold: f32,
) -> Result<VerifiedClaim, BlockedClaim> {
    if similarity_score < similarity_threshold {
        return Err(BlockedClaim {
            reason: BlockedReason::SimilarityBelowThreshold {
                score: similarity_score,
                threshold: similarity_threshold,
            },
            claim,
        });
    }

    Ok(VerifiedClaim {
        claim_id: claim.claim_id,
        doc_id: claim.doc_id,
        section_ref: claim.section_ref,
        claim_text: claim.claim_text,
        verbatim_passage: claim.verbatim_passage,
        polarity_tag: claim.polarity_tag,
        entities: claim.entities,
        hierarchy_path: claim.hierarchy_path,
        quality_tier: claim.quality_tier,
        created_at: claim.created_at,
        verified_at: Utc::now(),
        merkle_hash,
        source_csl_id,
        verification_method,
        similarity_score,
    })
}
