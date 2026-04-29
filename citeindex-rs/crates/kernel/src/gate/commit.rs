//! COMMIT gate — produce a CommitState with deterministic commit_hash.
//!
//! Invariant I3: Every COMMIT must produce a deterministic `commit_hash`.
//! The hash is sha256 of all verified claim IDs + texts, sorted canonically.

use chrono::Utc;
use sha2::{Digest, Sha256};

use crate::types::claim::VerifiedClaim;
use crate::types::commit::{CommitError, CommitState};
use crate::types::common::CslRecord;
use crate::types::ids::{FrameId, MerkleHash};

/// Execute the COMMIT gate: hash verified claims and produce CommitState.
///
/// This is the **only** way to produce a `CommitState`. The commit_hash
/// is deterministic given the same set of verified claims.
pub fn commit_output(
    frame_id: FrameId,
    verified_claims: Vec<VerifiedClaim>,
    csl_citations: Vec<CslRecord>,
    index_merkle_root: MerkleHash,
) -> Result<CommitState, CommitError> {
    if verified_claims.is_empty() {
        return Err(CommitError::NoClaims);
    }

    let commit_hash = compute_commit_hash(&verified_claims)?;

    Ok(CommitState {
        commit_hash,
        frame_id,
        committed_claims: verified_claims,
        csl_citations,
        committed_at: Utc::now(),
        index_merkle_root,
    })
}

/// Compute the deterministic commit hash from verified claims.
///
/// Algorithm: sort claim IDs canonically, concatenate claim_id + claim_text,
/// compute sha256 of the concatenated string.
fn compute_commit_hash(claims: &[VerifiedClaim]) -> Result<MerkleHash, CommitError> {
    let mut sorted_claims: Vec<&VerifiedClaim> = claims.iter().collect();
    sorted_claims.sort_by(|a, b| a.claim_id.0.cmp(&b.claim_id.0));

    let mut hasher = Sha256::new();
    for claim in &sorted_claims {
        hasher.update(&claim.claim_id.0);
        hasher.update(claim.claim_text.as_bytes());
    }

    let hash = hasher.finalize();
    let mut arr = [0u8; 32];
    arr.copy_from_slice(&hash);
    Ok(MerkleHash(arr))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::claim::{PolarityTag, VerificationMethod};
    use crate::types::ids::{ClaimId, CslId, DocId, QualityTier};

    fn make_verified_claim(text: &str, id_byte: u8) -> VerifiedClaim {
        VerifiedClaim {
            claim_id: ClaimId([id_byte; 32]),
            doc_id: DocId([0u8; 32]),
            section_ref: "Test".into(),
            claim_text: text.into(),
            verbatim_passage: "passage".into(),
            polarity_tag: PolarityTag::Positive,
            entities: vec![],
            hierarchy_path: "/test".into(),
            quality_tier: QualityTier::Gold,
            created_at: Utc::now(),
            verified_at: Utc::now(),
            merkle_hash: MerkleHash::ZERO,
            source_csl_id: CslId("src".into()),
            verification_method: VerificationMethod::PreGrounded,
            similarity_score: 0.8,
        }
    }

    #[test]
    fn test_commit_output_success() {
        let claims = vec![
            make_verified_claim("claim 1", 1),
            make_verified_claim("claim 2", 2),
        ];
        let csl = vec![CslRecord {
            id: "test".into(),
            csl_type: "article-journal".into(),
            title: Some("Test".into()),
            author: None,
            issued: None,
            doi: None,
            container_title: None,
            extra: serde_json::Value::Null,
        }];

        let result = commit_output(FrameId::new(), claims, csl, MerkleHash::ZERO);
        assert!(result.is_ok());
        let state = result.unwrap();
        assert_eq!(state.committed_claims.len(), 2);
        assert_eq!(state.csl_citations.len(), 1);
        assert_ne!(state.commit_hash, MerkleHash::ZERO);
    }

    #[test]
    fn test_commit_output_no_claims() {
        let result = commit_output(FrameId::new(), vec![], vec![], MerkleHash::ZERO);
        assert!(matches!(result, Err(CommitError::NoClaims)));
    }

    #[test]
    fn test_commit_hash_deterministic() {
        let claims = vec![
            make_verified_claim("claim A", 1),
            make_verified_claim("claim B", 2),
        ];
        let hash1 = compute_commit_hash(&claims).unwrap();
        let hash2 = compute_commit_hash(&claims).unwrap();
        assert_eq!(hash1, hash2);
    }

    #[test]
    fn test_commit_hash_order_independent() {
        let c1 = make_verified_claim("claim A", 1);
        let c2 = make_verified_claim("claim B", 2);

        let hash_ab = compute_commit_hash(&[c1.clone(), c2.clone()]).unwrap();
        let hash_ba = compute_commit_hash(&[c2, c1]).unwrap();
        // Both should produce same hash (sorted canonically)
        assert_eq!(hash_ab, hash_ba);
    }
}
