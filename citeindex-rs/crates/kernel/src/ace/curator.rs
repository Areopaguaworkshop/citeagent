//! PlaybookCurator — deterministic merge/prune/Merkle-commit.
//!
//! No LLM calls. Merges Reflector lessons into scholar_playbook.toml
//! using Levenshtein dedup, confidence reinforcement, and section pruning.

use chrono::Utc;

use super::playbook::{
    ApprovedSynonym, CoverageGap, PendingSynonym, PlaybookEntry, ScholarPlaybook,
};
use super::CuratorSection;
use crate::ace::reflector::Lesson;

/// Result of a curator merge operation.
#[derive(Debug, Clone)]
pub struct CuratorResult {
    pub lessons_received: usize,
    pub lessons_merged: usize,
    pub lessons_appended: usize,
    pub lessons_dropped: usize,
    pub synonyms_pending: usize,
    pub coverage_gaps_updated: usize,
    pub playbook_version: u64,
    pub merkle_hash: String,
}

/// Merge lessons into a playbook using the Curator algorithm.
pub fn merge_lessons(
    playbook: &mut ScholarPlaybook,
    lessons: &[Lesson],
    config: &CuratorSection,
) -> CuratorResult {
    let mut merged = 0;
    let mut appended = 0;
    let mut dropped = 0;
    let mut synonyms_pending = 0;
    let mut gaps_updated = 0;

    for lesson in lessons {
        match lesson.lesson_type.as_str() {
            "retrieval" => {
                let entry = PlaybookEntry {
                    description: lesson.description.clone(),
                    domain_path: lesson.domain_path.clone(),
                    confidence: lesson.confidence,
                };
                let section = &mut playbook.strategies.retrieval.helpful;
                match try_merge(section, &entry, config.similarity_threshold) {
                    MergeAction::Reinforced => merged += 1,
                    MergeAction::Appended => appended += 1,
                }
                prune_section(section, config.max_entries_per_section);
            }
            "citation" => {
                let entry = PlaybookEntry {
                    description: lesson.description.clone(),
                    domain_path: lesson.domain_path.clone(),
                    confidence: lesson.confidence,
                };
                let section = &mut playbook.strategies.citation.helpful;
                match try_merge(section, &entry, config.similarity_threshold) {
                    MergeAction::Reinforced => merged += 1,
                    MergeAction::Appended => appended += 1,
                }
                prune_section(section, config.max_entries_per_section);
            }
            "pitfall" => {
                let entry = PlaybookEntry {
                    description: lesson.description.clone(),
                    domain_path: lesson.domain_path.clone(),
                    confidence: lesson.confidence,
                };
                let section = &mut playbook.strategies.pitfall.entries;
                match try_merge(section, &entry, config.similarity_threshold) {
                    MergeAction::Reinforced => merged += 1,
                    MergeAction::Appended => appended += 1,
                }
                prune_section(section, config.max_entries_per_section);
            }
            "synonym" => {
                if lesson.confidence >= config.auto_approve_confidence {
                    // Auto-approve high-confidence synonyms
                    playbook.synonym_evolution.approved.push(ApprovedSynonym {
                        term: lesson.description.clone(),
                        expansion: vec![],
                    });
                    appended += 1;
                } else {
                    playbook
                        .synonym_evolution
                        .pending_review
                        .push(PendingSynonym {
                            term: lesson.description.clone(),
                            expansion: vec![],
                            confidence: lesson.confidence,
                        });
                    synonyms_pending += 1;
                }
            }
            "coverage_gap" => {
                // Find existing gap or create new one
                if let Some(existing) = playbook
                    .coverage_gaps
                    .detected
                    .iter_mut()
                    .find(|g| g.aspect == lesson.description)
                {
                    existing.sessions_unfilled += 1;
                    merged += 1;
                } else {
                    playbook.coverage_gaps.detected.push(CoverageGap {
                        aspect: lesson.description.clone(),
                        sessions_unfilled: 1,
                        suggested_terms: vec![],
                    });
                    appended += 1;
                }
                gaps_updated += 1;
            }
            _ => {
                dropped += 1;
            }
        }
    }

    // Update metadata
    playbook.meta.version += 1;
    playbook.meta.curator_run = Utc::now().to_rfc3339();

    let merkle_hash = playbook.merkle_hash();
    let hash_str = format!("sha256:{}", hex::encode(merkle_hash.0));

    CuratorResult {
        lessons_received: lessons.len(),
        lessons_merged: merged,
        lessons_appended: appended,
        lessons_dropped: dropped,
        synonyms_pending,
        coverage_gaps_updated: gaps_updated,
        playbook_version: playbook.meta.version,
        merkle_hash: hash_str,
    }
}

enum MergeAction {
    Reinforced,
    Appended,
}

/// Try to merge an entry into a section using Levenshtein similarity.
fn try_merge(
    section: &mut Vec<PlaybookEntry>,
    entry: &PlaybookEntry,
    similarity_threshold: f32,
) -> MergeAction {
    // Find closest existing entry by Levenshtein distance
    let mut best_idx = None;
    let mut best_similarity = 0.0f32;

    for (i, existing) in section.iter().enumerate() {
        let sim = levenshtein_similarity(&existing.description, &entry.description);
        if sim > best_similarity {
            best_similarity = sim;
            best_idx = Some(i);
        }
    }

    if best_similarity >= similarity_threshold {
        // Reinforce existing entry
        if let Some(idx) = best_idx {
            section[idx].confidence = (section[idx].confidence + entry.confidence) / 2.0;
        }
        MergeAction::Reinforced
    } else {
        // Append as new entry
        section.push(entry.clone());
        MergeAction::Appended
    }
}

/// Prune a section to max entries, keeping highest confidence.
pub fn prune_section(entries: &mut Vec<PlaybookEntry>, max: usize) {
    if entries.len() <= max {
        return;
    }
    entries.sort_by(|a, b| {
        b.confidence
            .partial_cmp(&a.confidence)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    entries.truncate(max);
}

/// Compute Levenshtein similarity as 1.0 - (distance / max_len).
fn levenshtein_similarity(a: &str, b: &str) -> f32 {
    let distance = levenshtein_distance(a, b);
    let max_len = a.len().max(b.len());
    if max_len == 0 {
        return 1.0;
    }
    1.0 - (distance as f32 / max_len as f32)
}

/// Compute Levenshtein edit distance between two strings.
fn levenshtein_distance(a: &str, b: &str) -> usize {
    let a_chars: Vec<char> = a.chars().collect();
    let b_chars: Vec<char> = b.chars().collect();
    let m = a_chars.len();
    let n = b_chars.len();

    let mut prev = (0..=n).collect::<Vec<_>>();
    let mut curr = vec![0; n + 1];

    for i in 1..=m {
        curr[0] = i;
        for j in 1..=n {
            let cost = if a_chars[i - 1] == b_chars[j - 1] {
                0
            } else {
                1
            };
            curr[j] = (prev[j] + 1).min(curr[j - 1] + 1).min(prev[j - 1] + cost);
        }
        std::mem::swap(&mut prev, &mut curr);
    }

    prev[n]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_levenshtein_distance() {
        assert_eq!(levenshtein_distance("", ""), 0);
        assert_eq!(levenshtein_distance("abc", "abc"), 0);
        assert_eq!(levenshtein_distance("abc", "abd"), 1);
        assert_eq!(levenshtein_distance("kitten", "sitting"), 3);
    }

    #[test]
    fn test_levenshtein_similarity() {
        assert_eq!(levenshtein_similarity("abc", "abc"), 1.0);
        assert!(levenshtein_similarity("abc", "abd") > 0.5);
        assert_eq!(levenshtein_similarity("", ""), 1.0);
    }

    #[test]
    fn test_prune_section() {
        let mut entries = vec![
            PlaybookEntry {
                description: "a".into(),
                domain_path: "/".into(),
                confidence: 0.5,
            },
            PlaybookEntry {
                description: "b".into(),
                domain_path: "/".into(),
                confidence: 0.9,
            },
            PlaybookEntry {
                description: "c".into(),
                domain_path: "/".into(),
                confidence: 0.3,
            },
        ];
        prune_section(&mut entries, 2);
        assert_eq!(entries.len(), 2);
        assert_eq!(entries[0].confidence, 0.9);
        assert_eq!(entries[1].confidence, 0.5);
    }

    #[test]
    fn test_merge_lessons() {
        let mut pb = ScholarPlaybook::empty("test");
        let config = CuratorSection::default();

        let lessons = vec![
            Lesson {
                lesson_type: "retrieval".into(),
                description: "Use claim_index for specific claims".into(),
                domain_path: "/cs/nlp".into(),
                confidence: 0.85,
            },
            Lesson {
                lesson_type: "coverage_gap".into(),
                description: "transformer efficiency".into(),
                domain_path: "/cs/nlp/transformers".into(),
                confidence: 0.7,
            },
        ];

        let result = merge_lessons(&mut pb, &lessons, &config);
        assert_eq!(result.lessons_received, 2);
        assert_eq!(result.lessons_appended, 2);
        assert_eq!(result.playbook_version, 1);
        assert_eq!(pb.strategies.retrieval.helpful.len(), 1);
        assert_eq!(pb.coverage_gaps.detected.len(), 1);
    }

    #[test]
    fn test_merge_reinforces_similar() {
        let mut pb = ScholarPlaybook::empty("test");
        pb.strategies.retrieval.helpful.push(PlaybookEntry {
            description: "Use claim_index for specific claims".into(),
            domain_path: "/cs/nlp".into(),
            confidence: 0.80,
        });

        let config = CuratorSection::default();
        let lessons = vec![Lesson {
            lesson_type: "retrieval".into(),
            description: "Use claim_index for specific factual claims".into(), // very similar
            domain_path: "/cs/nlp".into(),
            confidence: 0.90,
        }];

        let result = merge_lessons(&mut pb, &lessons, &config);
        assert_eq!(result.lessons_merged, 1);
        assert_eq!(pb.strategies.retrieval.helpful.len(), 1); // no new entry
        assert!(pb.strategies.retrieval.helpful[0].confidence > 0.80); // reinforced
    }
}
