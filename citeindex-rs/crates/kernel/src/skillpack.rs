//! Skill Pack system — directory-based packages bundling agents, skills,
//! synonyms, taxonomy extensions, and tool configs.
//!
//! Skill Packs are installed into `CITEINDEX_HOME/config/` subdirectories.
//! Each pack contains a `skillpack.toml` manifest describing its contents
//! and trust level.

use std::fs;
use std::path::{Path, PathBuf};

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use thiserror::Error;

// ── Errors ───────────────────────────────────────────────────

#[derive(Debug, Error)]
pub enum SkillPackError {
    #[error("manifest not found at {0}")]
    ManifestNotFound(PathBuf),

    #[error("invalid manifest: {0}")]
    InvalidManifest(String),

    #[error("pack already installed: {0}")]
    AlreadyInstalled(String),

    #[error("pack not found: {0}")]
    NotFound(String),

    #[error("validation failed: {0:?}")]
    ValidationFailed(Vec<String>),

    #[error("io error: {0}")]
    Io(#[from] std::io::Error),

    #[error("toml parse error: {0}")]
    TomlParse(#[from] toml::de::Error),
}

pub type Result<T> = std::result::Result<T, SkillPackError>;

// ── TrustLevel ───────────────────────────────────────────────

/// Trust level governing what tools a pack may access.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TrustLevel {
    /// Ships with the system — full tool access.
    Builtin,
    /// Signed by maintainers — full tool access.
    Verified,
    /// Unverified — restricted to declared `tools_allowed`.
    Community,
}

// ── SkillPackManifest ────────────────────────────────────────

/// Manifest loaded from `skillpack.toml` inside a pack directory.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkillPackManifest {
    pub name: String,
    pub version: String,
    pub description: String,
    pub author: String,
    pub trust_level: TrustLevel,

    /// Agent manifest filenames.
    #[serde(default)]
    pub agents: Vec<String>,

    /// Skill profile filenames.
    #[serde(default)]
    pub skills: Vec<String>,

    /// Synonym table filenames.
    #[serde(default)]
    pub synonyms: Vec<String>,

    /// Taxonomy extension filenames.
    #[serde(default)]
    pub taxonomy: Vec<String>,

    /// Tool config filenames.
    #[serde(default)]
    pub tools: Vec<String>,

    /// Other packs required by this one.
    #[serde(default)]
    pub dependencies: Vec<String>,
}

// ── SkillPack ────────────────────────────────────────────────

/// An installed skill pack on disk.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkillPack {
    pub manifest: SkillPackManifest,
    pub install_path: PathBuf,
    pub installed_at: DateTime<Utc>,
    pub enabled: bool,
}

// ── SkillPackSource ──────────────────────────────────────────

/// Where a pack can be installed from.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum SkillPackSource {
    /// Install from a local directory.
    LocalDir(PathBuf),
    /// Install from a git repository (stub — not yet implemented).
    GitUrl { url: String, branch: Option<String> },
}

// ── InstallReport ────────────────────────────────────────────

/// Report tracking what was installed during a pack install.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct InstallReport {
    pub agents_installed: Vec<String>,
    pub skills_installed: Vec<String>,
    pub synonyms_installed: Vec<String>,
    pub taxonomy_installed: Vec<String>,
    pub tools_installed: Vec<String>,
}

impl InstallReport {
    /// Total number of artefacts installed.
    pub fn total(&self) -> usize {
        self.agents_installed.len()
            + self.skills_installed.len()
            + self.synonyms_installed.len()
            + self.taxonomy_installed.len()
            + self.tools_installed.len()
    }
}

// ── SkillPackRegistry ────────────────────────────────────────

/// Manages installed skill packs under the config directory.
pub struct SkillPackRegistry;

impl SkillPackRegistry {
    /// Scan the config directory for installed packs.
    ///
    /// Each subdirectory containing a `skillpack.toml` is treated as an
    /// installed pack.
    pub fn list(config_dir: &Path) -> Result<Vec<SkillPack>> {
        let packs_dir = config_dir.join("skillpacks");
        if !packs_dir.exists() {
            return Ok(Vec::new());
        }

        let mut packs = Vec::new();
        for entry in fs::read_dir(&packs_dir)? {
            let entry = entry?;
            let path = entry.path();
            if !path.is_dir() {
                continue;
            }
            let manifest_path = path.join("skillpack.toml");
            if !manifest_path.exists() {
                continue;
            }
            let content = fs::read_to_string(&manifest_path)?;
            let manifest: SkillPackManifest = toml::from_str(&content)?;

            // Read install metadata if present, otherwise use file mtime.
            let installed_at = fs::metadata(&manifest_path)?
                .modified()
                .ok()
                .and_then(|t| {
                    let duration = t.duration_since(std::time::UNIX_EPOCH).ok()?;
                    DateTime::from_timestamp(duration.as_secs() as i64, 0)
                })
                .unwrap_or_else(Utc::now);

            packs.push(SkillPack {
                manifest,
                install_path: path,
                installed_at,
                enabled: true,
            });
        }

        Ok(packs)
    }

    /// Install a pack from the given source into the config directory.
    pub fn install(source: &SkillPackSource, config_dir: &Path) -> Result<SkillPack> {
        let src_dir = match source {
            SkillPackSource::LocalDir(path) => path.clone(),
            SkillPackSource::GitUrl { .. } => {
                return Err(SkillPackError::InvalidManifest(
                    "git source not yet implemented".into(),
                ));
            }
        };

        let manifest_path = src_dir.join("skillpack.toml");
        if !manifest_path.exists() {
            return Err(SkillPackError::ManifestNotFound(manifest_path));
        }

        let content = fs::read_to_string(&manifest_path)?;
        let manifest: SkillPackManifest = toml::from_str(&content)?;

        if let Err(errors) = Self::validate(&manifest) {
            return Err(SkillPackError::ValidationFailed(errors));
        }

        let packs_dir = config_dir.join("skillpacks");
        let dest = packs_dir.join(&manifest.name);
        if dest.exists() {
            return Err(SkillPackError::AlreadyInstalled(manifest.name.clone()));
        }

        copy_dir_recursive(&src_dir, &dest)?;

        Ok(SkillPack {
            manifest,
            install_path: dest,
            installed_at: Utc::now(),
            enabled: true,
        })
    }

    /// Remove an installed pack by name.
    pub fn uninstall(name: &str, config_dir: &Path) -> Result<()> {
        let dest = config_dir.join("skillpacks").join(name);
        if !dest.exists() {
            return Err(SkillPackError::NotFound(name.into()));
        }
        fs::remove_dir_all(&dest)?;
        Ok(())
    }

    /// Validate a manifest, returning a list of problems if invalid.
    pub fn validate(manifest: &SkillPackManifest) -> std::result::Result<(), Vec<String>> {
        let mut errors = Vec::new();

        if manifest.name.is_empty() {
            errors.push("name must not be empty".into());
        }
        if manifest.version.is_empty() {
            errors.push("version must not be empty".into());
        }
        if manifest.description.is_empty() {
            errors.push("description must not be empty".into());
        }
        if manifest.author.is_empty() {
            errors.push("author must not be empty".into());
        }

        if errors.is_empty() {
            Ok(())
        } else {
            Err(errors)
        }
    }
}

// ── Helpers ──────────────────────────────────────────────────

/// Recursively copy a directory tree.
fn copy_dir_recursive(src: &Path, dst: &Path) -> std::io::Result<()> {
    fs::create_dir_all(dst)?;
    for entry in fs::read_dir(src)? {
        let entry = entry?;
        let src_path = entry.path();
        let dst_path = dst.join(entry.file_name());
        if src_path.is_dir() {
            copy_dir_recursive(&src_path, &dst_path)?;
        } else {
            fs::copy(&src_path, &dst_path)?;
        }
    }
    Ok(())
}

// ── Tests ────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    fn sample_manifest_toml() -> &'static str {
        r#"
name = "test-pack"
version = "1.0.0"
description = "A test skill pack"
author = "Test Author"
trust_level = "community"
agents = ["agent1.toml"]
skills = ["skill1.toml"]
synonyms = ["syn.toml"]
taxonomy = ["tax.toml"]
tools = ["tool1.toml"]
dependencies = ["core-pack"]
"#
    }

    #[test]
    fn test_trust_level_serialization() {
        let json = serde_json::to_string(&TrustLevel::Builtin).unwrap();
        assert_eq!(json, r#""builtin""#);

        let json = serde_json::to_string(&TrustLevel::Verified).unwrap();
        assert_eq!(json, r#""verified""#);

        let json = serde_json::to_string(&TrustLevel::Community).unwrap();
        assert_eq!(json, r#""community""#);

        let round: TrustLevel = serde_json::from_str(r#""verified""#).unwrap();
        assert_eq!(round, TrustLevel::Verified);
    }

    #[test]
    fn test_manifest_parse_toml() {
        let manifest: SkillPackManifest = toml::from_str(sample_manifest_toml()).unwrap();
        assert_eq!(manifest.name, "test-pack");
        assert_eq!(manifest.version, "1.0.0");
        assert_eq!(manifest.trust_level, TrustLevel::Community);
        assert_eq!(manifest.agents, vec!["agent1.toml"]);
        assert_eq!(manifest.dependencies, vec!["core-pack"]);
    }

    #[test]
    fn test_manifest_validate_valid() {
        let manifest: SkillPackManifest = toml::from_str(sample_manifest_toml()).unwrap();
        assert!(SkillPackRegistry::validate(&manifest).is_ok());
    }

    #[test]
    fn test_manifest_validate_missing_name() {
        let toml_str = r#"
name = ""
version = "1.0.0"
description = "desc"
author = "auth"
trust_level = "community"
"#;
        let manifest: SkillPackManifest = toml::from_str(toml_str).unwrap();
        let errors = SkillPackRegistry::validate(&manifest).unwrap_err();
        assert!(errors.iter().any(|e| e.contains("name")));
    }

    #[test]
    fn test_skill_pack_source_variants() {
        let local = SkillPackSource::LocalDir(PathBuf::from("/tmp/pack"));
        assert!(matches!(local, SkillPackSource::LocalDir(_)));

        let git = SkillPackSource::GitUrl {
            url: "https://github.com/example/pack.git".into(),
            branch: Some("main".into()),
        };
        assert!(matches!(git, SkillPackSource::GitUrl { .. }));

        // Roundtrip via JSON
        let json = serde_json::to_string(&git).unwrap();
        let round: SkillPackSource = serde_json::from_str(&json).unwrap();
        assert!(matches!(round, SkillPackSource::GitUrl { .. }));
    }

    #[test]
    fn test_install_report_default() {
        let report = InstallReport::default();
        assert_eq!(report.total(), 0);
        assert!(report.agents_installed.is_empty());
        assert!(report.skills_installed.is_empty());
        assert!(report.synonyms_installed.is_empty());
        assert!(report.taxonomy_installed.is_empty());
        assert!(report.tools_installed.is_empty());
    }

    #[test]
    fn test_list_empty_dir() {
        let tmp = std::env::temp_dir().join("citeindex_test_skillpack_list_empty");
        let _ = fs::remove_dir_all(&tmp);
        fs::create_dir_all(&tmp).unwrap();

        let packs = SkillPackRegistry::list(&tmp).unwrap();
        assert!(packs.is_empty());

        let _ = fs::remove_dir_all(&tmp);
    }
}
