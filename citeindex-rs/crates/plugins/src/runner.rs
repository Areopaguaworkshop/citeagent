//! Plugin command runner — spawn plugin processes from registered commands.

use std::path::Path;
use std::process::{Command, Output};

/// Output from a plugin command execution.
#[derive(Debug)]
pub struct PluginOutput {
    pub success: bool,
    pub exit_code: i32,
    pub stdout: String,
    pub stderr: String,
}

/// Runs plugin commands in the plugin's directory.
pub struct PluginRunner<'a> {
    plugin_dir: &'a Path,
}

impl<'a> PluginRunner<'a> {
    pub fn new(plugin_dir: &'a Path) -> Self {
        Self { plugin_dir }
    }

    /// Run a command synchronously in the plugin directory.
    pub fn run_command_sync(&self, command: &str) -> anyhow::Result<PluginOutput> {
        let parts: Vec<&str> = command.split_whitespace().collect();
        if parts.is_empty() {
            anyhow::bail!("Empty command");
        }

        let output = Command::new(parts[0])
            .args(&parts[1..])
            .current_dir(self.plugin_dir)
            .output()?;

        Ok(Self::to_plugin_output(output))
    }

    /// Run a command asynchronously.
    pub async fn run_command_async(&self, command: &str) -> anyhow::Result<PluginOutput> {
        let parts: Vec<&str> = command.split_whitespace().collect();
        if parts.is_empty() {
            anyhow::bail!("Empty command");
        }

        let output = tokio::process::Command::new(parts[0])
            .args(&parts[1..])
            .current_dir(self.plugin_dir)
            .output()
            .await?;

        Ok(Self::to_plugin_output_from_tokio(output))
    }

    fn to_plugin_output(output: Output) -> PluginOutput {
        PluginOutput {
            success: output.status.success(),
            exit_code: output.status.code().unwrap_or(-1),
            stdout: String::from_utf8_lossy(&output.stdout).to_string(),
            stderr: String::from_utf8_lossy(&output.stderr).to_string(),
        }
    }

    fn to_plugin_output_from_tokio(output: std::process::Output) -> PluginOutput {
        PluginOutput {
            success: output.status.success(),
            exit_code: output.status.code().unwrap_or(-1),
            stdout: String::from_utf8_lossy(&output.stdout).to_string(),
            stderr: String::from_utf8_lossy(&output.stderr).to_string(),
        }
    }
}
