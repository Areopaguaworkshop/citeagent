//! LoRA Triplet Extraction — S8_lora_triplet_schema.md
//!
//! Extracts training triplets from session traces at REFLECT stage.
//! 4-gate quality filter for positive triplets; failure classification
//! for contrastive learning.

use std::fs::OpenOptions;
use std::io::Write;
use std::path::Path;

use chrono::Utc;
use serde::{Deserialize, Serialize};
use uuid::Uuid;

/// A positive training triplet (passed all quality gates).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PositiveTriplet {
    pub triplet_id: String,
    pub trace_id: String,
    pub frame_id: String,
    pub created_at: String,
    pub agent_name: String,
    pub model: String,
    pub model_tier: String,
    pub query: String,
    pub context: String,
    pub response: String,
    #[serde(default)]
    pub context_sources: Vec<ContextSource>,
    pub verified_claim_count: u32,
    pub blocked_claim_count: u32,
    pub cite_anchor_count: u32,
    pub coverage_score: f32,
    pub replay_guarantee: String,
    pub skill: String,
    pub hierarchy_path: String,
    pub language: String,
    pub token_count: TokenCount,
    pub quality_gates: QualityGates,
    #[serde(default)]
    pub is_intermediate: bool,
    pub final_triplet_id: Option<String>,
}

/// A failure training triplet (contrastive learning).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FailureTriplet {
    pub triplet_id: String,
    pub trace_id: String,
    pub frame_id: String,
    pub created_at: String,
    pub agent_name: String,
    pub model: String,
    pub model_tier: String,
    pub query: String,
    pub context: String,
    pub response: String,
    #[serde(default)]
    pub context_sources: Vec<ContextSource>,
    pub failure_type: String,
    #[serde(default)]
    pub failure_details: Vec<FailureDetail>,
    pub verified_claim_count: u32,
    pub blocked_claim_count: u32,
    pub cite_anchor_count: u32,
    pub coverage_score: f32,
    pub skill: String,
    pub hierarchy_path: String,
    pub language: String,
    pub token_count: TokenCount,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContextSource {
    pub source_csl_id: String,
    pub doc_id: String,
    pub quality_tier: String,
    pub slot_id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TokenCount {
    pub query_tokens: u32,
    pub context_tokens: u32,
    pub response_tokens: u32,
}

/// The 4-gate quality filter results.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QualityGates {
    pub citation_density: f32,
    pub verification_pass_rate: f32,
    pub contradiction_free: bool,
    /// Populated by background learning pipeline (Gate 4).
    pub novelty_score: Option<f32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FailureDetail {
    pub reason: String,
    pub claim_id: Option<String>,
    pub claim_text: Option<String>,
    pub score: Option<f32>,
    pub threshold: Option<f32>,
}

/// Failure type classification.
pub const FAILURE_TYPES: &[&str] = &[
    "claim_blocked",
    "guardrail_violation",
    "constraint_violation",
    "coverage_insufficient",
    "hallucinated_citation",
    "merkle_mismatch",
];

/// Input data for triplet extraction from a completed frame.
#[derive(Debug, Clone)]
pub struct ExtractionInput {
    pub trace_id: String,
    pub frame_id: String,
    pub agent_name: String,
    pub model: String,
    pub model_tier: String,
    pub query: String,
    pub context: String,
    pub response: String,
    pub context_sources: Vec<ContextSource>,
    pub verified_claim_count: u32,
    pub blocked_claim_count: u32,
    pub cite_anchor_count: u32,
    pub total_claim_count: u32,
    pub coverage_score: f32,
    pub replay_guarantee: String,
    pub skill: String,
    pub hierarchy_path: String,
    pub language: String,
    pub has_contradictions: bool,
    pub token_count: TokenCount,
}

/// Evaluate the 4-gate quality filter (Gates 1-3 synchronous).
/// Gate 4 (novelty) is deferred to the background pipeline.
pub fn evaluate_quality_gates(input: &ExtractionInput) -> QualityGates {
    let citation_density = if input.total_claim_count > 0 {
        input.cite_anchor_count as f32 / input.total_claim_count as f32
    } else {
        0.0
    };

    let verification_pass_rate = if input.total_claim_count > 0 {
        input.verified_claim_count as f32 / input.total_claim_count as f32
    } else {
        1.0
    };

    QualityGates {
        citation_density,
        verification_pass_rate,
        contradiction_free: !input.has_contradictions,
        novelty_score: None, // Gate 4: deferred to background
    }
}

/// Check if Gates 1-3 pass.
pub fn gates_1_3_pass(gates: &QualityGates) -> bool {
    gates.citation_density >= 0.70
        && gates.verification_pass_rate >= 0.80
        && gates.contradiction_free
}

/// Extract a triplet from a completed frame.
/// Returns either a positive or failure triplet.
pub fn extract_triplet(input: ExtractionInput) -> TripletResult {
    let is_failure = input.blocked_claim_count > 0 || input.coverage_score < 0.5;

    if is_failure {
        let failure_type = if input.blocked_claim_count > 0 {
            "claim_blocked"
        } else {
            "coverage_insufficient"
        };

        TripletResult::Failure(FailureTriplet {
            triplet_id: Uuid::new_v4().to_string(),
            trace_id: input.trace_id,
            frame_id: input.frame_id,
            created_at: Utc::now().to_rfc3339(),
            agent_name: input.agent_name,
            model: input.model,
            model_tier: input.model_tier,
            query: input.query,
            context: input.context,
            response: input.response,
            context_sources: input.context_sources,
            failure_type: failure_type.into(),
            failure_details: vec![],
            verified_claim_count: input.verified_claim_count,
            blocked_claim_count: input.blocked_claim_count,
            cite_anchor_count: input.cite_anchor_count,
            coverage_score: input.coverage_score,
            skill: input.skill,
            hierarchy_path: input.hierarchy_path,
            language: input.language,
            token_count: input.token_count,
        })
    } else {
        let quality_gates = evaluate_quality_gates(&input);
        let passes_gates = gates_1_3_pass(&quality_gates);

        if passes_gates {
            TripletResult::Positive(PositiveTriplet {
                triplet_id: Uuid::new_v4().to_string(),
                trace_id: input.trace_id,
                frame_id: input.frame_id,
                created_at: Utc::now().to_rfc3339(),
                agent_name: input.agent_name,
                model: input.model,
                model_tier: input.model_tier,
                query: input.query,
                context: input.context,
                response: input.response,
                context_sources: input.context_sources,
                verified_claim_count: input.verified_claim_count,
                blocked_claim_count: 0,
                cite_anchor_count: input.cite_anchor_count,
                coverage_score: input.coverage_score,
                replay_guarantee: input.replay_guarantee,
                skill: input.skill,
                hierarchy_path: input.hierarchy_path,
                language: input.language,
                token_count: input.token_count,
                quality_gates,
                is_intermediate: false,
                final_triplet_id: None,
            })
        } else {
            // Didn't pass quality gates → treat as failure
            TripletResult::Failure(FailureTriplet {
                triplet_id: Uuid::new_v4().to_string(),
                trace_id: input.trace_id,
                frame_id: input.frame_id,
                created_at: Utc::now().to_rfc3339(),
                agent_name: input.agent_name,
                model: input.model,
                model_tier: input.model_tier,
                query: input.query,
                context: input.context,
                response: input.response,
                context_sources: input.context_sources,
                failure_type: "quality_gate_failed".into(),
                failure_details: vec![],
                verified_claim_count: input.verified_claim_count,
                blocked_claim_count: input.blocked_claim_count,
                cite_anchor_count: input.cite_anchor_count,
                coverage_score: input.coverage_score,
                skill: input.skill,
                hierarchy_path: input.hierarchy_path,
                language: input.language,
                token_count: input.token_count,
            })
        }
    }
}

/// Result of triplet extraction.
#[derive(Debug)]
pub enum TripletResult {
    Positive(PositiveTriplet),
    Failure(FailureTriplet),
}

/// Append a positive triplet to the JSONL file.
pub fn append_positive(path: &Path, triplet: &PositiveTriplet) -> anyhow::Result<()> {
    let mut file = OpenOptions::new().create(true).append(true).open(path)?;
    let json = serde_json::to_string(triplet)?;
    writeln!(file, "{json}")?;
    Ok(())
}

/// Append a failure triplet to the JSONL file.
pub fn append_failure(path: &Path, triplet: &FailureTriplet) -> anyhow::Result<()> {
    let mut file = OpenOptions::new().create(true).append(true).open(path)?;
    let json = serde_json::to_string(triplet)?;
    writeln!(file, "{json}")?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_input(verified: u32, blocked: u32, anchors: u32, coverage: f32) -> ExtractionInput {
        ExtractionInput {
            trace_id: "t1".into(),
            frame_id: "f1".into(),
            agent_name: "LiteratureReviewAgent".into(),
            model: "anthropic/claude-sonnet-4-20250514".into(),
            model_tier: "cloud_premium".into(),
            query: "transformer attention".into(),
            context: "source text here".into(),
            response: "The Transformer [cite: src1] outperforms...".into(),
            context_sources: vec![],
            verified_claim_count: verified,
            blocked_claim_count: blocked,
            cite_anchor_count: anchors,
            total_claim_count: verified + blocked,
            coverage_score: coverage,
            replay_guarantee: "Exact".into(),
            skill: "literature_review".into(),
            hierarchy_path: "/cs/nlp".into(),
            language: "en".into(),
            has_contradictions: false,
            token_count: TokenCount {
                query_tokens: 10,
                context_tokens: 500,
                response_tokens: 200,
            },
        }
    }

    #[test]
    fn test_quality_gates_pass() {
        let input = make_input(9, 0, 8, 0.85);
        let gates = evaluate_quality_gates(&input);
        assert!(gates.citation_density >= 0.70);
        assert!(gates.verification_pass_rate >= 0.80);
        assert!(gates.contradiction_free);
        assert!(gates_1_3_pass(&gates));
    }

    #[test]
    fn test_quality_gates_fail_citation() {
        let input = make_input(10, 0, 5, 0.85);
        let gates = evaluate_quality_gates(&input);
        assert!(gates.citation_density < 0.70); // 5/10 = 0.5
        assert!(!gates_1_3_pass(&gates));
    }

    #[test]
    fn test_extract_positive_triplet() {
        let input = make_input(9, 0, 8, 0.85);
        let result = extract_triplet(input);
        assert!(matches!(result, TripletResult::Positive(_)));
    }

    #[test]
    fn test_extract_failure_blocked() {
        let input = make_input(3, 2, 4, 0.70);
        let result = extract_triplet(input);
        match result {
            TripletResult::Failure(f) => assert_eq!(f.failure_type, "claim_blocked"),
            _ => panic!("expected failure"),
        }
    }

    #[test]
    fn test_extract_failure_coverage() {
        let input = make_input(5, 0, 4, 0.30);
        let result = extract_triplet(input);
        match result {
            TripletResult::Failure(f) => assert_eq!(f.failure_type, "coverage_insufficient"),
            _ => panic!("expected failure"),
        }
    }
}
