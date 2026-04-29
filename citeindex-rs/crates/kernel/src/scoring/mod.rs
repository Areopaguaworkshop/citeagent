//! Score Fusion — I4_score_fusion_formula.md
//!
//! Five-signal score fusion: BM25, hierarchy, citation degree, recency,
//! claim density. Built into search tools — agents receive fused scores.

use serde::{Deserialize, Serialize};

/// Weights for the five scoring signals.
/// Must sum to 1.0 (validated at config load time).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScoreFusionWeights {
    pub w_bm25: f32,
    pub w_hierarchy: f32,
    pub w_citation_degree: f32,
    pub w_recency: f32,
    pub w_claim_density: f32,
}

impl Default for ScoreFusionWeights {
    fn default() -> Self {
        Self {
            w_bm25: 0.55,
            w_hierarchy: 0.15,
            w_citation_degree: 0.12,
            w_recency: 0.10,
            w_claim_density: 0.08,
        }
    }
}

impl ScoreFusionWeights {
    pub fn validate(&self) -> Result<(), String> {
        let sum = self.w_bm25
            + self.w_hierarchy
            + self.w_citation_degree
            + self.w_recency
            + self.w_claim_density;
        if (sum - 1.0).abs() > 0.001 {
            return Err(format!(
                "score fusion weights sum to {sum:.4}, expected 1.0"
            ));
        }
        Ok(())
    }
}

/// Breakdown of how the fused score was computed.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScoreBreakdown {
    pub bm25: f32,
    pub hierarchy: f32,
    pub citation_degree: f32,
    pub recency: f32,
    pub claim_density: f32,
}

/// Normalize BM25 scores within a result set.
/// max_score is the highest BM25 score in this query's results.
pub fn normalize_bm25(raw_score: f32, max_score: f32) -> f32 {
    if max_score <= 0.0 {
        0.0
    } else {
        (raw_score / max_score).clamp(0.0, 1.0)
    }
}

/// Compute hierarchy boost based on shared prefix depth.
///
/// query_path: the hierarchy context of the current query (e.g., "/cs/nlp/transformers")
/// result_path: the hierarchy_path of the search result (e.g., "/cs/nlp/transformers/attention")
///
/// Returns a value in [0.0, 1.0].
pub fn hierarchy_boost(query_path: &str, result_path: &str) -> f32 {
    let query_parts: Vec<&str> = query_path.split('/').filter(|s| !s.is_empty()).collect();
    let result_parts: Vec<&str> = result_path.split('/').filter(|s| !s.is_empty()).collect();

    if query_parts.is_empty() {
        return 0.0;
    }

    let shared = query_parts
        .iter()
        .zip(result_parts.iter())
        .take_while(|(a, b)| a == b)
        .count();

    (shared as f32 / query_parts.len() as f32).clamp(0.0, 1.0)
}

/// Normalize citation degree to [0, 1].
/// Uses log normalization: log(1 + degree) / log(1 + max_degree_in_corpus)
pub fn citation_degree_normalized(degree: u32, max_degree: u32) -> f32 {
    if max_degree == 0 {
        return 0.0;
    }
    ((1.0 + degree as f64).ln() / (1.0 + max_degree as f64).ln()) as f32
}

/// Compute recency boost based on publication year.
/// Returns a value in [0.0, 1.0].
/// Exponential decay: e^(-age/10)
pub fn recency_boost(pub_year: i64, current_year: i64) -> f32 {
    let age = (current_year - pub_year).max(0) as f32;
    (-age / 10.0).exp()
}

/// Normalize claim density to [0, 1].
/// Uses log normalization like citation_degree.
pub fn claim_density_normalized(count: u32, max_count: u32) -> f32 {
    if max_count == 0 {
        return 0.0;
    }
    ((1.0 + count as f64).ln() / (1.0 + max_count as f64).ln()) as f32
}

/// Compute the fused score for a single search result.
pub fn fuse_score(
    raw_bm25: f32,
    max_bm25: f32,
    query_hierarchy: Option<&str>,
    result_hierarchy: &str,
    result_year: i64,
    current_year: i64,
    result_citation_degree: u32,
    max_citation_degree: u32,
    result_claim_count: u32,
    max_claim_count: u32,
    weights: &ScoreFusionWeights,
) -> (f32, ScoreBreakdown) {
    let bm25_norm = normalize_bm25(raw_bm25, max_bm25);

    let hier = match query_hierarchy {
        Some(qp) => hierarchy_boost(qp, result_hierarchy),
        None => 0.0,
    };

    let cite_deg = citation_degree_normalized(result_citation_degree, max_citation_degree);
    let recency = recency_boost(result_year, current_year);
    let claim_den = claim_density_normalized(result_claim_count, max_claim_count);

    let fused = (weights.w_bm25 * bm25_norm
        + weights.w_hierarchy * hier
        + weights.w_citation_degree * cite_deg
        + weights.w_recency * recency
        + weights.w_claim_density * claim_den)
        .clamp(0.0, 1.0);

    let breakdown = ScoreBreakdown {
        bm25: weights.w_bm25 * bm25_norm,
        hierarchy: weights.w_hierarchy * hier,
        citation_degree: weights.w_citation_degree * cite_deg,
        recency: weights.w_recency * recency,
        claim_density: weights.w_claim_density * claim_den,
    };

    (fused, breakdown)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_normalize_bm25() {
        assert_eq!(normalize_bm25(5.0, 10.0), 0.5);
        assert_eq!(normalize_bm25(10.0, 10.0), 1.0);
        assert_eq!(normalize_bm25(0.0, 0.0), 0.0);
        assert_eq!(normalize_bm25(15.0, 10.0), 1.0); // clamped
    }

    #[test]
    fn test_hierarchy_boost() {
        assert_eq!(
            hierarchy_boost("/cs/nlp/transformers", "/cs/nlp/transformers/attention"),
            1.0
        );
        let boost = hierarchy_boost("/cs/nlp/transformers", "/cs/nlp/icl");
        assert!((boost - 0.6667).abs() < 0.01);
        assert_eq!(
            hierarchy_boost("/cs/nlp/transformers", "/math/algebra"),
            0.0
        );
        assert_eq!(hierarchy_boost("", "/cs/nlp"), 0.0);
    }

    #[test]
    fn test_recency_boost() {
        let b = recency_boost(2026, 2026);
        assert!((b - 1.0).abs() < 0.001);
        let b = recency_boost(2016, 2026);
        assert!((b - 0.3679).abs() < 0.01);
    }

    #[test]
    fn test_citation_degree_normalized() {
        assert_eq!(citation_degree_normalized(0, 0), 0.0);
        assert_eq!(citation_degree_normalized(100, 100), 1.0);
        let n = citation_degree_normalized(50, 100);
        assert!(n > 0.0 && n < 1.0);
    }

    #[test]
    fn test_fuse_score_default_weights() {
        let weights = ScoreFusionWeights::default();
        assert!(weights.validate().is_ok());

        let (score, breakdown) = fuse_score(
            10.0,
            10.0,
            Some("/cs/nlp"),
            "/cs/nlp/transformers",
            2024,
            2026,
            50,
            100,
            10,
            20,
            &weights,
        );
        assert!(score > 0.0 && score <= 1.0);
        assert!(breakdown.bm25 > 0.0);
        assert!(breakdown.hierarchy > 0.0);
    }
}
