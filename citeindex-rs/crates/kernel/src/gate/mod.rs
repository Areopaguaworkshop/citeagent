//! Pre-Grounded Gate — I3_pregrounded_gate_contract.md
//!
//! Anti-hallucination mechanism. Two phases:
//! 1. Pre-grounding: inject verified sources into context before LLM call.
//! 2. Post-verification: validate cite anchors and claim–passage similarity.

pub mod commit;
pub mod verify;

use std::collections::HashSet;

use once_cell::sync::Lazy;
use regex::Regex;

use crate::types::ids::CslId;

/// Matches [cite: SOURCE_ID, LOCATOR] or [cite: SOURCE_ID]
static CITE_ANCHOR_RE: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"\[cite:\s*([^\],]+?)(?:\s*,\s*([^\]]+?))?\s*\]").unwrap());

/// Recorded at request dispatch time. Used by post-verification.
#[derive(Debug, Clone)]
pub struct InjectedSourceSet {
    pub source_ids: HashSet<CslId>,
    pub slot_count: usize,
    pub total_tokens: usize,
}

impl InjectedSourceSet {
    pub fn new() -> Self {
        Self {
            source_ids: HashSet::new(),
            slot_count: 0,
            total_tokens: 0,
        }
    }

    pub fn contains(&self, id: &CslId) -> bool {
        self.source_ids.contains(id)
    }
}

/// A parsed cite anchor from LLM output.
#[derive(Debug, Clone)]
pub struct ParsedCiteAnchor {
    pub source_id: String,
    pub locator: Option<String>,
    pub full_match: String,
    pub position: usize,
}

/// Parse all [cite: ...] anchors from agent output text.
pub fn parse_cite_anchors(text: &str) -> Vec<ParsedCiteAnchor> {
    CITE_ANCHOR_RE
        .captures_iter(text)
        .map(|cap| ParsedCiteAnchor {
            source_id: cap[1].trim().to_string(),
            locator: cap.get(2).map(|m| m.as_str().trim().to_string()),
            full_match: cap[0].to_string(),
            position: cap.get(0).unwrap().start(),
        })
        .collect()
}

/// Check anchors against injected source set.
/// Returns (valid_anchors, invalid_anchors).
pub fn check_anchors_against_injected(
    anchors: &[ParsedCiteAnchor],
    injected: &InjectedSourceSet,
) -> (Vec<ParsedCiteAnchor>, Vec<ParsedCiteAnchor>) {
    let mut valid = Vec::new();
    let mut invalid = Vec::new();

    for anchor in anchors {
        if injected
            .source_ids
            .contains(&CslId(anchor.source_id.clone()))
        {
            valid.push(anchor.clone());
        } else {
            invalid.push(anchor.clone());
        }
    }

    (valid, invalid)
}

/// Compute text similarity between claim and source passage.
/// Uses Jaccard similarity on lowercased whitespace-split terms.
pub fn compute_passage_similarity(claim_text: &str, source_passage: &str) -> f32 {
    let claim_lower = claim_text.to_lowercase();
    let passage_lower = source_passage.to_lowercase();

    let claim_terms: HashSet<&str> = claim_lower.split_whitespace().collect();
    let passage_terms: HashSet<&str> = passage_lower.split_whitespace().collect();

    if claim_terms.is_empty() && passage_terms.is_empty() {
        return 1.0;
    }
    if claim_terms.is_empty() || passage_terms.is_empty() {
        return 0.0;
    }

    let intersection = claim_terms.intersection(&passage_terms).count();
    let union = claim_terms.union(&passage_terms).count();

    if union == 0 {
        0.0
    } else {
        intersection as f32 / union as f32
    }
}

/// Prohibited phrases that suggest hallucination.
pub const PROHIBITED_PHRASES: &[&str] = &[
    "I believe",
    "I think",
    "it is widely known",
    "it goes without saying",
    "everyone knows",
    "obviously",
    "it is common knowledge",
];

/// Check output text for prohibited phrases.
/// Returns the list of detected prohibited phrases.
pub fn detect_prohibited_phrases(text: &str) -> Vec<&'static str> {
    let lower = text.to_lowercase();
    PROHIBITED_PHRASES
        .iter()
        .filter(|phrase| lower.contains(&phrase.to_lowercase()))
        .copied()
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_cite_anchors_basic() {
        let text =
            "The Transformer outperforms all previous models [cite: sha256:a1b2c3, p. 6002].";
        let anchors = parse_cite_anchors(text);
        assert_eq!(anchors.len(), 1);
        assert_eq!(anchors[0].source_id, "sha256:a1b2c3");
        assert_eq!(anchors[0].locator.as_deref(), Some("p. 6002"));
    }

    #[test]
    fn test_parse_cite_anchors_no_locator() {
        let text = "Some claim [cite: sha256:abc123].";
        let anchors = parse_cite_anchors(text);
        assert_eq!(anchors.len(), 1);
        assert_eq!(anchors[0].source_id, "sha256:abc123");
        assert!(anchors[0].locator.is_none());
    }

    #[test]
    fn test_parse_cite_anchors_multiple() {
        let text = "Claim A [cite: src1, p. 1]. Claim B [cite: src2, p. 2]. Claim C [cite: src3].";
        let anchors = parse_cite_anchors(text);
        assert_eq!(anchors.len(), 3);
    }

    #[test]
    fn test_check_anchors_against_injected() {
        let mut injected = InjectedSourceSet::new();
        injected.source_ids.insert(CslId("sha256:valid".into()));

        let anchors = vec![
            ParsedCiteAnchor {
                source_id: "sha256:valid".into(),
                locator: None,
                full_match: "[cite: sha256:valid]".into(),
                position: 0,
            },
            ParsedCiteAnchor {
                source_id: "sha256:invalid".into(),
                locator: None,
                full_match: "[cite: sha256:invalid]".into(),
                position: 30,
            },
        ];

        let (valid, invalid) = check_anchors_against_injected(&anchors, &injected);
        assert_eq!(valid.len(), 1);
        assert_eq!(invalid.len(), 1);
        assert_eq!(valid[0].source_id, "sha256:valid");
        assert_eq!(invalid[0].source_id, "sha256:invalid");
    }

    #[test]
    fn test_compute_passage_similarity() {
        let claim = "Transformer outperforms RNN on translation";
        let passage = "The Transformer model outperforms RNN on machine translation tasks";
        let sim = compute_passage_similarity(claim, passage);
        assert!(sim > 0.3, "similarity should be reasonable: {sim}");

        let unrelated = "This paper discusses photosynthesis in tropical plants";
        let sim2 = compute_passage_similarity(claim, unrelated);
        assert!(sim2 < 0.1, "unrelated should have low similarity: {sim2}");
    }

    #[test]
    fn test_detect_prohibited_phrases() {
        let text = "I believe the results show improvement. Obviously this is correct.";
        let detected = detect_prohibited_phrases(text);
        assert!(detected.contains(&"I believe"));
        assert!(detected.contains(&"obviously"));
        assert_eq!(detected.len(), 2);
    }

    #[test]
    fn test_no_prohibited_phrases() {
        let text = "The results demonstrate a 5% improvement [cite: src1, p. 12].";
        let detected = detect_prohibited_phrases(text);
        assert!(detected.is_empty());
    }
}
