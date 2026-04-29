//! CLI command definitions and dispatch — kernel-side implementations.
//!
//! The actual binary entry point (clap parsing) lives in a separate crate,
//! but the kernel provides the command logic dispatched here.

use std::path::{Path, PathBuf};
use std::time::Instant;

use serde::{Deserialize, Serialize};

use crate::storage::StorageLayout;
use crate::trace::TraceRetention;

// ── Command enum ─────────────────────────────────────────────

/// All CLI subcommands recognized by CiteIndex v12.
#[derive(Debug, Clone)]
pub enum CliCommand {
    Init {
        data_dir: Option<PathBuf>,
        force: bool,
    },
    IndexRebuild {
        index: Option<String>,
    },
    FineTunePrune {
        max_age_days: u32,
        dry_run: bool,
    },
    SkillpackList,
    SkillpackInstall {
        source: String,
    },
    SkillpackUninstall {
        name: String,
    },
    Backup {
        output_path: PathBuf,
    },
    Restore {
        input_path: PathBuf,
    },
    LoraTrain {
        adapter_name: String,
        base_model: Option<String>,
    },
    Migrate {
        corpus_dir: PathBuf,
        dry_run: bool,
    },
    Status,
    TracePrune {
        retention_days: Option<u32>,
    },
    Maintenance,
}

// ── Result type ──────────────────────────────────────────────

/// Outcome of a CLI command execution.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CliResult {
    pub success: bool,
    pub message: String,
    pub details: Option<serde_json::Value>,
    pub duration_ms: u64,
}

// ── Backup manifest ──────────────────────────────────────────

/// Manifest written into backup archives for restore validation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BackupManifest {
    pub version: String,
    pub created_at: String,
    pub data_dir: String,
    pub includes: Vec<String>,
}

// ── Dispatch ─────────────────────────────────────────────────

/// Route a [`CliCommand`] to its implementation and return a [`CliResult`].
///
/// `data_dir` overrides the default storage root (`~/.citeindex`).
/// Most commands are stubs that describe what they would do; `Init`,
/// `Status`, and `TracePrune` have real implementations.
pub fn dispatch(cmd: CliCommand, data_dir: Option<&Path>) -> anyhow::Result<CliResult> {
    let start = Instant::now();

    let (success, message, details) = match cmd {
        CliCommand::Init {
            data_dir: init_dir,
            force,
        } => {
            let resolve_dir = init_dir.as_deref().or(data_dir);
            let layout = StorageLayout::resolve(resolve_dir);
            crate::storage::init(&layout, force)?;
            let msg = format!("Initialized CiteIndex home at {}", layout.root.display());
            (
                true,
                msg,
                Some(serde_json::json!({ "root": layout.root.display().to_string() })),
            )
        }

        CliCommand::IndexRebuild { index } => {
            let target = index.as_deref().unwrap_or("all");
            let msg = format!("Would rebuild index: {target}");
            (true, msg, Some(serde_json::json!({ "index": target })))
        }

        CliCommand::FineTunePrune {
            max_age_days,
            dry_run,
        } => {
            let msg = format!(
                "Would prune fine-tune samples older than {max_age_days} days (dry_run={dry_run})"
            );
            (
                true,
                msg,
                Some(serde_json::json!({ "max_age_days": max_age_days, "dry_run": dry_run })),
            )
        }

        CliCommand::SkillpackList => {
            let msg = "Would list installed skill packs".to_string();
            (true, msg, None)
        }

        CliCommand::SkillpackInstall { source } => {
            let msg = format!("Would install skill pack from: {source}");
            (true, msg, Some(serde_json::json!({ "source": source })))
        }

        CliCommand::SkillpackUninstall { name } => {
            let msg = format!("Would uninstall skill pack: {name}");
            (true, msg, Some(serde_json::json!({ "name": name })))
        }

        CliCommand::Backup { output_path } => {
            let msg = format!("Would create backup at {}", output_path.display());
            let manifest = BackupManifest {
                version: env!("CARGO_PKG_VERSION").to_string(),
                created_at: chrono::Utc::now().to_rfc3339(),
                data_dir: data_dir
                    .map(|p| p.display().to_string())
                    .unwrap_or_else(|| "~/.citeindex".into()),
                includes: vec![
                    "config".into(),
                    "indexes".into(),
                    "documents".into(),
                    "citations".into(),
                    "memory".into(),
                ],
            };
            (true, msg, Some(serde_json::to_value(&manifest)?))
        }

        CliCommand::Restore { input_path } => {
            let msg = format!("Would restore from {}", input_path.display());
            (
                true,
                msg,
                Some(serde_json::json!({ "input_path": input_path.display().to_string() })),
            )
        }

        CliCommand::LoraTrain {
            adapter_name,
            base_model,
        } => {
            let model = base_model.as_deref().unwrap_or("default");
            let msg = format!("Would train LoRA adapter '{adapter_name}' on base model '{model}'");
            (
                true,
                msg,
                Some(serde_json::json!({ "adapter_name": adapter_name, "base_model": model })),
            )
        }

        CliCommand::Migrate {
            corpus_dir,
            dry_run,
        } => {
            let msg = format!(
                "Would migrate corpus from {} (dry_run={dry_run})",
                corpus_dir.display()
            );
            (
                true,
                msg,
                Some(
                    serde_json::json!({ "corpus_dir": corpus_dir.display().to_string(), "dry_run": dry_run }),
                ),
            )
        }

        CliCommand::Status => {
            let layout = StorageLayout::resolve(data_dir);
            let exists = layout.root.exists();
            let msg = if exists {
                format!("CiteIndex home exists at {}", layout.root.display())
            } else {
                format!("CiteIndex home not found at {}", layout.root.display())
            };
            let details = serde_json::json!({
                "root": layout.root.display().to_string(),
                "exists": exists,
                "config_dir": layout.config_dir.exists(),
                "indexes_dir": layout.indexes_dir.exists(),
                "traces_dir": layout.traces_dir.exists(),
            });
            (exists, msg, Some(details))
        }

        CliCommand::TracePrune { retention_days } => {
            let days = retention_days.unwrap_or(30);
            let layout = StorageLayout::resolve(data_dir);
            let report = TraceRetention::cleanup(&layout.traces_dir, days)?;
            let msg = format!(
                "Pruned {} directories ({} files), kept {}",
                report.directories_removed, report.files_removed, report.directories_kept,
            );
            (
                true,
                msg,
                Some(serde_json::json!({
                    "retention_days": days,
                    "directories_removed": report.directories_removed,
                    "files_removed": report.files_removed,
                    "directories_kept": report.directories_kept,
                })),
            )
        }

        CliCommand::Maintenance => {
            let msg = "Would run scheduled maintenance (index optimize, trace prune, tmp cleanup)"
                .to_string();
            (true, msg, None)
        }
    };

    let duration_ms = start.elapsed().as_millis() as u64;

    Ok(CliResult {
        success,
        message,
        details,
        duration_ms,
    })
}

// ── Formatting ───────────────────────────────────────────────

/// Format a [`CliResult`] for terminal output.
pub fn format_result(result: &CliResult) -> String {
    let status = if result.success { "✓" } else { "✗" };
    let mut out = format!("{status} {}", result.message);
    if let Some(ref details) = result.details {
        if let Ok(pretty) = serde_json::to_string_pretty(details) {
            out.push('\n');
            out.push_str(&pretty);
        }
    }
    out.push_str(&format!("\n({} ms)", result.duration_ms));
    out
}

// ── Tests ────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn test_cli_command_variants() {
        // Ensure all variants can be constructed and debug-printed.
        let cmds: Vec<CliCommand> = vec![
            CliCommand::Init {
                data_dir: None,
                force: false,
            },
            CliCommand::IndexRebuild { index: None },
            CliCommand::FineTunePrune {
                max_age_days: 90,
                dry_run: true,
            },
            CliCommand::SkillpackList,
            CliCommand::SkillpackInstall {
                source: "https://example.com/pack.tar.gz".into(),
            },
            CliCommand::SkillpackUninstall {
                name: "my-pack".into(),
            },
            CliCommand::Backup {
                output_path: PathBuf::from("/tmp/backup.tar.gz"),
            },
            CliCommand::Restore {
                input_path: PathBuf::from("/tmp/backup.tar.gz"),
            },
            CliCommand::LoraTrain {
                adapter_name: "scholarly".into(),
                base_model: None,
            },
            CliCommand::Migrate {
                corpus_dir: PathBuf::from("/data/corpus"),
                dry_run: false,
            },
            CliCommand::Status,
            CliCommand::TracePrune {
                retention_days: Some(7),
            },
            CliCommand::Maintenance,
        ];
        for cmd in &cmds {
            let dbg = format!("{cmd:?}");
            assert!(!dbg.is_empty());
        }
        assert_eq!(cmds.len(), 13);
    }

    #[test]
    fn test_dispatch_init() {
        let tmp = std::env::temp_dir().join(format!("citeindex_cli_init_{}", uuid::Uuid::new_v4()));
        let cmd = CliCommand::Init {
            data_dir: Some(tmp.clone()),
            force: true,
        };
        let result = dispatch(cmd, None).unwrap();
        assert!(result.success);
        assert!(result.message.contains("Initialized"));
        assert!(tmp.exists());
        assert!(tmp.join("config").exists());
        let _ = fs::remove_dir_all(&tmp);
    }

    #[test]
    fn test_dispatch_status_no_dir() {
        let tmp =
            std::env::temp_dir().join(format!("citeindex_cli_status_no_{}", uuid::Uuid::new_v4()));
        // Do NOT create the directory — status should report it missing.
        let cmd = CliCommand::Status;
        let result = dispatch(cmd, Some(&tmp)).unwrap();
        assert!(!result.success);
        assert!(result.message.contains("not found"));
    }

    #[test]
    fn test_dispatch_status_with_dir() {
        let tmp =
            std::env::temp_dir().join(format!("citeindex_cli_status_ok_{}", uuid::Uuid::new_v4()));
        // Initialize the layout so Status finds a real home.
        let layout = StorageLayout::new(tmp.clone());
        crate::storage::init(&layout, true).unwrap();

        let cmd = CliCommand::Status;
        let result = dispatch(cmd, Some(&tmp)).unwrap();
        assert!(result.success);
        assert!(result.message.contains("exists"));
        let details = result.details.unwrap();
        assert_eq!(details["exists"], true);
        assert_eq!(details["config_dir"], true);

        let _ = fs::remove_dir_all(&tmp);
    }

    #[test]
    fn test_dispatch_trace_prune() {
        let tmp =
            std::env::temp_dir().join(format!("citeindex_cli_trace_{}", uuid::Uuid::new_v4()));
        let traces_dir = tmp.join("traces");
        fs::create_dir_all(&traces_dir).unwrap();

        // Create an old trace directory (60 days ago)
        let old_date = (chrono::Utc::now() - chrono::Duration::days(60))
            .format("%Y-%m-%d")
            .to_string();
        let old_dir = traces_dir.join(&old_date);
        fs::create_dir_all(&old_dir).unwrap();
        fs::write(old_dir.join("trace.jsonl"), "{}").unwrap();

        let cmd = CliCommand::TracePrune {
            retention_days: Some(30),
        };
        let result = dispatch(cmd, Some(&tmp)).unwrap();
        assert!(result.success);
        assert!(result.message.contains("Pruned"));
        assert!(!old_dir.exists());

        let _ = fs::remove_dir_all(&tmp);
    }

    #[test]
    fn test_dispatch_maintenance() {
        let cmd = CliCommand::Maintenance;
        let result = dispatch(cmd, None).unwrap();
        assert!(result.success);
        assert!(result.message.contains("maintenance"));
    }

    #[test]
    fn test_format_result_success() {
        let result = CliResult {
            success: true,
            message: "All good".into(),
            details: Some(serde_json::json!({ "count": 42 })),
            duration_ms: 123,
        };
        let out = format_result(&result);
        assert!(out.contains('✓'));
        assert!(out.contains("All good"));
        assert!(out.contains("42"));
        assert!(out.contains("123 ms"));
    }

    #[test]
    fn test_format_result_failure() {
        let result = CliResult {
            success: false,
            message: "Something broke".into(),
            details: None,
            duration_ms: 5,
        };
        let out = format_result(&result);
        assert!(out.contains('✗'));
        assert!(out.contains("Something broke"));
        assert!(out.contains("5 ms"));
        assert!(!out.contains('{'));
    }
}
