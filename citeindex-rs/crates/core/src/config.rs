//! Configuration loader — reads `config.toml` for paths, LLM backends,
//! plugin registry, and TUI preferences.
//!
//! Matches `rust_core_orchestration.yaml → load_configuration`.

use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

/// Top-level configuration loaded from `config.toml`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CiteIndexConfig {
    #[serde(default = "default_corpus_root")]
    pub corpus_root: PathBuf,

    #[serde(default = "default_python_bin")]
    pub python_bin: String,

    #[serde(default)]
    pub llm: LlmConfig,

    #[serde(default)]
    pub tui: TuiConfig,

    #[serde(default)]
    pub plugins: PluginsConfig,

    #[serde(default)]
    pub memory: MemoryConfig,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LlmConfig {
    #[serde(default = "default_llm_model")]
    pub model: String,

    #[serde(default = "default_temperature")]
    pub temperature: f64,

    #[serde(default = "default_max_tokens")]
    pub max_tokens: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TuiConfig {
    #[serde(default = "default_theme")]
    pub theme: String,

    #[serde(default)]
    pub side_panel_collapsed: bool,

    #[serde(default = "default_side_panel_width")]
    pub side_panel_width_pct: u16,

    #[serde(default = "default_cite_style")]
    pub cite_style: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PluginsConfig {
    #[serde(default = "default_plugin_dir")]
    pub directory: PathBuf,

    #[serde(default)]
    pub enabled: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryConfig {
    #[serde(default = "default_memory_backend")]
    pub backend: String, // "file" or "postgresql"

    #[serde(default)]
    pub postgresql_url: Option<String>,
}

// ── Defaults ────────────────────────────────────────────────────────────

fn default_corpus_root() -> PathBuf {
    PathBuf::from("corpus")
}
fn default_python_bin() -> String {
    "python".into()
}
fn default_llm_model() -> String {
    "ollama/qwen3".into()
}
fn default_temperature() -> f64 {
    0.1
}
fn default_max_tokens() -> u32 {
    1024
}
fn default_theme() -> String {
    "dark".into()
}
fn default_side_panel_width() -> u16 {
    30
}
fn default_cite_style() -> String {
    "chicago-author-date".into()
}
fn default_plugin_dir() -> PathBuf {
    PathBuf::from("plugins")
}
fn default_memory_backend() -> String {
    "file".into()
}

impl Default for LlmConfig {
    fn default() -> Self {
        Self {
            model: default_llm_model(),
            temperature: default_temperature(),
            max_tokens: default_max_tokens(),
        }
    }
}

impl Default for TuiConfig {
    fn default() -> Self {
        Self {
            theme: default_theme(),
            side_panel_collapsed: false,
            side_panel_width_pct: default_side_panel_width(),
            cite_style: default_cite_style(),
        }
    }
}

impl Default for PluginsConfig {
    fn default() -> Self {
        Self {
            directory: default_plugin_dir(),
            enabled: Vec::new(),
        }
    }
}

impl Default for MemoryConfig {
    fn default() -> Self {
        Self {
            backend: default_memory_backend(),
            postgresql_url: None,
        }
    }
}

impl Default for CiteIndexConfig {
    fn default() -> Self {
        Self {
            corpus_root: default_corpus_root(),
            python_bin: default_python_bin(),
            llm: LlmConfig::default(),
            tui: TuiConfig::default(),
            plugins: PluginsConfig::default(),
            memory: MemoryConfig::default(),
        }
    }
}

impl CiteIndexConfig {
    /// Load configuration from a TOML file, falling back to defaults.
    pub fn load(path: &Path) -> anyhow::Result<Self> {
        if path.exists() {
            let content = std::fs::read_to_string(path)?;
            let cfg: Self = toml::from_str(&content)?;
            Ok(cfg)
        } else {
            tracing::info!("Config file not found at {:?}, using defaults", path);
            Ok(Self::default())
        }
    }

    /// Search for config.toml in standard locations.
    pub fn discover() -> Self {
        let mut candidates: Vec<PathBuf> = vec![
            PathBuf::from("config.toml"),
            PathBuf::from("citeindex.toml"),
        ];
        if let Some(config_dir) = dirs::config_dir() {
            candidates.push(config_dir.join("citeindex").join("config.toml"));
        }

        for path in &candidates {
            if path.exists() {
                match Self::load(path) {
                    Ok(cfg) => {
                        tracing::info!("Loaded config from {:?}", path);
                        return cfg;
                    }
                    Err(e) => {
                        tracing::warn!("Failed to load {:?}: {}", path, e);
                    }
                }
            }
        }

        tracing::info!("No config file found, using defaults");
        Self::default()
    }
}
