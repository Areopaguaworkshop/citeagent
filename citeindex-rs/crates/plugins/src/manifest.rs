//! Plugin manifest — parse and validate `plugin.toml`.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::Path;

/// A plugin manifest loaded from `plugin.toml`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PluginManifest {
    pub name: String,
    pub version: String,

    #[serde(default)]
    pub description: Option<String>,

    #[serde(default)]
    pub author: Option<String>,

    #[serde(default)]
    pub commands: HashMap<String, String>,

    #[serde(default)]
    pub test_command: Option<String>,
}

#[derive(Debug, thiserror::Error)]
pub enum ManifestError {
    #[error("plugin.toml not found at {0}")]
    NotFound(String),

    #[error("Failed to read plugin.toml: {0}")]
    ReadError(#[from] std::io::Error),

    #[error("Invalid plugin.toml: {0}")]
    ParseError(#[from] toml::de::Error),

    #[error("Missing required field: {0}")]
    MissingField(String),

    #[error("No commands defined in plugin")]
    NoCommands,
}

impl PluginManifest {
    /// Load and validate a plugin manifest from a directory.
    pub fn load(plugin_dir: &Path) -> Result<Self, ManifestError> {
        let manifest_path = plugin_dir.join("plugin.toml");
        if !manifest_path.exists() {
            return Err(ManifestError::NotFound(
                manifest_path.to_string_lossy().into(),
            ));
        }

        let content = std::fs::read_to_string(&manifest_path)?;
        let manifest: Self = toml::from_str(&content)?;
        manifest.validate()?;
        Ok(manifest)
    }

    /// Validate required fields.
    fn validate(&self) -> Result<(), ManifestError> {
        if self.name.is_empty() {
            return Err(ManifestError::MissingField("name".into()));
        }
        if self.version.is_empty() {
            return Err(ManifestError::MissingField("version".into()));
        }
        if self.commands.is_empty() {
            return Err(ManifestError::NoCommands);
        }
        Ok(())
    }
}
