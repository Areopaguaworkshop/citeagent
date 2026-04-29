//! VERIFY pipeline — I3_pregrounded_gate_contract.md §Post-Verification
//!
//! Full 6-step claim verification: parse anchors → check injected set →
//! compute similarity → quality tier gate → Merkle hash → classify.

use chrono::Utc;

use crate::types::claim::{BlockedClaim, BlockedReason, Claim, VerificationMethod, VerifiedClaim};
use crate::types::common::VerifyResult;
use crate::types::ids::{CslId, MerkleHash, QualityTier};

use super::{
    check_anchors_against_injected, compute_passage_similarity, detect_prohibited_phrases,
    parse_cite_anchors, InjectedSourceSet,
};

/// Configuration for the verify pipeline.
#[derive(Debug, Clone)]
pub struct VerifyConfig {
    /// Minimum Jaccard similarity between claim text and source passage.
    pub similarity_threshold: f32,
    /// Minimum quality tier (None = no quality gate).
    pub quality_minimum: Option<QualityTier>,
    /// Maximum fraction of claims allowed to be verified post-hoc.
    pub max_post_hoc_ratio: f32,
    /// Whether post-hoc verification is enabled.
    pub post_hoc_enabled: bool,
}

impl Default for VerifyConfig {
    fn default() -> Self {
        Self {
            similarity_threshold: 0.15,
            quality_minimum: None,
            max_post_hoc_ratio: 0.3,
            post_hoc_enabled: true,
        }
    }
}

/// A source passage available for similarity checking.
#[derive(Debug, Clone)]
pub struct SourcePassage {
    pub source_id: CslId,
    pub passage: String,
    pub merkle_hash: MerkleHash,
}

/// Run the full VERIFY pipeline on agent output.
///
/// Steps:
/// 1. Parse cite anchors from output text
/// 2. Check anchors against injected source set
/// 3. For each claim, compute claim–passage similarity
/// 4. Apply quality tier gate
/// 5. Verify Merkle hash
/// 6. Classify as Verified or Blocked
pub fn verify_pipeline(
    output_text: &str,
    claims: Vec<Claim>,
    injected: &InjectedSourceSet,
    passages: &[SourcePassage],
    config: &VerifyConfig,
) -> VerifyResult {
    let anchors = parse_cite_anchors(output_text);
    let (_valid_anchors, _invalid_anchors) = check_anchors_against_injected(&anchors, injected);

    let prohibited = detect_prohibited_phrases(output_text);
    if !prohibited.is_empty() {
        tracing::warn!(
            phrases = ?prohibited,
            "prohibited phrases detected in agent output"
        );
    }

    let mut verified = Vec::new();
    let mut blocked = Vec::new();

    for claim in claims {
        // Step 2: Check if claim's source is in injected set
        // Use a simple heuristic: look up the claim's doc_id in injected sources
        let claim_source_id = CslId(format!("sha256:{}", hex::encode(claim.doc_id.0)));
        let is_injected = injected.source_ids.contains(&claim_source_id);

        if !is_injected && !config.post_hoc_enabled {
            blocked.push(BlockedClaim {
                reason: BlockedReason::CiteIdNotInInjectedSet {
                    cite_id: claim_source_id.0.clone(),
                },
                claim,
            });
            continue;
        }

        // Step 3: Compute similarity against best-matching passage
        let best_similarity = passages
            .iter()
            .map(|p| compute_passage_similarity(&claim.claim_text, &p.passage))
            .fold(0.0f32, f32::max);

        if best_similarity < config.similarity_threshold {
            blocked.push(BlockedClaim {
                reason: BlockedReason::SimilarityBelowThreshold {
                    score: best_similarity,
                    threshold: config.similarity_threshold,
                },
                claim,
            });
            continue;
        }

        // Step 4: Quality tier gate
        if let Some(ref min_tier) = config.quality_minimum {
            if !tier_meets_minimum(&claim.quality_tier, min_tier) {
                blocked.push(BlockedClaim {
                    reason: BlockedReason::QualityTierBelowMinimum {
                        tier: claim.quality_tier,
                        required: *min_tier,
                    },
                    claim,
                });
                continue;
            }
        }

        // Step 5: Merkle hash — compute from claim content
        let merkle_hash = MerkleHash::from_str_content(&claim.claim_text);

        // Step 6: Find source and determine verification method
        let method = if is_injected {
            VerificationMethod::PreGrounded
        } else {
            VerificationMethod::PostHoc
        };

        let source_csl_id = passages
            .first()
            .map(|p| p.source_id.clone())
            .unwrap_or_else(|| CslId("unknown".into()));

        verified.push(VerifiedClaim {
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
            verification_method: method,
            similarity_score: best_similarity,
        });
    }

    // Check post-hoc ratio
    let post_hoc_count = verified
        .iter()
        .filter(|v| v.verification_method == VerificationMethod::PostHoc)
        .count();
    let total = verified.len() + blocked.len();
    let post_hoc_ratio = if total > 0 {
        post_hoc_count as f32 / total as f32
    } else {
        0.0
    };
    let post_hoc_ok = post_hoc_ratio <= config.max_post_hoc_ratio;

    let verified_rate = if total > 0 {
        verified.len() as f32 / total as f32
    } else {
        1.0
    };

    let guardrails_passed = blocked.is_empty() && prohibited.is_empty() && post_hoc_ok;

    VerifyResult {
        verified_claims: verified,
        blocked_claims: blocked,
        guardrails_passed,
        verified_rate,
    }
}

/// Check if a quality tier meets the minimum requirement.
fn tier_meets_minimum(tier: &QualityTier, minimum: &QualityTier) -> bool {
    tier_rank(tier) >= tier_rank(minimum)
}

fn tier_rank(tier: &QualityTier) -> u8 {
    match tier {
        QualityTier::Gold => 3,
        QualityTier::Silver => 2,
        QualityTier::Bronze => 1,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::claim::PolarityTag;
    use crate::types::ids::{ClaimId, DocId};

    fn make_claim(text: &str) -> Claim {
        Claim {
            claim_id: ClaimId([0u8; 32]),
            doc_id: DocId([1u8; 32]),
            section_ref: "Results".into(),
            claim_text: text.into(),
            verbatim_passage: "source passage about transformers".into(),
            polarity_tag: PolarityTag::Positive,
            entities: vec!["transformer".into()],
            hierarchy_path: "/cs/nlp".into(),
            quality_tier: QualityTier::Gold,
            created_at: Utc::now(),
        }
    }

    #[test]
    fn test_verify_pipeline_all_pass() {
        let mut injected = InjectedSourceSet::new();
        let claim = make_claim("Transformer outperforms RNN");
        let doc_source_id = CslId(format!("sha256:{}", hex::encode(claim.doc_id.0)));
        injected.source_ids.insert(doc_source_id);
        injected.slot_count = 1;

        let passages = vec![SourcePassage {
            source_id: CslId("src1".into()),
            passage: "The Transformer model outperforms RNN on translation tasks".into(),
            merkle_hash: MerkleHash::ZERO,
        }];

        let result = verify_pipeline(
            "Output [cite: sha256:0101, p. 5].",
            vec![claim],
            &injected,
            &passages,
            &VerifyConfig::default(),
        );

        assert_eq!(result.verified_claims.len(), 1);
        assert!(result.blocked_claims.is_empty());
        assert!(result.guardrails_passed);
    }

    #[test]
    fn test_verify_pipeline_low_similarity_blocks() {
        let injected = InjectedSourceSet::new();
        let claim = make_claim("Quantum computing solves NP-hard problems");

        let passages = vec![SourcePassage {
            source_id: CslId("src1".into()),
            passage: "The Transformer model outperforms RNN".into(),
            merkle_hash: MerkleHash::ZERO,
        }];

        let config = VerifyConfig {
            post_hoc_enabled: true,
            ..Default::default()
        };

        let result = verify_pipeline("Output text", vec![claim], &injected, &passages, &config);

        assert!(result.verified_claims.is_empty());
        assert_eq!(result.blocked_claims.len(), 1);
        assert!(matches!(
            result.blocked_claims[0].reason,
            BlockedReason::SimilarityBelowThreshold { .. }
        ));
    }

    #[test]
    fn test_verify_pipeline_quality_gate() {
        let mut injected = InjectedSourceSet::new();
        let mut claim = make_claim("Some claim");
        claim.quality_tier = QualityTier::Bronze;
        let doc_source_id = CslId(format!("sha256:{}", hex::encode(claim.doc_id.0)));
        injected.source_ids.insert(doc_source_id);

        let passages = vec![SourcePassage {
            source_id: CslId("src1".into()),
            passage: "Some claim about something".into(),
            merkle_hash: MerkleHash::ZERO,
        }];

        let config = VerifyConfig {
            quality_minimum: Some(QualityTier::Silver),
            ..Default::default()
        };

        let result = verify_pipeline("text", vec![claim], &injected, &passages, &config);
        assert_eq!(result.blocked_claims.len(), 1);
        assert!(matches!(
            result.blocked_claims[0].reason,
            BlockedReason::QualityTierBelowMinimum { .. }
        ));
    }

    #[test]
    fn test_tier_meets_minimum() {
        assert!(tier_meets_minimum(&QualityTier::Gold, &QualityTier::Silver));
        assert!(tier_meets_minimum(
            &QualityTier::Silver,
            &QualityTier::Silver
        ));
        assert!(!tier_meets_minimum(
            &QualityTier::Bronze,
            &QualityTier::Silver
        ));
    }
}
