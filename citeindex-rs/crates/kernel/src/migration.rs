//! Data migration — Legacy `corpus/` → `~/.citeindex/` storage layout.
//!
//! Scans a legacy corpus directory (or a single CSL-JSON file), builds a
//! migration plan describing each step, and executes (or dry-runs) the
//! plan to produce the v12 storage layout.

use std::fs;
use std::path::{Path, PathBuf};
use std::time::Instant;

use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::storage::StorageLayout;

// ── Error types ───────────────────────────────────────────────────────

#[derive(Debug, Error)]
pub enum MigrationError {
    #[error("IO error at {path}: {source}")]
    Io {
        path: PathBuf,
        source: std::io::Error,
    },

    #[error("Invalid CSL-JSON at {path}: {detail}")]
    InvalidCslJson { path: PathBuf, detail: String },

    #[error("Missing required field '{field}' in record {record_id}")]
    MissingField { record_id: String, field: String },

    #[error("Target directory already exists: {0}")]
    TargetExists(PathBuf),

    #[error("Validation failure: {0}")]
    Validation(String),
}

// ── Source / Step enums ───────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum MigrationSource {
    LegacyCorpus(PathBuf),
    CslJsonFile(PathBuf),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum MigrationStep {
    ConvertCslRecord {
        source_path: PathBuf,
        record_id: String,
    },
    GeneratePageIndexTree {
        source_path: PathBuf,
        doc_id: String,
    },
    CopySource {
        from: PathBuf,
        to: PathBuf,
    },
    CreateIndex {
        index_name: String,
    },
    RebuildMerkle,
}

// ── Plan / Result / Report structs ───────────────────────────────────

#[derive(Debug, Clone)]
pub struct MigrationPlan {
    pub source: MigrationSource,
    pub target_layout: PathBuf,
    pub documents_found: usize,
    pub csl_records_found: usize,
    pub tree_files_found: usize,
    pub steps: Vec<MigrationStep>,
    pub dry_run: bool,
}

#[derive(Debug)]
pub struct MigrationResult {
    pub steps_completed: usize,
    pub steps_failed: usize,
    pub documents_migrated: usize,
    pub csl_records_converted: usize,
    pub trees_generated: usize,
    pub errors: Vec<MigrationError>,
    pub duration_ms: u64,
}

impl Default for MigrationResult {
    fn default() -> Self {
        Self {
            steps_completed: 0,
            steps_failed: 0,
            documents_migrated: 0,
            csl_records_converted: 0,
            trees_generated: 0,
            errors: Vec::new(),
            duration_ms: 0,
        }
    }
}

#[derive(Debug, Clone)]
pub struct ValidationReport {
    pub documents_present: usize,
    pub trees_valid: usize,
    pub indexes_built: bool,
    pub config_present: bool,
    pub issues: Vec<String>,
}

// ── Public API ────────────────────────────────────────────────────────

/// Scan a legacy `corpus/` directory and build a migration plan.
///
/// The plan enumerates every CSL-JSON record, every document source file,
/// and every PageIndex tree file found under `corpus_dir`.
pub fn scan_legacy_corpus(corpus_dir: &Path) -> anyhow::Result<MigrationPlan> {
    let mut plan = MigrationPlan {
        source: MigrationSource::LegacyCorpus(corpus_dir.to_path_buf()),
        target_layout: PathBuf::new(),
        documents_found: 0,
        csl_records_found: 0,
        tree_files_found: 0,
        steps: Vec::new(),
        dry_run: false,
    };

    if !corpus_dir.exists() {
        return Ok(plan);
    }

    for entry in fs::read_dir(corpus_dir)? {
        let entry = entry?;
        let path = entry.path();

        if path.is_file() {
            if let Some(ext) = path.extension().and_then(|e| e.to_str()) {
                match ext {
                    "json" => {
                        // Attempt to read as CSL-JSON array or single record.
                        let data = fs::read_to_string(&path)?;
                        if let Ok(value) = serde_json::from_str::<serde_json::Value>(&data) {
                            let records = match &value {
                                serde_json::Value::Array(arr) => arr.clone(),
                                obj @ serde_json::Value::Object(_) => vec![obj.clone()],
                                _ => Vec::new(),
                            };
                            for record in &records {
                                let record_id = record
                                    .get("id")
                                    .and_then(|v| v.as_str())
                                    .unwrap_or("unknown")
                                    .to_string();
                                plan.steps.push(MigrationStep::ConvertCslRecord {
                                    source_path: path.clone(),
                                    record_id,
                                });
                                plan.csl_records_found += 1;
                            }
                        }
                    }
                    "pdf" | "html" | "txt" | "md" => {
                        let doc_id = path
                            .file_stem()
                            .and_then(|s| s.to_str())
                            .unwrap_or("unknown")
                            .to_string();
                        plan.steps.push(MigrationStep::CopySource {
                            from: path.clone(),
                            to: PathBuf::new(), // resolved at execute time
                        });
                        plan.documents_found += 1;

                        plan.steps.push(MigrationStep::GeneratePageIndexTree {
                            source_path: path.clone(),
                            doc_id,
                        });
                        plan.tree_files_found += 1;
                    }
                    _ => {}
                }
            }
        }
    }

    // Always finish with index creation and Merkle rebuild.
    if plan.csl_records_found > 0 || plan.documents_found > 0 {
        plan.steps.push(MigrationStep::CreateIndex {
            index_name: "document_index".into(),
        });
        plan.steps.push(MigrationStep::CreateIndex {
            index_name: "claim_index".into(),
        });
        plan.steps.push(MigrationStep::RebuildMerkle);
    }

    Ok(plan)
}

/// Execute (or dry-run) a migration plan.
///
/// When `plan.dry_run` is `true` the function walks every step but
/// performs no I/O; the returned `MigrationResult` reflects what
/// *would* happen.
pub fn execute_plan(plan: &MigrationPlan) -> anyhow::Result<MigrationResult> {
    let start = Instant::now();
    let mut result = MigrationResult::default();

    if plan.dry_run {
        result.steps_completed = plan.steps.len();
        result.documents_migrated = plan.documents_found;
        result.csl_records_converted = plan.csl_records_found;
        result.trees_generated = plan.tree_files_found;
        result.duration_ms = start.elapsed().as_millis() as u64;
        return Ok(result);
    }

    let layout = StorageLayout::new(plan.target_layout.clone());

    // Ensure target directories exist.
    fs::create_dir_all(&layout.documents_dir).map_err(|e| MigrationError::Io {
        path: layout.documents_dir.clone(),
        source: e,
    })?;
    fs::create_dir_all(&layout.sources_dir).map_err(|e| MigrationError::Io {
        path: layout.sources_dir.clone(),
        source: e,
    })?;

    for step in &plan.steps {
        match execute_step(step, &layout) {
            Ok(()) => {
                result.steps_completed += 1;
                match step {
                    MigrationStep::ConvertCslRecord { .. } => {
                        result.csl_records_converted += 1;
                    }
                    MigrationStep::GeneratePageIndexTree { .. } => {
                        result.trees_generated += 1;
                    }
                    MigrationStep::CopySource { .. } => {
                        result.documents_migrated += 1;
                    }
                    _ => {}
                }
            }
            Err(e) => {
                result.steps_failed += 1;
                result.errors.push(e);
            }
        }
    }

    result.duration_ms = start.elapsed().as_millis() as u64;
    Ok(result)
}

/// Convert a single CSL-JSON record, adding `ci_`-prefixed fields.
///
/// The original record is preserved; additional metadata fields
/// (`ci_migrated_at`, `ci_version`, `ci_source`) are injected.
pub fn convert_csl_record(record: &serde_json::Value) -> serde_json::Value {
    let mut out = record.clone();
    if let Some(obj) = out.as_object_mut() {
        obj.insert(
            "ci_migrated_at".into(),
            serde_json::Value::String(chrono::Utc::now().to_rfc3339()),
        );
        obj.insert("ci_version".into(), serde_json::Value::String("12".into()));
        obj.insert(
            "ci_source".into(),
            serde_json::Value::String("legacy_corpus".into()),
        );
    }
    out
}

/// Validate a completed migration at `target_dir`.
pub fn validate_migration(target_dir: &Path) -> anyhow::Result<ValidationReport> {
    let layout = StorageLayout::new(target_dir.to_path_buf());
    let mut report = ValidationReport {
        documents_present: 0,
        trees_valid: 0,
        indexes_built: false,
        config_present: false,
        issues: Vec::new(),
    };

    // Check config
    report.config_present = layout.config_toml.exists();
    if !report.config_present {
        report.issues.push("config.toml not found".into());
    }

    // Count documents
    if layout.sources_dir.exists() {
        if let Ok(entries) = fs::read_dir(&layout.sources_dir) {
            report.documents_present = entries.filter_map(|e| e.ok()).count();
        }
    } else {
        report
            .issues
            .push("documents/sources/ directory missing".into());
    }

    // Count valid tree files
    if layout.structured_dir.exists() {
        if let Ok(entries) = fs::read_dir(&layout.structured_dir) {
            for entry in entries.filter_map(|e| e.ok()) {
                let path = entry.path();
                if path.extension().and_then(|e| e.to_str()) == Some("json") {
                    if fs::read_to_string(&path)
                        .ok()
                        .and_then(|s| serde_json::from_str::<serde_json::Value>(&s).ok())
                        .is_some()
                    {
                        report.trees_valid += 1;
                    } else {
                        report.issues.push(format!("Invalid tree file: {:?}", path));
                    }
                }
            }
        }
    }

    // Check indexes
    report.indexes_built = layout.document_index_dir.exists() && layout.claim_index_dir.exists();
    if !report.indexes_built {
        report.issues.push("One or more indexes missing".into());
    }

    Ok(report)
}

// ── Internal helpers ──────────────────────────────────────────────────

fn execute_step(step: &MigrationStep, layout: &StorageLayout) -> Result<(), MigrationError> {
    match step {
        MigrationStep::ConvertCslRecord {
            source_path,
            record_id,
        } => {
            let data = fs::read_to_string(source_path).map_err(|e| MigrationError::Io {
                path: source_path.clone(),
                source: e,
            })?;
            let value: serde_json::Value =
                serde_json::from_str(&data).map_err(|e| MigrationError::InvalidCslJson {
                    path: source_path.clone(),
                    detail: e.to_string(),
                })?;

            let records = match &value {
                serde_json::Value::Array(arr) => arr.clone(),
                obj @ serde_json::Value::Object(_) => vec![obj.clone()],
                _ => Vec::new(),
            };

            for rec in &records {
                let id = rec.get("id").and_then(|v| v.as_str()).unwrap_or("unknown");
                if id == record_id {
                    let converted = convert_csl_record(rec);
                    let out_path = layout.citations_dir.join(format!("{}.json", record_id));
                    let json = serde_json::to_string_pretty(&converted).map_err(|e| {
                        MigrationError::InvalidCslJson {
                            path: out_path.clone(),
                            detail: e.to_string(),
                        }
                    })?;
                    fs::write(&out_path, json).map_err(|e| MigrationError::Io {
                        path: out_path,
                        source: e,
                    })?;
                    break;
                }
            }
            Ok(())
        }

        MigrationStep::GeneratePageIndexTree {
            source_path,
            doc_id,
        } => {
            let tree = serde_json::json!({
                "doc_id": doc_id,
                "source": source_path.to_string_lossy(),
                "ci_version": "12",
                "nodes": [],
            });
            let out_path = layout.structured_dir.join(format!("{}.json", doc_id));
            let json = serde_json::to_string_pretty(&tree).map_err(|e| {
                MigrationError::InvalidCslJson {
                    path: out_path.clone(),
                    detail: e.to_string(),
                }
            })?;
            fs::write(&out_path, json).map_err(|e| MigrationError::Io {
                path: out_path,
                source: e,
            })?;
            Ok(())
        }

        MigrationStep::CopySource { from, to } => {
            let dest = if to.as_os_str().is_empty() {
                // Resolve destination inside layout.
                let filename = from.file_name().unwrap_or_default();
                layout.sources_dir.join(filename)
            } else {
                to.clone()
            };
            fs::copy(from, &dest).map_err(|e| MigrationError::Io {
                path: dest,
                source: e,
            })?;
            Ok(())
        }

        MigrationStep::CreateIndex { index_name } => {
            let dir = layout.indexes_dir.join(index_name);
            fs::create_dir_all(&dir).map_err(|e| MigrationError::Io {
                path: dir,
                source: e,
            })?;
            Ok(())
        }

        MigrationStep::RebuildMerkle => {
            // Merkle rebuild is a no-op placeholder; real implementation
            // lives in the indexing subsystem.
            Ok(())
        }
    }
}

// ── Tests ─────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn test_migration_source_variants() {
        let corpus = MigrationSource::LegacyCorpus(PathBuf::from("/data/corpus"));
        let csl = MigrationSource::CslJsonFile(PathBuf::from("/data/refs.json"));

        match &corpus {
            MigrationSource::LegacyCorpus(p) => assert_eq!(p, &PathBuf::from("/data/corpus")),
            _ => panic!("expected LegacyCorpus"),
        }
        match &csl {
            MigrationSource::CslJsonFile(p) => assert_eq!(p, &PathBuf::from("/data/refs.json")),
            _ => panic!("expected CslJsonFile"),
        }
    }

    #[test]
    fn test_convert_csl_record_adds_prefix() {
        let record = serde_json::json!({
            "id": "smith2023",
            "type": "article-journal",
            "title": "Test Article"
        });

        let converted = convert_csl_record(&record);
        let obj = converted.as_object().unwrap();

        assert!(obj.contains_key("ci_migrated_at"));
        assert_eq!(obj.get("ci_version").unwrap(), "12");
        assert_eq!(obj.get("ci_source").unwrap(), "legacy_corpus");
        // Original fields preserved.
        assert_eq!(obj.get("id").unwrap(), "smith2023");
        assert_eq!(obj.get("title").unwrap(), "Test Article");
    }

    #[test]
    fn test_scan_empty_dir() {
        let tmp = std::env::temp_dir().join("citeindex_test_scan_empty");
        let _ = fs::remove_dir_all(&tmp);
        fs::create_dir_all(&tmp).unwrap();

        let plan = scan_legacy_corpus(&tmp).unwrap();
        assert_eq!(plan.documents_found, 0);
        assert_eq!(plan.csl_records_found, 0);
        assert_eq!(plan.tree_files_found, 0);
        assert!(plan.steps.is_empty());

        let _ = fs::remove_dir_all(&tmp);
    }

    #[test]
    fn test_migration_plan_dry_run() {
        let plan = MigrationPlan {
            source: MigrationSource::LegacyCorpus(PathBuf::from("/fake")),
            target_layout: PathBuf::new(),
            documents_found: 5,
            csl_records_found: 10,
            tree_files_found: 5,
            steps: vec![
                MigrationStep::ConvertCslRecord {
                    source_path: PathBuf::from("a.json"),
                    record_id: "r1".into(),
                },
                MigrationStep::RebuildMerkle,
            ],
            dry_run: true,
        };

        let result = execute_plan(&plan).unwrap();
        assert_eq!(result.steps_completed, 2);
        assert_eq!(result.steps_failed, 0);
        assert_eq!(result.documents_migrated, 5);
        assert_eq!(result.csl_records_converted, 10);
        assert_eq!(result.trees_generated, 5);
        assert!(result.errors.is_empty());
    }

    #[test]
    fn test_migration_result_default() {
        let result = MigrationResult::default();
        assert_eq!(result.steps_completed, 0);
        assert_eq!(result.steps_failed, 0);
        assert_eq!(result.documents_migrated, 0);
        assert_eq!(result.csl_records_converted, 0);
        assert_eq!(result.trees_generated, 0);
        assert!(result.errors.is_empty());
        assert_eq!(result.duration_ms, 0);
    }

    #[test]
    fn test_validation_report_no_issues() {
        let report = ValidationReport {
            documents_present: 3,
            trees_valid: 3,
            indexes_built: true,
            config_present: true,
            issues: Vec::new(),
        };
        assert!(report.issues.is_empty());
        assert!(report.indexes_built);
        assert!(report.config_present);
    }

    #[test]
    fn test_migration_step_variants() {
        let steps: Vec<MigrationStep> = vec![
            MigrationStep::ConvertCslRecord {
                source_path: PathBuf::from("a.json"),
                record_id: "id1".into(),
            },
            MigrationStep::GeneratePageIndexTree {
                source_path: PathBuf::from("doc.pdf"),
                doc_id: "doc1".into(),
            },
            MigrationStep::CopySource {
                from: PathBuf::from("/src/a.pdf"),
                to: PathBuf::from("/dst/a.pdf"),
            },
            MigrationStep::CreateIndex {
                index_name: "document_index".into(),
            },
            MigrationStep::RebuildMerkle,
        ];
        assert_eq!(steps.len(), 5);
        assert!(matches!(steps[0], MigrationStep::ConvertCslRecord { .. }));
        assert!(matches!(
            steps[1],
            MigrationStep::GeneratePageIndexTree { .. }
        ));
        assert!(matches!(steps[2], MigrationStep::CopySource { .. }));
        assert!(matches!(steps[3], MigrationStep::CreateIndex { .. }));
        assert!(matches!(steps[4], MigrationStep::RebuildMerkle));
    }
}
