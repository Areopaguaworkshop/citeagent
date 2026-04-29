//! scholar_playbook.toml — parsing, serialization, and Merkle integrity.

use serde::{Deserialize, Serialize};

/// A single entry in a playbook strategy section.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlaybookEntry {
    pub description: String,
    pub domain_path: String,
    pub confidence: f32,
}

/// A pending synonym for scholar review.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PendingSynonym {
    pub term: String,
    pub expansion: Vec<String>,
    pub confidence: f32,
}

/// An approved synonym.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApprovedSynonym {
    pub term: String,
    pub expansion: Vec<String>,
}

/// A detected coverage gap.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CoverageGap {
    pub aspect: String,
    pub sessions_unfilled: u32,
    #[serde(default)]
    pub suggested_terms: Vec<String>,
}

/// The `[meta]` section.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlaybookMeta {
    #[serde(default)]
    pub project_id: String,
    #[serde(default)]
    pub domain_path: String,
    #[serde(default)]
    pub version: u64,
    #[serde(default)]
    pub curator_run: String,
}

/// Strategy section with helpful and harmful entries.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct StrategySection {
    #[serde(default)]
    pub helpful: Vec<PlaybookEntry>,
    #[serde(default)]
    pub harmful: Vec<PlaybookEntry>,
}

/// Pitfall strategy section.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct PitfallSection {
    #[serde(default)]
    pub entries: Vec<PlaybookEntry>,
}

/// Synonym evolution section.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct SynonymEvolution {
    #[serde(default)]
    pub pending_review: Vec<PendingSynonym>,
    #[serde(default)]
    pub approved: Vec<ApprovedSynonym>,
}

/// Coverage gaps section.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct CoverageGaps {
    #[serde(default)]
    pub detected: Vec<CoverageGap>,
}

/// Full scholar_playbook.toml structure.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScholarPlaybook {
    pub meta: PlaybookMeta,
    #[serde(default)]
    pub strategies: Strategies,
    #[serde(default)]
    pub synonym_evolution: SynonymEvolution,
    #[serde(default)]
    pub coverage_gaps: CoverageGaps,
}

/// All strategy subsections.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Strategies {
    #[serde(default)]
    pub retrieval: StrategySection,
    #[serde(default)]
    pub citation: StrategySection,
    #[serde(default)]
    pub pitfall: PitfallSection,
}

impl ScholarPlaybook {
    /// Load from a TOML file. Returns default if file doesn't exist.
    pub fn load(path: &std::path::Path) -> anyhow::Result<Self> {
        if path.exists() {
            let content = std::fs::read_to_string(path)?;
            let playbook: Self = toml::from_str(&content)?;
            Ok(playbook)
        } else {
            Ok(Self::empty(""))
        }
    }

    /// Create an empty playbook for a project.
    pub fn empty(project_id: &str) -> Self {
        Self {
            meta: PlaybookMeta {
                project_id: project_id.into(),
                domain_path: String::new(),
                version: 0,
                curator_run: String::new(),
            },
            strategies: Strategies::default(),
            synonym_evolution: SynonymEvolution::default(),
            coverage_gaps: CoverageGaps::default(),
        }
    }

    /// Save to a TOML file.
    pub fn save(&self, path: &std::path::Path) -> anyhow::Result<()> {
        let content = toml::to_string_pretty(self)?;
        std::fs::write(path, content)?;
        Ok(())
    }

    /// Compute Merkle hash of the playbook content.
    pub fn merkle_hash(&self) -> crate::types::ids::MerkleHash {
        let content = toml::to_string(self).unwrap_or_default();
        crate::types::ids::MerkleHash::from_str_content(&content)
    }

    /// Get all approved synonyms as (term, expansions) pairs.
    pub fn approved_synonyms(&self) -> Vec<(String, Vec<String>)> {
        self.synonym_evolution
            .approved
            .iter()
            .map(|s| (s.term.clone(), s.expansion.clone()))
            .collect()
    }

    /// Get all pitfall descriptions for injection into system prompt.
    pub fn pitfall_descriptions(&self) -> Vec<String> {
        self.strategies
            .pitfall
            .entries
            .iter()
            .map(|e| e.description.clone())
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_empty_playbook() {
        let pb = ScholarPlaybook::empty("test-proj");
        assert_eq!(pb.meta.project_id, "test-proj");
        assert_eq!(pb.meta.version, 0);
        assert!(pb.strategies.retrieval.helpful.is_empty());
    }

    #[test]
    fn test_playbook_roundtrip() {
        let mut pb = ScholarPlaybook::empty("test");
        pb.strategies.retrieval.helpful.push(PlaybookEntry {
            description: "Use claim_index for specific claims".into(),
            domain_path: "/cs/nlp".into(),
            confidence: 0.85,
        });
        pb.synonym_evolution.approved.push(ApprovedSynonym {
            term: "LLM".into(),
            expansion: vec!["large language model".into()],
        });

        let toml_str = toml::to_string_pretty(&pb).unwrap();
        let parsed: ScholarPlaybook = toml::from_str(&toml_str).unwrap();
        assert_eq!(parsed.strategies.retrieval.helpful.len(), 1);
        assert_eq!(parsed.synonym_evolution.approved.len(), 1);
    }

    #[test]
    fn test_merkle_hash_deterministic() {
        let pb = ScholarPlaybook::empty("test");
        let h1 = pb.merkle_hash();
        let h2 = pb.merkle_hash();
        assert_eq!(h1, h2);
    }

    #[test]
    fn test_approved_synonyms() {
        let mut pb = ScholarPlaybook::empty("test");
        pb.synonym_evolution.approved.push(ApprovedSynonym {
            term: "ICL".into(),
            expansion: vec!["in-context learning".into()],
        });
        let syns = pb.approved_synonyms();
        assert_eq!(syns.len(), 1);
        assert_eq!(syns[0].0, "ICL");
    }
}
