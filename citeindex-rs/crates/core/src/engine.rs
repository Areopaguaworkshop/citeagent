//! Core orchestrator engine — coordinates Python IPC, plugins, memory,
//! and task monitoring.
//!
//! Matches `rust_core_orchestration.yaml`.

use crate::config::CiteIndexConfig;
use crate::ipc::{prepare_runtime_storage, AgentRuntime};
use crate::memory::{MemoryEntry, MemoryStore};
use citeindex_kernel::storage::StorageLayout;
use serde_json::Value;
use std::path::PathBuf;

/// The central orchestrator that ties together all CiteIndex subsystems.
pub struct Engine {
    pub config: CiteIndexConfig,
    pub memory: MemoryStore,
    runtime: AgentRuntime,
}

impl Engine {
    /// Create a new engine with the given configuration.
    pub fn new(config: CiteIndexConfig) -> Self {
        let storage_layout = StorageLayout::new(config.corpus_root.join(".citeindex"));
        let legacy_memory_dir = config.corpus_root.join(".memory");
        let memory = MemoryStore::new(&storage_layout.sessions_dir, Some(&legacy_memory_dir));
        if let Err(error) = prepare_runtime_storage(&config.corpus_root, &storage_layout.root) {
            tracing::warn!(
                "Failed to prepare runtime storage from legacy corpus: {}",
                error
            );
        }
        let runtime = AgentRuntime::new(
            &config.python_bin,
            &storage_layout.root.to_string_lossy(),
            &config.llm.model,
        );
        Self {
            config,
            memory,
            runtime,
        }
    }

    /// Run ingestion via the v12 agent runtime.
    pub async fn ingest(&self, input_path: &str, extra_args: &[&str]) -> anyhow::Result<Value> {
        let corpus = self.config.corpus_root.to_string_lossy();
        self.runtime.ingest(input_path, &corpus, extra_args).await
    }

    /// Run search via the v12 agent runtime.
    pub async fn search(&self, query: &str) -> anyhow::Result<Value> {
        let corpus = self.config.corpus_root.to_string_lossy();
        self.runtime
            .search(query, &corpus, &self.config.tui.cite_style)
            .await
    }

    /// Run chat via the v12 agent runtime.
    pub async fn chat(&self, prompt: &str, thread_id: &str) -> anyhow::Result<Value> {
        let corpus = self.config.corpus_root.to_string_lossy();
        let result = self
            .runtime
            .chat(prompt, &corpus, &self.config.llm.model, thread_id)
            .await?;

        // The Python chat pipeline already saves memory, but we can also
        // save on the Rust side for the Rust memory DAG.
        let answer = result
            .get("answer_human")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let kernel_memory_saved = result
            .get("kernel_memory_save")
            .and_then(|value| value.get("status"))
            .and_then(|value| value.as_str())
            == Some("ok");

        if !answer.is_empty() && !kernel_memory_saved {
            let evidence_ids: Vec<String> = result
                .get("answer_machine")
                .and_then(|m| m.get("evidence"))
                .and_then(|e| e.as_array())
                .map(|arr| {
                    arr.iter()
                        .filter_map(|v| v.get("node_id").and_then(|n| n.as_str()))
                        .map(String::from)
                        .collect()
                })
                .unwrap_or_default();

            let entry = MemoryEntry::new(thread_id, prompt, answer, evidence_ids);
            if let Err(e) = self.memory.save(&entry) {
                tracing::warn!("Failed to save Rust-side memory: {}", e);
            }
        }

        Ok(result)
    }

    /// Search chat memory.
    pub fn memory_search(&self, query: &str, thread_id: Option<&str>) -> Vec<MemoryEntry> {
        self.memory.search(query, thread_id)
    }

    /// Shut down spawned agent processes.
    pub async fn shutdown(&self) -> anyhow::Result<()> {
        self.runtime.shutdown().await
    }

    /// Get the corpus root path.
    pub fn corpus_root(&self) -> &PathBuf {
        &self.config.corpus_root
    }
}
