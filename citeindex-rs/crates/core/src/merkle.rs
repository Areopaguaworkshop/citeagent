//! Rust-native Merkle tree for chat memory and document verification.
//!
//! Each memory entry: `hash(timestamp + conversation_chunk + citation_links)`.

use sha2::{Digest, Sha256};

/// Compute SHA-256 hex digest of a string.
pub fn sha256_hex(data: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(data.as_bytes());
    hex::encode(hasher.finalize())
}

/// A node in the Merkle DAG.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct MerkleNode {
    pub hash: String,
    pub left: Option<String>,
    pub right: Option<String>,
}

/// Build a deterministic Merkle tree from leaf hashes.
/// Odd nodes are duplicated at each level for deterministic pairing.
/// Returns (root_hash, levels).
pub fn build_merkle_tree(leaf_hashes: &[String]) -> MerkleTree {
    let leaves = if leaf_hashes.is_empty() {
        vec![sha256_hex("")]
    } else {
        leaf_hashes.to_vec()
    };

    let mut levels: Vec<Vec<String>> = vec![leaves.clone()];

    while levels.last().map_or(true, |l| l.len() > 1) {
        let current = levels.last().unwrap();
        let mut next = Vec::new();
        let mut i = 0;
        while i < current.len() {
            let left = &current[i];
            let right = if i + 1 < current.len() {
                &current[i + 1]
            } else {
                left
            };
            let combined = format!("{}{}", left, right);
            next.push(sha256_hex(&combined));
            i += 2;
        }
        levels.push(next);
    }

    let root = levels
        .last()
        .and_then(|l| l.first())
        .cloned()
        .unwrap_or_default();

    MerkleTree {
        algorithm: "sha256".into(),
        leaf_count: leaf_hashes.len(),
        levels,
        root,
    }
}

/// Build a Merkle proof for a leaf at a given index.
pub fn build_merkle_proof(tree: &MerkleTree, leaf_index: usize) -> Vec<ProofStep> {
    if tree.levels.is_empty() || leaf_index >= tree.levels[0].len() {
        return Vec::new();
    }

    let mut proof = Vec::new();
    let mut idx = leaf_index;

    for level in &tree.levels[..tree.levels.len().saturating_sub(1)] {
        let sibling_idx = idx ^ 1;
        let sibling_idx = if sibling_idx >= level.len() {
            idx
        } else {
            sibling_idx
        };
        let position = if sibling_idx > idx { "right" } else { "left" };
        proof.push(ProofStep {
            position: position.into(),
            hash: level[sibling_idx].clone(),
        });
        idx /= 2;
    }

    proof
}

/// Verify a Merkle proof.
pub fn verify_merkle_proof(leaf_hash: &str, proof: &[ProofStep], expected_root: &str) -> bool {
    let mut current = leaf_hash.to_string();

    for step in proof {
        current = if step.position == "left" {
            sha256_hex(&format!("{}{}", step.hash, current))
        } else {
            sha256_hex(&format!("{}{}", current, step.hash))
        };
    }

    current == expected_root
}

/// A complete Merkle tree.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct MerkleTree {
    pub algorithm: String,
    pub leaf_count: usize,
    pub levels: Vec<Vec<String>>,
    pub root: String,
}

/// A single step in a Merkle proof.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct ProofStep {
    pub position: String,
    pub hash: String,
}
