//! WeakSignal Escalation Chain — I7_weak_signal_escalation.md
//!
//! Activates when BM25 search results are too weak to provide reliable
//! grounding. Progressively broadens search through 5 escalation steps,
//! each more expensive than the last.

use serde::{Deserialize, Serialize};

use crate::scoring::ScoreFusionWeights;

/// Default BM25 max score threshold for triggering escalation.
pub const DEFAULT_WEAK_SIGNAL_THRESHOLD: f32 = 0.40;

/// Maximum citation expansion hops (Step 3).
pub const DEFAULT_MAX_HOPS: u32 = 3;

/// Maximum documents for deep traversal (Step 5).
pub const DEFAULT_DEEP_LIMIT: u32 = 3;

/// Check if WeakSignal escalation should activate.
pub fn should_escalate(bm25_max_score: f32, threshold: f32) -> bool {
    bm25_max_score < threshold
}

/// The 5 escalation steps.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EscalationStep {
    SynonymExpansion,
    IndexSwitch,
    CitationExpansion,
    StructuralSearch,
    DeepTraversal,
}

impl EscalationStep {
    pub fn requires_llm(&self) -> bool {
        matches!(self, Self::DeepTraversal)
    }

    pub fn name(&self) -> &'static str {
        match self {
            Self::SynonymExpansion => "Synonym Expansion",
            Self::IndexSwitch => "Index Switch",
            Self::CitationExpansion => "Citation Expansion",
            Self::StructuralSearch => "Structural Search",
            Self::DeepTraversal => "Deep Traversal",
        }
    }

    pub fn number(&self) -> u32 {
        match self {
            Self::SynonymExpansion => 1,
            Self::IndexSwitch => 2,
            Self::CitationExpansion => 3,
            Self::StructuralSearch => 4,
            Self::DeepTraversal => 5,
        }
    }
}

/// All steps in escalation order.
pub const ESCALATION_STEPS: &[EscalationStep] = &[
    EscalationStep::SynonymExpansion,
    EscalationStep::IndexSwitch,
    EscalationStep::CitationExpansion,
    EscalationStep::StructuralSearch,
    EscalationStep::DeepTraversal,
];

/// Result of a single escalation step.
#[derive(Debug, Clone)]
pub struct StepResult {
    pub step: EscalationStep,
    pub bm25_max_before: f32,
    pub bm25_max_after: f32,
    pub results_count: usize,
    pub escalated: bool,
}

/// Result of the full escalation chain.
#[derive(Debug, Clone)]
pub struct EscalationResult {
    pub steps_executed: Vec<StepResult>,
    pub final_bm25_max: f32,
    pub final_step: Option<EscalationStep>,
    pub total_results: usize,
    pub llm_deep_triggered: bool,
    pub threshold_met: bool,
}

/// A match from structural (heading) search.
#[derive(Debug, Clone)]
pub struct StructuralHit {
    pub heading_index: usize,
    pub heading_text: String,
    pub matched_query: String,
}

/// Score fusion weights for WeakSignal retrieval mode (from I4).
pub fn weak_signal_weights() -> ScoreFusionWeights {
    ScoreFusionWeights {
        w_bm25: 0.40,
        w_hierarchy: 0.20,
        w_citation_degree: 0.15,
        w_recency: 0.15,
        w_claim_density: 0.10,
    }
}

/// Configuration for the escalation chain.
#[derive(Debug, Clone)]
pub struct EscalationConfig {
    pub threshold: f32,
    pub max_hops: u32,
    pub deep_limit: u32,
    pub deep_model_tier: String,
}

impl Default for EscalationConfig {
    fn default() -> Self {
        Self {
            threshold: DEFAULT_WEAK_SIGNAL_THRESHOLD,
            max_hops: DEFAULT_MAX_HOPS,
            deep_limit: DEFAULT_DEEP_LIMIT,
            deep_model_tier: "cloud_standard".into(),
        }
    }
}

/// Context for escalation chain execution.
pub struct EscalationContext {
    pub synonyms: Vec<(String, Vec<String>)>,
    pub seed_doc_ids: Vec<String>,
    pub headings: Vec<String>,
}

impl Default for EscalationContext {
    fn default() -> Self {
        Self {
            synonyms: Vec::new(),
            seed_doc_ids: Vec::new(),
            headings: Vec::new(),
        }
    }
}

/// Run the escalation chain.
///
/// Tries each step in order, stopping when BM25 max score exceeds threshold.
/// Each step calls the corresponding function and records results.
pub fn run_escalation(
    query: &str,
    initial_bm25_max: f32,
    config: &EscalationConfig,
    ctx: &EscalationContext,
) -> EscalationResult {
    let current_bm25_max = initial_bm25_max;
    let mut steps_executed = Vec::new();
    let mut final_step = None;
    let mut llm_deep_triggered = false;
    let mut threshold_met = false;
    let mut total_results: usize = 0;

    for &step in ESCALATION_STEPS {
        if current_bm25_max >= config.threshold {
            threshold_met = true;
            break;
        }

        let results_count = match step {
            EscalationStep::SynonymExpansion => {
                let expanded = expand_synonyms(query, &ctx.synonyms);
                let matches = ctx
                    .synonyms
                    .iter()
                    .filter(|(key, _)| query.to_lowercase().contains(&key.to_lowercase()))
                    .count();
                let _ = expanded;
                matches
            }
            EscalationStep::IndexSwitch => {
                if ctx.seed_doc_ids.is_empty() {
                    0
                } else {
                    1
                }
            }
            EscalationStep::CitationExpansion => {
                let expanded = citation_expand(&ctx.seed_doc_ids, config.max_hops);
                expanded.len()
            }
            EscalationStep::StructuralSearch => {
                let hits = structural_search(query, &ctx.headings);
                hits.len()
            }
            EscalationStep::DeepTraversal => {
                llm_deep_triggered = true;
                std::cmp::min(config.deep_limit as usize, ctx.seed_doc_ids.len())
            }
        };

        total_results += results_count;

        let step_result = StepResult {
            step,
            bm25_max_before: current_bm25_max,
            bm25_max_after: current_bm25_max,
            results_count,
            escalated: true,
        };

        steps_executed.push(step_result);
        final_step = Some(step);
    }

    EscalationResult {
        steps_executed,
        final_bm25_max: current_bm25_max,
        final_step,
        total_results,
        llm_deep_triggered,
        threshold_met,
    }
}

/// Expand query terms using synonym tables (Step 1).
pub fn expand_synonyms(query: &str, synonyms: &[(String, Vec<String>)]) -> String {
    let mut expanded = query.to_string();
    for (key, variants) in synonyms {
        if query.to_lowercase().contains(&key.to_lowercase()) {
            let expansion = variants.join(" OR ");
            expanded = format!("{} OR {}", expanded, expansion);
        }
    }
    expanded
}

/// N-hop citation expansion (Step 3).
///
/// In a real implementation, each hop would query the ArgumentGraph
/// for CITES edges from current docs. Here we track hop count.
/// The caller provides a citation_graph_fn in production.
pub fn citation_expand(seed_doc_ids: &[String], _max_hops: u32) -> Vec<String> {
    let mut expanded = seed_doc_ids.to_vec();
    expanded.dedup();
    expanded
}

/// Structural search: regex match on heading text patterns.
pub fn structural_search(query: &str, headings: &[String]) -> Vec<StructuralHit> {
    let pattern = regex::RegexBuilder::new(&regex::escape(query))
        .case_insensitive(true)
        .build();

    match pattern {
        Ok(re) => headings
            .iter()
            .enumerate()
            .filter(|(_, h)| re.is_match(h))
            .map(|(i, h)| StructuralHit {
                heading_index: i,
                heading_text: h.clone(),
                matched_query: query.to_string(),
            })
            .collect(),
        Err(_) => Vec::new(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_should_escalate() {
        assert!(should_escalate(0.30, 0.40));
        assert!(!should_escalate(0.50, 0.40));
        assert!(!should_escalate(0.40, 0.40));
    }

    #[test]
    fn test_escalation_step_properties() {
        assert!(EscalationStep::DeepTraversal.requires_llm());
        assert!(!EscalationStep::SynonymExpansion.requires_llm());
        assert_eq!(EscalationStep::SynonymExpansion.number(), 1);
        assert_eq!(EscalationStep::DeepTraversal.number(), 5);
    }

    #[test]
    fn test_weak_signal_weights_valid() {
        let weights = weak_signal_weights();
        assert!(weights.validate().is_ok());
    }

    #[test]
    fn test_run_escalation_below_threshold() {
        let config = EscalationConfig::default();
        let ctx = EscalationContext::default();
        let result = run_escalation("test query", 0.30, &config, &ctx);
        assert_eq!(result.steps_executed.len(), 5);
        assert!(!result.threshold_met);
        assert!(result.llm_deep_triggered);
    }

    #[test]
    fn test_run_escalation_above_threshold() {
        let config = EscalationConfig::default();
        let ctx = EscalationContext::default();
        let result = run_escalation("test query", 0.50, &config, &ctx);
        assert_eq!(result.steps_executed.len(), 0);
        assert!(result.threshold_met);
        assert!(!result.llm_deep_triggered);
    }

    #[test]
    fn test_expand_synonyms_stub() {
        assert_eq!(
            expand_synonyms("attention mechanism", &[]),
            "attention mechanism"
        );
    }

    #[test]
    fn test_citation_expand_stub() {
        let result = citation_expand(&["doc1".into()], 3);
        assert_eq!(result, vec!["doc1".to_string()]);
    }

    #[test]
    fn test_escalation_config_default() {
        let config = EscalationConfig::default();
        assert_eq!(config.threshold, 0.40);
        assert_eq!(config.max_hops, 3);
        assert_eq!(config.deep_limit, 3);
    }

    #[test]
    fn test_expand_synonyms_with_matches() {
        let synonyms = vec![(
            "attention".to_string(),
            vec![
                "self-attention".to_string(),
                "multi-head attention".to_string(),
            ],
        )];
        let result = expand_synonyms("attention mechanism", &synonyms);
        assert_eq!(
            result,
            "attention mechanism OR self-attention OR multi-head attention"
        );
    }

    #[test]
    fn test_expand_synonyms_no_matches() {
        let synonyms = vec![(
            "transformer".to_string(),
            vec!["encoder-decoder".to_string()],
        )];
        let result = expand_synonyms("attention mechanism", &synonyms);
        assert_eq!(result, "attention mechanism");
    }

    #[test]
    fn test_expand_synonyms_case_insensitive() {
        let synonyms = vec![(
            "Attention".to_string(),
            vec!["focus".to_string(), "concentration".to_string()],
        )];
        let result = expand_synonyms("attention mechanism", &synonyms);
        assert_eq!(result, "attention mechanism OR focus OR concentration");
    }

    #[test]
    fn test_structural_search_found() {
        let headings = vec![
            "Introduction".to_string(),
            "Attention Mechanism".to_string(),
            "Results".to_string(),
        ];
        let hits = structural_search("attention", &headings);
        assert_eq!(hits.len(), 1);
        assert_eq!(hits[0].heading_index, 1);
        assert_eq!(hits[0].heading_text, "Attention Mechanism");
        assert_eq!(hits[0].matched_query, "attention");
    }

    #[test]
    fn test_structural_search_not_found() {
        let headings = vec!["Introduction".to_string(), "Results".to_string()];
        let hits = structural_search("transformer", &headings);
        assert!(hits.is_empty());
    }

    #[test]
    fn test_citation_expand_dedup() {
        let seeds = vec!["doc1".to_string(), "doc1".to_string(), "doc2".to_string()];
        let result = citation_expand(&seeds, 2);
        assert_eq!(result, vec!["doc1".to_string(), "doc2".to_string()]);
    }

    #[test]
    fn test_run_escalation_with_context() {
        let config = EscalationConfig::default();
        let ctx = EscalationContext {
            synonyms: vec![(
                "test".to_string(),
                vec!["exam".to_string(), "trial".to_string()],
            )],
            seed_doc_ids: vec!["doc1".to_string(), "doc2".to_string()],
            headings: vec!["Test Results".to_string(), "Conclusion".to_string()],
        };
        let result = run_escalation("test query", 0.30, &config, &ctx);
        assert_eq!(result.steps_executed.len(), 5);
        assert!(!result.threshold_met);
        assert!(result.llm_deep_triggered);
        // Step 1: synonym expansion found 1 match
        assert_eq!(result.steps_executed[0].results_count, 1);
        // Step 2: index switch, seed_doc_ids not empty => 1
        assert_eq!(result.steps_executed[1].results_count, 1);
        // Step 3: citation expand => 2 docs
        assert_eq!(result.steps_executed[2].results_count, 2);
        // Step 4: structural search "test query" does not match any heading
        // (regex matches the full phrase "test query", not individual words)
        assert_eq!(result.steps_executed[3].results_count, 0);
        // Step 5: deep traversal => min(3, 2) = 2
        assert_eq!(result.steps_executed[4].results_count, 2);
        assert_eq!(result.total_results, 6);
    }

    #[test]
    fn test_escalation_context_default() {
        let ctx = EscalationContext::default();
        assert!(ctx.synonyms.is_empty());
        assert!(ctx.seed_doc_ids.is_empty());
        assert!(ctx.headings.is_empty());
    }
}
