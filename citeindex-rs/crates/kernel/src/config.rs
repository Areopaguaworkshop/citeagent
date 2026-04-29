//! v12 Configuration — multi-file config system.
//!
//! Reads from `~/.citeindex/config/config.toml` and related files.
//! See: S5_storage_layout.md, D_decisions.md.

use serde::{Deserialize, Serialize};
use std::path::Path;

use crate::storage::StorageLayout;

/// Top-level v12 configuration loaded from `config/config.toml`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KernelConfig {
    #[serde(default)]
    pub llm: LlmRoutingConfig,

    #[serde(default)]
    pub retrieval: RetrievalConfig,

    #[serde(default)]
    pub score_fusion: ScoreFusionConfig,

    #[serde(default)]
    pub admission: AdmissionConfig,

    #[serde(default)]
    pub lora: LoraConfig,

    #[serde(default)]
    pub api: ApiConfig,

    #[serde(default)]
    pub traces: TracesConfig,

    #[serde(default)]
    pub kernel: KernelProcessConfig,
}

/// 3-tier model routing (D5).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LlmRoutingConfig {
    #[serde(default = "default_cloud_premium")]
    pub cloud_premium: String,

    #[serde(default = "default_cloud_standard")]
    pub cloud_standard: String,

    #[serde(default = "default_local_base")]
    pub local_base: String,

    #[serde(default = "default_personal")]
    pub personal: String,
}

/// Retrieval settings including WeakSignal thresholds (I7).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RetrievalConfig {
    #[serde(default = "default_weak_signal_threshold")]
    pub weak_signal_threshold: f32,

    #[serde(default = "default_weak_signal_max_hops")]
    pub weak_signal_max_hops: u32,

    #[serde(default = "default_weak_signal_deep_limit")]
    pub weak_signal_deep_limit: u32,

    #[serde(default = "default_weak_signal_deep_model_tier")]
    pub weak_signal_deep_model_tier: String,
}

/// Score fusion weights (I4).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScoreFusionConfig {
    #[serde(default = "default_w_bm25")]
    pub w_bm25: f32,

    #[serde(default = "default_w_hierarchy")]
    pub w_hierarchy: f32,

    #[serde(default = "default_w_citation_degree")]
    pub w_citation_degree: f32,

    #[serde(default = "default_w_recency")]
    pub w_recency: f32,

    #[serde(default = "default_w_claim_density")]
    pub w_claim_density: f32,
}

/// Admission policy thresholds (T9).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AdmissionConfig {
    #[serde(default = "default_full_max")]
    pub full_max_load_pct: f32,

    #[serde(default = "default_standard_max")]
    pub standard_max_load_pct: f32,

    #[serde(default = "default_degraded_max")]
    pub degraded_max_load_pct: f32,
}

/// LoRA adapter settings (S8).
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct LoraConfig {
    pub active_adapter: Option<String>,
    pub base_model: Option<String>,
}

/// REST API settings (A1).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApiConfig {
    #[serde(default = "default_api_port")]
    pub port: u16,

    pub bearer_token: Option<String>,

    #[serde(default = "default_rate_limit")]
    pub rate_limit_per_min: u32,
}

/// Trace retention settings (S7).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TracesConfig {
    #[serde(default = "default_retention_days")]
    pub retention_days: u32,
}

/// Kernel process settings.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KernelProcessConfig {
    #[serde(default = "default_python_bin")]
    pub python_bin: String,
}

// ── Defaults ──────────────────────────────────────────────────

fn default_cloud_premium() -> String {
    "anthropic/claude-sonnet-4-20250514".into()
}
fn default_cloud_standard() -> String {
    "anthropic/claude-sonnet-4-20250514".into()
}
fn default_local_base() -> String {
    "ollama/llama3".into()
}
fn default_personal() -> String {
    "ollama/llama3".into()
}
fn default_weak_signal_threshold() -> f32 {
    0.40
}
fn default_weak_signal_max_hops() -> u32 {
    3
}
fn default_weak_signal_deep_limit() -> u32 {
    3
}
fn default_weak_signal_deep_model_tier() -> String {
    "cloud_standard".into()
}
fn default_w_bm25() -> f32 {
    0.55
}
fn default_w_hierarchy() -> f32 {
    0.15
}
fn default_w_citation_degree() -> f32 {
    0.12
}
fn default_w_recency() -> f32 {
    0.10
}
fn default_w_claim_density() -> f32 {
    0.08
}
fn default_full_max() -> f32 {
    50.0
}
fn default_standard_max() -> f32 {
    75.0
}
fn default_degraded_max() -> f32 {
    90.0
}
fn default_api_port() -> u16 {
    7432
}
fn default_rate_limit() -> u32 {
    60
}
fn default_retention_days() -> u32 {
    30
}
fn default_python_bin() -> String {
    "python".into()
}

impl Default for LlmRoutingConfig {
    fn default() -> Self {
        Self {
            cloud_premium: default_cloud_premium(),
            cloud_standard: default_cloud_standard(),
            local_base: default_local_base(),
            personal: default_personal(),
        }
    }
}

impl Default for RetrievalConfig {
    fn default() -> Self {
        Self {
            weak_signal_threshold: default_weak_signal_threshold(),
            weak_signal_max_hops: default_weak_signal_max_hops(),
            weak_signal_deep_limit: default_weak_signal_deep_limit(),
            weak_signal_deep_model_tier: default_weak_signal_deep_model_tier(),
        }
    }
}

impl Default for ScoreFusionConfig {
    fn default() -> Self {
        Self {
            w_bm25: default_w_bm25(),
            w_hierarchy: default_w_hierarchy(),
            w_citation_degree: default_w_citation_degree(),
            w_recency: default_w_recency(),
            w_claim_density: default_w_claim_density(),
        }
    }
}

impl Default for AdmissionConfig {
    fn default() -> Self {
        Self {
            full_max_load_pct: default_full_max(),
            standard_max_load_pct: default_standard_max(),
            degraded_max_load_pct: default_degraded_max(),
        }
    }
}

impl Default for ApiConfig {
    fn default() -> Self {
        Self {
            port: default_api_port(),
            bearer_token: None,
            rate_limit_per_min: default_rate_limit(),
        }
    }
}

impl Default for TracesConfig {
    fn default() -> Self {
        Self {
            retention_days: default_retention_days(),
        }
    }
}

impl Default for KernelProcessConfig {
    fn default() -> Self {
        Self {
            python_bin: default_python_bin(),
        }
    }
}

impl Default for KernelConfig {
    fn default() -> Self {
        Self {
            llm: LlmRoutingConfig::default(),
            retrieval: RetrievalConfig::default(),
            score_fusion: ScoreFusionConfig::default(),
            admission: AdmissionConfig::default(),
            lora: LoraConfig::default(),
            api: ApiConfig::default(),
            traces: TracesConfig::default(),
            kernel: KernelProcessConfig::default(),
        }
    }
}

impl ScoreFusionConfig {
    /// Validate that weights sum to 1.0.
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

impl KernelConfig {
    /// Load from a TOML file, falling back to defaults.
    pub fn load(path: &Path) -> anyhow::Result<Self> {
        if path.exists() {
            let content = std::fs::read_to_string(path)?;
            let cfg: Self = toml::from_str(&content)?;
            Ok(cfg)
        } else {
            tracing::info!("Config not found at {:?}, using defaults", path);
            Ok(Self::default())
        }
    }

    /// Load config from the storage layout's config.toml path.
    pub fn load_from_layout(layout: &StorageLayout) -> anyhow::Result<Self> {
        Self::load(&layout.config_toml)
    }

    /// Resolve the ModelId for a given model tier string.
    pub fn resolve_model(&self, tier: &str) -> &str {
        match tier {
            "cloud_premium" => &self.llm.cloud_premium,
            "cloud_standard" => &self.llm.cloud_standard,
            "local_base" => &self.llm.local_base,
            "personal" => &self.llm.personal,
            _ => &self.llm.cloud_standard,
        }
    }
}
