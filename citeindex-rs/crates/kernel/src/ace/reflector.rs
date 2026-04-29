//! SessionReflector — builds the LLM prompt and parses lesson output.
//!
//! The Reflector is NOT a full agent. It is a single structured LLM call
//! managed by the kernel. It analyzes session traces and extracts lessons.

use serde::{Deserialize, Serialize};

/// A lesson extracted by the Reflector from a session trace.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Lesson {
    /// retrieval | citation | synonym | coverage_gap | pitfall
    #[serde(rename = "type")]
    pub lesson_type: String,
    pub description: String,
    pub domain_path: String,
    pub confidence: f32,
}

/// Summary of a session trace for the Reflector input.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionSummary {
    pub trace_id: String,
    pub frame_id: String,
    pub bm25_max_scores: Vec<f32>,
    pub citation_hit_ratio: f32,
    #[serde(default)]
    pub citation_miss_sources: Vec<String>,
    #[serde(default)]
    pub synonym_expansions_used: Vec<String>,
    #[serde(default)]
    pub coverage_scores: std::collections::HashMap<String, f32>,
    #[serde(default)]
    pub recover_events: u32,
    #[serde(default)]
    pub retrieval_mode: String,
    #[serde(default)]
    pub hierarchy_path: String,
}

/// The Reflector system prompt.
pub const REFLECTOR_SYSTEM_PROMPT: &str = r#"You are a research methodology reflector. Analyze the session trace and
extract actionable lessons for future sessions. Categories:

- retrieval: What search strategies worked or failed?
- citation: Which sources were useful vs. noisy?
- synonym: What term expansions helped or hurt?
- coverage_gap: What aspects remain uncovered?
- pitfall: What mistakes should be avoided next time?

Output a JSON array of lessons. Each lesson has:
- type: retrieval | citation | synonym | coverage_gap | pitfall
- description: one-sentence actionable insight
- domain_path: the hierarchy_path this applies to
- confidence: 0.0–1.0 (how confident you are this is a real pattern)"#;

/// Build the Reflector prompt from a session summary.
pub fn build_reflector_prompt(summary: &SessionSummary) -> String {
    let summary_json = serde_json::to_string_pretty(summary).unwrap_or_default();
    format!(
        "Analyze this session trace summary and extract lessons:\n\n```json\n{summary_json}\n```"
    )
}

/// Parse the Reflector LLM output into lessons.
pub fn parse_lessons(output: &str) -> Result<Vec<Lesson>, String> {
    // Try to extract JSON array from the output
    let trimmed = output.trim();

    // Handle markdown code block wrapping
    let json_str = if trimmed.starts_with("```") {
        trimmed
            .trim_start_matches("```json")
            .trim_start_matches("```")
            .trim_end_matches("```")
            .trim()
    } else {
        trimmed
    };

    serde_json::from_str::<Vec<Lesson>>(json_str)
        .map_err(|e| format!("failed to parse lessons: {e}"))
}

/// Reflector trigger mode.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ReflectorTrigger {
    /// Triggered asynchronously after COMMIT → REFLECT.
    PostCommit,
    /// Scholar triggers manually via `/reflect now`.
    Manual,
    /// Runs once per day on unreflected traces.
    Nightly,
}

impl ReflectorTrigger {
    pub fn from_str(s: &str) -> Self {
        match s {
            "manual" => Self::Manual,
            "nightly" => Self::Nightly,
            _ => Self::PostCommit,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_lessons() {
        let output = r#"[
            {"type": "retrieval", "description": "BM25 with attention worked well", "domain_path": "/cs/nlp", "confidence": 0.85},
            {"type": "coverage_gap", "description": "No edge device papers", "domain_path": "/cs/nlp/transformers", "confidence": 0.70}
        ]"#;

        let lessons = parse_lessons(output).unwrap();
        assert_eq!(lessons.len(), 2);
        assert_eq!(lessons[0].lesson_type, "retrieval");
        assert_eq!(lessons[1].lesson_type, "coverage_gap");
    }

    #[test]
    fn test_parse_lessons_code_block() {
        let output = "```json\n[{\"type\": \"synonym\", \"description\": \"ICL expansion\", \"domain_path\": \"/cs\", \"confidence\": 0.9}]\n```";
        let lessons = parse_lessons(output).unwrap();
        assert_eq!(lessons.len(), 1);
    }

    #[test]
    fn test_parse_lessons_invalid() {
        let result = parse_lessons("not json");
        assert!(result.is_err());
    }

    #[test]
    fn test_build_reflector_prompt() {
        let summary = SessionSummary {
            trace_id: "t1".into(),
            frame_id: "f1".into(),
            bm25_max_scores: vec![0.82, 0.45],
            citation_hit_ratio: 0.85,
            citation_miss_sources: vec![],
            synonym_expansions_used: vec![],
            coverage_scores: std::collections::HashMap::new(),
            recover_events: 0,
            retrieval_mode: "Exploratory".into(),
            hierarchy_path: "/cs/nlp".into(),
        };

        let prompt = build_reflector_prompt(&summary);
        assert!(prompt.contains("trace_id"));
        assert!(prompt.contains("0.82"));
    }

    #[test]
    fn test_reflector_trigger() {
        assert_eq!(
            ReflectorTrigger::from_str("post_commit"),
            ReflectorTrigger::PostCommit
        );
        assert_eq!(
            ReflectorTrigger::from_str("manual"),
            ReflectorTrigger::Manual
        );
        assert_eq!(
            ReflectorTrigger::from_str("nightly"),
            ReflectorTrigger::Nightly
        );
    }
}
