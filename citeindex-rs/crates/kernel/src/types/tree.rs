//! S1 — PageIndex JSON Tree types
//!
//! Per-document structured representation for tantivy ingest,
//! `/deep` traversal, citation rendering, and claim extraction.

use serde::{Deserialize, Serialize};

/// Top-level PageIndex JSON Tree structure.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PageIndexTree {
    pub citeindex_version: String,
    pub tree_version: String,
    pub level_0: Level0,
    #[serde(default)]
    pub level_1: Vec<SectionNode>,
}

/// Level 0 — Citation Root (CSL-JSON metadata + CiteIndex extensions).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Level0 {
    pub id: serde_json::Value,
    #[serde(rename = "type")]
    pub csl_type: String,
    pub title: String,
    #[serde(default)]
    pub author: Vec<CslNameVar>,
    #[serde(default)]
    pub editor: Vec<CslNameVar>,
    pub issued: Option<CslDateVar>,
    #[serde(rename = "DOI")]
    pub doi: Option<String>,
    #[serde(rename = "ISBN")]
    pub isbn: Option<String>,
    #[serde(rename = "URL")]
    pub url: Option<String>,
    #[serde(rename = "container-title")]
    pub container_title: Option<String>,
    pub volume: Option<serde_json::Value>,
    pub issue: Option<serde_json::Value>,
    pub page: Option<serde_json::Value>,
    pub publisher: Option<String>,
    #[serde(rename = "publisher-place")]
    pub publisher_place: Option<String>,
    #[serde(rename = "abstract")]
    pub abstract_text: Option<String>,
    pub language: Option<String>,
    pub keyword: Option<String>,

    // CiteIndex extensions (ci_ prefix)
    #[serde(default)]
    pub ci_doc_id: Option<String>,
    #[serde(default)]
    pub ci_quality_tier: Option<String>,
    #[serde(default)]
    pub ci_hierarchy_path: Option<String>,
    #[serde(default)]
    pub ci_merkle_hash: Option<String>,
    #[serde(default)]
    pub ci_source_type: Option<String>,
    #[serde(default)]
    pub ci_ingested_at: Option<String>,
    #[serde(default)]
    pub ci_structure_confidence: Option<f64>,
    #[serde(default)]
    pub ci_indexed_at: Option<String>,
    #[serde(default)]
    pub ci_project_ids: Vec<String>,
    #[serde(default)]
    pub ci_claim_anchors: Vec<ClaimAnchor>,

    /// Additional CSL-JSON fields not explicitly modeled.
    #[serde(flatten)]
    pub extra: serde_json::Map<String, serde_json::Value>,
}

/// CSL name variable (author, editor, etc.).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CslNameVar {
    pub family: Option<String>,
    pub given: Option<String>,
    pub literal: Option<String>,
}

/// CSL date variable.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CslDateVar {
    #[serde(rename = "date-parts")]
    pub date_parts: Option<Vec<Vec<i64>>>,
    pub raw: Option<String>,
}

/// Claim anchor linking a verified claim to this document.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClaimAnchor {
    pub claim_id: String,
    pub section_ref: String,
    pub verbatim_passage: String,
}

/// Level 1 — Major Section.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SectionNode {
    pub node_id: String,
    pub heading: Option<String>,
    #[serde(default)]
    pub section_number: Option<String>,
    #[serde(default)]
    pub section_type: Option<String>,
    #[serde(default)]
    pub page_range: Option<String>,
    #[serde(default)]
    pub children: Vec<SubsectionNode>,
}

/// Level 2 — Subsection.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SubsectionNode {
    pub node_id: String,
    pub heading: Option<String>,
    #[serde(default)]
    pub section_number: Option<String>,
    #[serde(default)]
    pub children: Vec<LocatorNode>,
}

/// Level 3 — Locator (page, paragraph, or timestamp).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LocatorNode {
    pub node_id: String,
    #[serde(default)]
    pub locator_type: Option<String>,

    // PDF locator fields
    pub page_number: Option<i64>,
    pub page_label: Option<String>,
    #[serde(default)]
    pub text_blocks: Vec<TextBlock>,
    #[serde(default)]
    pub figures: Vec<Figure>,
    #[serde(default)]
    pub tables: Vec<Table>,

    // URL/paragraph locator fields
    pub paragraph_number: Option<i64>,
    pub paragraph_id: Option<String>,
    pub text: Option<String>,

    // Media/timestamp locator fields
    pub start_time: Option<String>,
    pub end_time: Option<String>,
    pub speaker: Option<String>,
    pub transcript_text: Option<String>,

    // Level 4 children (lines)
    #[serde(default)]
    pub children: Vec<LineNode>,
}

/// Text block within a page.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TextBlock {
    pub block_id: String,
    pub text: String,
    #[serde(default)]
    pub block_type: Option<String>,
    #[serde(default)]
    pub bbox: Option<Vec<f64>>,
}

/// Figure reference.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Figure {
    pub figure_id: String,
    #[serde(default)]
    pub figure_number: Option<String>,
    #[serde(default)]
    pub caption: Option<String>,
    #[serde(default)]
    pub image_path: Option<String>,
    pub page_number: Option<i64>,
    #[serde(default)]
    pub bbox: Option<Vec<f64>>,
}

/// Table reference.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Table {
    pub table_id: String,
    #[serde(default)]
    pub table_number: Option<String>,
    #[serde(default)]
    pub caption: Option<String>,
    #[serde(default)]
    pub content: Option<String>,
    #[serde(default)]
    pub image_path: Option<String>,
    pub page_number: Option<i64>,
    #[serde(default)]
    pub bbox: Option<Vec<f64>>,
}

/// Level 4 — Line (primary source granularity).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LineNode {
    pub node_id: String,
    pub line_number: i64,
    pub text: String,
    #[serde(default)]
    pub line_type: Option<String>,
}

impl PageIndexTree {
    /// Load a PageIndex tree from a JSON file on disk.
    pub fn load(path: &std::path::Path) -> anyhow::Result<Self> {
        let content = std::fs::read_to_string(path)?;
        let tree: Self = serde_json::from_str(&content)?;
        Ok(tree)
    }

    /// Get all text content from the tree (for regex search, etc.).
    pub fn all_text(&self) -> Vec<(String, String)> {
        let mut result = Vec::new();
        for section in &self.level_1 {
            for subsection in &section.children {
                for locator in &subsection.children {
                    let node_id = locator.node_id.clone();
                    // Collect text from all sources in this locator
                    for block in &locator.text_blocks {
                        result.push((node_id.clone(), block.text.clone()));
                    }
                    if let Some(ref text) = locator.text {
                        result.push((node_id.clone(), text.clone()));
                    }
                    if let Some(ref text) = locator.transcript_text {
                        result.push((node_id.clone(), text.clone()));
                    }
                }
            }
        }
        result
    }

    /// Find a node by its node_id, searching all levels.
    pub fn find_node(&self, target_id: &str) -> Option<FoundNode> {
        for section in &self.level_1 {
            if section.node_id == target_id {
                return Some(FoundNode::Section(section.clone()));
            }
            for subsection in &section.children {
                if subsection.node_id == target_id {
                    return Some(FoundNode::Subsection(subsection.clone()));
                }
                for locator in &subsection.children {
                    if locator.node_id == target_id {
                        return Some(FoundNode::Locator(locator.clone()));
                    }
                    for line in &locator.children {
                        if line.node_id == target_id {
                            return Some(FoundNode::Line(line.clone()));
                        }
                    }
                }
            }
        }
        None
    }

    /// Get the publication year from Level 0 issued date.
    pub fn year(&self) -> Option<i64> {
        self.level_0
            .issued
            .as_ref()
            .and_then(|d| d.date_parts.as_ref())
            .and_then(|parts| parts.first())
            .and_then(|year_parts| year_parts.first())
            .copied()
    }

    /// Get authors as a display string.
    pub fn authors_display(&self) -> String {
        self.level_0
            .author
            .iter()
            .map(|a| {
                if let Some(ref lit) = a.literal {
                    lit.clone()
                } else {
                    let family = a.family.as_deref().unwrap_or("");
                    let given = a.given.as_deref().unwrap_or("");
                    if given.is_empty() {
                        family.to_string()
                    } else {
                        format!("{family}, {given}")
                    }
                }
            })
            .collect::<Vec<_>>()
            .join("; ")
    }
}

/// Result of find_node() — which level the node was found at.
#[derive(Debug, Clone)]
pub enum FoundNode {
    Section(SectionNode),
    Subsection(SubsectionNode),
    Locator(LocatorNode),
    Line(LineNode),
}
