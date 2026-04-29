//! Rust-native memory manager — Merkle DAG for chat memory with
//! file-based persistence and optional PostgreSQL backend.
//!
//! Matches Phase 3.4 and `rust_core_orchestration.yaml → manage_memory`.

use crate::merkle::{build_merkle_tree, sha256_hex, MerkleTree};
use chrono::Utc;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use std::fs::{self, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};

/// A single memory entry persisted to JSONL.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryEntry {
    pub entry_id: String,
    pub timestamp: String,
    pub thread_id: String,
    pub query: String,
    pub response: String,
    pub evidence_node_ids: Vec<String>,
    pub sha256: String,
}

impl MemoryEntry {
    pub fn new(
        thread_id: &str,
        query: &str,
        response: &str,
        evidence_node_ids: Vec<String>,
    ) -> Self {
        let timestamp = Utc::now().format("%Y-%m-%dT%H:%M:%S+00:00").to_string();
        let payload = format!("{}|{}|{}", timestamp, query, response);
        let hash = sha256_hex(&payload);
        let entry_id = hash[..16].to_string();

        Self {
            entry_id,
            timestamp,
            thread_id: thread_id.into(),
            query: query.into(),
            response: response.into(),
            evidence_node_ids,
            sha256: hash,
        }
    }
}

/// File-based JSONL memory store with Merkle DAG support.
pub struct MemoryStore {
    memory_dir: PathBuf,
    legacy_memory_dir: Option<PathBuf>,
}

impl MemoryStore {
    pub fn new(memory_dir: &Path, legacy_memory_dir: Option<&Path>) -> Self {
        fs::create_dir_all(memory_dir).ok();
        Self {
            memory_dir: memory_dir.to_path_buf(),
            legacy_memory_dir: legacy_memory_dir.map(Path::to_path_buf),
        }
    }

    /// Save a memory entry to the thread's JSONL file.
    pub fn save(&self, entry: &MemoryEntry) -> anyhow::Result<()> {
        let path = self.thread_path(&entry.thread_id);
        let mut file = OpenOptions::new().create(true).append(true).open(&path)?;
        let line = serde_json::to_string(entry)?;
        writeln!(file, "{}", line)?;
        tracing::info!(
            entry_id = %entry.entry_id,
            thread = %entry.thread_id,
            "Memory entry saved"
        );
        Ok(())
    }

    /// Load all entries for a thread.
    pub fn load_thread(&self, thread_id: &str) -> Vec<MemoryEntry> {
        let mut by_id = HashMap::new();

        if let Some(legacy_dir) = self.legacy_memory_dir.as_ref() {
            for entry in self.load_thread_from_dir(legacy_dir, thread_id) {
                by_id.insert(entry.entry_id.clone(), entry);
            }
        }
        for entry in self.load_thread_from_dir(&self.memory_dir, thread_id) {
            by_id.insert(entry.entry_id.clone(), entry);
        }

        let mut entries = by_id.into_values().collect::<Vec<_>>();
        entries.sort_by(|a, b| a.timestamp.cmp(&b.timestamp));
        entries
    }

    /// Simple keyword search across all threads (or a specific thread).
    pub fn search(&self, query: &str, thread_id: Option<&str>) -> Vec<MemoryEntry> {
        let query_lower = query.to_lowercase();
        let keywords: Vec<&str> = query_lower.split_whitespace().collect();
        if keywords.is_empty() {
            return Vec::new();
        }

        let threads = match thread_id {
            Some(tid) => vec![tid.to_string()],
            None => self.list_threads(),
        };

        let mut results: Vec<(usize, MemoryEntry)> = Vec::new();
        for tid in &threads {
            for entry in self.load_thread(tid) {
                let text = format!("{} {}", entry.query, entry.response).to_lowercase();
                let hits = keywords.iter().filter(|kw| text.contains(*kw)).count();
                if hits > 0 {
                    results.push((hits, entry));
                }
            }
        }

        results.sort_by(|a, b| b.0.cmp(&a.0));
        results.into_iter().map(|(_, e)| e).collect()
    }

    /// Build a Merkle tree for all entries in a thread.
    pub fn build_merkle_dag(&self, thread_id: &str) -> MerkleTree {
        let entries = self.load_thread(thread_id);
        let hashes: Vec<String> = entries.iter().map(|e| e.sha256.clone()).collect();
        build_merkle_tree(&hashes)
    }

    /// List all thread IDs.
    pub fn list_threads(&self) -> Vec<String> {
        let mut threads = HashSet::new();
        if let Some(legacy_dir) = self.legacy_memory_dir.as_ref() {
            self.collect_thread_names(legacy_dir, &mut threads);
        }
        self.collect_thread_names(&self.memory_dir, &mut threads);

        let mut sorted = threads.into_iter().collect::<Vec<_>>();
        sorted.sort();
        sorted
    }

    fn load_thread_from_dir(&self, dir: &Path, thread_id: &str) -> Vec<MemoryEntry> {
        let path = self.thread_path_in_dir(dir, thread_id);
        if !path.exists() {
            return Vec::new();
        }

        let file = match fs::File::open(&path) {
            Ok(file) => file,
            Err(_) => return Vec::new(),
        };

        BufReader::new(file)
            .lines()
            .filter_map(|line| line.ok())
            .filter(|line| !line.trim().is_empty())
            .filter_map(|line| serde_json::from_str::<MemoryEntry>(&line).ok())
            .collect()
    }

    fn collect_thread_names(&self, dir: &Path, threads: &mut HashSet<String>) {
        if let Ok(entries) = fs::read_dir(dir) {
            for entry in entries.flatten() {
                if let Some(name) = entry.file_name().to_str() {
                    if name.ends_with(".jsonl") {
                        threads.insert(name.trim_end_matches(".jsonl").to_string());
                    }
                }
            }
        }
    }

    fn thread_path(&self, thread_id: &str) -> PathBuf {
        self.thread_path_in_dir(&self.memory_dir, thread_id)
    }

    fn thread_path_in_dir(&self, dir: &Path, thread_id: &str) -> PathBuf {
        let safe: String = thread_id
            .chars()
            .map(|c| {
                if c.is_alphanumeric() || c == '-' || c == '_' {
                    c
                } else {
                    '_'
                }
            })
            .collect();
        dir.join(format!("{}.jsonl", safe))
    }
}

#[cfg(test)]
mod tests {
    use std::env;

    use super::*;

    #[test]
    fn test_memory_store_merges_primary_and_legacy_entries_by_entry_id() {
        let root = env::temp_dir().join(format!("citeindex-memory-store-{}", uuid::Uuid::new_v4()));
        let primary = root.join("primary");
        let legacy = root.join("legacy");
        fs::create_dir_all(&primary).unwrap();
        fs::create_dir_all(&legacy).unwrap();

        let legacy_entry = MemoryEntry {
            entry_id: "mem-1".into(),
            timestamp: "2026-04-03T10:00:00+00:00".into(),
            thread_id: "thread-1".into(),
            query: "Old query".into(),
            response: "Old response".into(),
            evidence_node_ids: vec![],
            sha256: "old-hash".into(),
        };
        let primary_entry = MemoryEntry {
            entry_id: "mem-1".into(),
            timestamp: "2026-04-03T11:00:00+00:00".into(),
            thread_id: "thread-1".into(),
            query: "New query".into(),
            response: "New response".into(),
            evidence_node_ids: vec!["doc-1:node-1".into()],
            sha256: "new-hash".into(),
        };

        fs::write(
            legacy.join("thread-1.jsonl"),
            format!("{}\n", serde_json::to_string(&legacy_entry).unwrap()),
        )
        .unwrap();
        fs::write(
            primary.join("thread-1.jsonl"),
            format!("{}\n", serde_json::to_string(&primary_entry).unwrap()),
        )
        .unwrap();

        let store = MemoryStore::new(&primary, Some(&legacy));
        let entries = store.load_thread("thread-1");

        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].query, "New query");
        assert_eq!(entries[0].sha256, "new-hash");

        fs::remove_dir_all(root).unwrap();
    }
}
