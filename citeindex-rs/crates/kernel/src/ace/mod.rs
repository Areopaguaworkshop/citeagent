//! ACE Scholar Adaptation Layer — S9_ace_schema.md
//!
//! Self-improving context management: Generator → Reflector → Curator loop.
//! - Reflector: single LLM call extracting lessons from session traces.
//! - Curator: deterministic Rust merge/prune of scholar_playbook.toml.
//! - Playbook: TOML config injected at PLAN/THINK/ACT stages.

pub mod curator;
pub mod playbook;
pub mod reflector;

/// ACE configuration loaded from `config/scholarly_ace.toml`.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct AceConfig {
    #[serde(default)]
    pub scholarly_ace: ScholarlyAceSection,
    #[serde(default)]
    pub curator: CuratorSection,
    #[serde(default)]
    pub synonym_evolution: SynonymEvolutionSection,
    #[serde(default)]
    pub coverage_gap_feed: CoverageGapFeedSection,
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct ScholarlyAceSection {
    #[serde(default = "default_true")]
    pub enabled: bool,
    #[serde(default = "default_reflector_tier")]
    pub reflector_model_tier: String,
    #[serde(default)]
    pub reflector_temperature: f32,
    #[serde(default = "default_reflector_tokens")]
    pub reflector_max_tokens: u32,
    #[serde(default = "default_trigger")]
    pub reflector_trigger: String,
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct CuratorSection {
    #[serde(default = "default_similarity")]
    pub similarity_threshold: f32,
    #[serde(default = "default_max_entries")]
    pub max_entries_per_section: usize,
    #[serde(default = "default_auto_approve")]
    pub auto_approve_confidence: f32,
    #[serde(default = "default_true")]
    pub merkle_commit_on_write: bool,
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct SynonymEvolutionSection {
    #[serde(default = "default_pending_max")]
    pub pending_review_max: usize,
    #[serde(default)]
    pub auto_flush_approved: bool,
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct CoverageGapFeedSection {
    #[serde(default = "default_true")]
    pub feed_to_gap_agent: bool,
    #[serde(default = "default_min_sessions")]
    pub min_sessions_unfilled: u32,
}

fn default_true() -> bool {
    true
}
fn default_reflector_tier() -> String {
    "cloud_standard".into()
}
fn default_reflector_tokens() -> u32 {
    2048
}
fn default_trigger() -> String {
    "post_commit".into()
}
fn default_similarity() -> f32 {
    0.75
}
fn default_max_entries() -> usize {
    12
}
fn default_auto_approve() -> f32 {
    0.90
}
fn default_pending_max() -> usize {
    50
}
fn default_min_sessions() -> u32 {
    2
}

impl Default for ScholarlyAceSection {
    fn default() -> Self {
        Self {
            enabled: true,
            reflector_model_tier: default_reflector_tier(),
            reflector_temperature: 0.0,
            reflector_max_tokens: default_reflector_tokens(),
            reflector_trigger: default_trigger(),
        }
    }
}

impl Default for CuratorSection {
    fn default() -> Self {
        Self {
            similarity_threshold: default_similarity(),
            max_entries_per_section: default_max_entries(),
            auto_approve_confidence: default_auto_approve(),
            merkle_commit_on_write: true,
        }
    }
}

impl Default for SynonymEvolutionSection {
    fn default() -> Self {
        Self {
            pending_review_max: default_pending_max(),
            auto_flush_approved: false,
        }
    }
}

impl Default for CoverageGapFeedSection {
    fn default() -> Self {
        Self {
            feed_to_gap_agent: true,
            min_sessions_unfilled: default_min_sessions(),
        }
    }
}

impl Default for AceConfig {
    fn default() -> Self {
        Self {
            scholarly_ace: ScholarlyAceSection::default(),
            curator: CuratorSection::default(),
            synonym_evolution: SynonymEvolutionSection::default(),
            coverage_gap_feed: CoverageGapFeedSection::default(),
        }
    }
}

impl AceConfig {
    pub fn load(path: &std::path::Path) -> anyhow::Result<Self> {
        if path.exists() {
            let content = std::fs::read_to_string(path)?;
            let config: Self = toml::from_str(&content)?;
            Ok(config)
        } else {
            Ok(Self::default())
        }
    }
}
