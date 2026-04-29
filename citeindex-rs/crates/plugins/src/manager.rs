//! Plugin manager — install, enable, disable, list plugins.
//!
//! Matches `plugin_add_system.yaml` lifecycle.

use crate::manifest::{ManifestError, PluginManifest};
use crate::runner::PluginRunner;
use std::collections::HashMap;
use std::path::{Path, PathBuf};

/// A registered plugin with its manifest and directory.
#[derive(Debug, Clone)]
pub struct RegisteredPlugin {
    pub manifest: PluginManifest,
    pub directory: PathBuf,
    pub enabled: bool,
}

/// Manages the lifecycle of CiteIndex plugins.
pub struct PluginManager {
    plugins_dir: PathBuf,
    registry: HashMap<String, RegisteredPlugin>,
}

impl PluginManager {
    pub fn new(plugins_dir: &Path) -> Self {
        std::fs::create_dir_all(plugins_dir).ok();
        Self {
            plugins_dir: plugins_dir.to_path_buf(),
            registry: HashMap::new(),
        }
    }

    /// Scan the plugins directory and load all valid plugins.
    pub fn discover(&mut self) {
        self.registry.clear();

        if let Ok(entries) = std::fs::read_dir(&self.plugins_dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                if !path.is_dir() {
                    continue;
                }

                match PluginManifest::load(&path) {
                    Ok(manifest) => {
                        let name = manifest.name.clone();
                        tracing::info!(plugin = %name, "Discovered plugin");
                        self.registry.insert(
                            name,
                            RegisteredPlugin {
                                manifest,
                                directory: path,
                                enabled: true,
                            },
                        );
                    }
                    Err(e) => {
                        tracing::debug!(
                            path = %path.display(),
                            error = %e,
                            "Skipping directory (not a valid plugin)"
                        );
                    }
                }
            }
        }
    }

    /// Install a plugin from a local path.
    ///
    /// Validates the manifest, optionally runs the test command, then copies
    /// the plugin into the plugins directory.
    pub fn install_from_path(
        &mut self,
        source: &Path,
        run_tests: bool,
    ) -> Result<String, PluginInstallError> {
        // Step 1: Validate manifest
        let manifest = PluginManifest::load(source).map_err(PluginInstallError::Manifest)?;

        let name = manifest.name.clone();
        tracing::info!(plugin = %name, "Validating plugin manifest");

        // Step 2: Optional test
        if run_tests {
            if let Some(ref test_cmd) = manifest.test_command {
                tracing::info!(plugin = %name, cmd = %test_cmd, "Running plugin test");
                let runner = PluginRunner::new(source);
                match runner.run_command_sync(test_cmd) {
                    Ok(output) if output.success => {
                        tracing::info!(plugin = %name, "Plugin test passed");
                    }
                    Ok(output) => {
                        return Err(PluginInstallError::TestFailed(format!(
                            "Test exited with code {}: {}",
                            output.exit_code, output.stderr
                        )));
                    }
                    Err(e) => {
                        return Err(PluginInstallError::TestFailed(e.to_string()));
                    }
                }
            }
        }

        // Step 3: Copy to plugins directory
        let dest = self.plugins_dir.join(&name);
        if dest.exists() {
            tracing::warn!(plugin = %name, "Overwriting existing plugin");
            std::fs::remove_dir_all(&dest).ok();
        }
        copy_dir_recursive(source, &dest)
            .map_err(|e| PluginInstallError::CopyFailed(e.to_string()))?;

        // Step 4: Register
        self.registry.insert(
            name.clone(),
            RegisteredPlugin {
                manifest,
                directory: dest,
                enabled: true,
            },
        );

        tracing::info!(plugin = %name, "Plugin installed successfully");
        Ok(name)
    }

    /// Install a plugin from a git URL.
    pub fn install_from_git(
        &mut self,
        url: &str,
        run_tests: bool,
    ) -> Result<String, PluginInstallError> {
        // Clone to a temp directory, then install from path
        let tmp = std::env::temp_dir().join(format!(
            "citeindex-plugin-{}",
            chrono::Utc::now().timestamp()
        ));
        let status = std::process::Command::new("git")
            .args(["clone", "--depth=1", url, &tmp.to_string_lossy()])
            .status()
            .map_err(|e| PluginInstallError::GitCloneFailed(e.to_string()))?;

        if !status.success() {
            return Err(PluginInstallError::GitCloneFailed(format!(
                "git clone exited with {:?}",
                status.code()
            )));
        }

        let result = self.install_from_path(&tmp, run_tests);
        std::fs::remove_dir_all(&tmp).ok();
        result
    }

    /// Enable a plugin by name.
    pub fn enable(&mut self, name: &str) -> bool {
        if let Some(plugin) = self.registry.get_mut(name) {
            plugin.enabled = true;
            true
        } else {
            false
        }
    }

    /// Disable a plugin by name.
    pub fn disable(&mut self, name: &str) -> bool {
        if let Some(plugin) = self.registry.get_mut(name) {
            plugin.enabled = false;
            true
        } else {
            false
        }
    }

    /// Get a plugin by name.
    pub fn get(&self, name: &str) -> Option<&RegisteredPlugin> {
        self.registry.get(name)
    }

    /// List all registered plugins.
    pub fn list(&self) -> Vec<&RegisteredPlugin> {
        let mut plugins: Vec<_> = self.registry.values().collect();
        plugins.sort_by_key(|p| &p.manifest.name);
        plugins
    }

    /// Get all commands from all enabled plugins.
    pub fn all_commands(&self) -> Vec<(String, String, PathBuf)> {
        let mut cmds = Vec::new();
        for plugin in self.registry.values() {
            if !plugin.enabled {
                continue;
            }
            for (cmd_name, cmd_value) in &plugin.manifest.commands {
                cmds.push((
                    cmd_name.clone(),
                    cmd_value.clone(),
                    plugin.directory.clone(),
                ));
            }
        }
        cmds.sort_by(|a, b| a.0.cmp(&b.0));
        cmds
    }
}

#[derive(Debug, thiserror::Error)]
pub enum PluginInstallError {
    #[error("Invalid manifest: {0}")]
    Manifest(#[from] ManifestError),

    #[error("Plugin test failed: {0}")]
    TestFailed(String),

    #[error("Failed to copy plugin: {0}")]
    CopyFailed(String),

    #[error("Git clone failed: {0}")]
    GitCloneFailed(String),
}

/// Recursively copy a directory.
fn copy_dir_recursive(src: &Path, dst: &Path) -> std::io::Result<()> {
    std::fs::create_dir_all(dst)?;
    for entry in std::fs::read_dir(src)? {
        let entry = entry?;
        let ty = entry.file_type()?;
        let dest_path = dst.join(entry.file_name());
        if ty.is_dir() {
            copy_dir_recursive(&entry.path(), &dest_path)?;
        } else {
            std::fs::copy(entry.path(), &dest_path)?;
        }
    }
    Ok(())
}
