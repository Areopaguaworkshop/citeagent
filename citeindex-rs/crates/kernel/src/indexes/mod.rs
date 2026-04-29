//! Tantivy index schema builders for the CiteIndex v12 kernel (Phase 2).
//!
//! Implements the S4_tantivy_index_schemas contract:
//! - Document index (papers, references)
//! - Memory index (session memories)
//! - Claim index (extracted claims)
//!
//! Multi-language tokenizers are registered per index. Currently only English,
//! French, German, and Russian have real stemmers; Chinese and Japanese use
//! placeholder (English) tokenizers until jieba/lindera integration.

use std::path::Path;

use anyhow::{Context, Result};
use tantivy::schema::{
    DateOptions, FacetOptions, IndexRecordOption, NumericOptions, Schema, SchemaBuilder,
    TextFieldIndexing, TextOptions,
};
use tantivy::tokenizer::{
    Language, LowerCaser, RemoveLongFilter, SimpleTokenizer, Stemmer, TextAnalyzer,
};

/// Supported languages and their corresponding tokenizer names.
const SUPPORTED_LANGS: &[(&str, &str)] = &[
    ("en", "citeindex_en"),
    ("zh", "citeindex_zh"),
    ("ja", "citeindex_ja"),
    ("fr", "citeindex_fr"),
    ("de", "citeindex_de"),
    ("ru", "citeindex_ru"),
];

/// Register all CiteIndex tokenizers on the given index.
///
/// - `citeindex_en`: SimpleTokenizer + RemoveLongFilter(40) + LowerCaser + Stemmer(English)
/// - `citeindex_zh`, `citeindex_ja`: Placeholder stubs (clone of English tokenizer)
/// - `citeindex_fr`, `citeindex_de`, `citeindex_ru`: SimpleTokenizer + LowerCaser + Stemmer
pub fn register_tokenizers(index: &tantivy::Index) {
    let en = TextAnalyzer::builder(SimpleTokenizer::default())
        .filter(RemoveLongFilter::limit(40))
        .filter(LowerCaser)
        .filter(Stemmer::new(Language::English))
        .build();
    index.tokenizers().register("citeindex_en", en);

    // zh/ja: placeholder stubs using English tokenizer
    tracing::info!(
        "Registering placeholder tokenizers for zh/ja (English-based); \
         jieba/lindera not yet integrated"
    );
    for name in &["citeindex_zh", "citeindex_ja"] {
        let stub = TextAnalyzer::builder(SimpleTokenizer::default())
            .filter(RemoveLongFilter::limit(40))
            .filter(LowerCaser)
            .filter(Stemmer::new(Language::English))
            .build();
        index.tokenizers().register(name, stub);
    }

    // fr
    let fr = TextAnalyzer::builder(SimpleTokenizer::default())
        .filter(LowerCaser)
        .filter(Stemmer::new(Language::French))
        .build();
    index.tokenizers().register("citeindex_fr", fr);

    // de
    let de = TextAnalyzer::builder(SimpleTokenizer::default())
        .filter(LowerCaser)
        .filter(Stemmer::new(Language::German))
        .build();
    index.tokenizers().register("citeindex_de", de);

    // ru
    let ru = TextAnalyzer::builder(SimpleTokenizer::default())
        .filter(LowerCaser)
        .filter(Stemmer::new(Language::Russian))
        .build();
    index.tokenizers().register("citeindex_ru", ru);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// TEXT field that is stored only (not indexed).
fn text_stored_only() -> TextOptions {
    TextOptions::default().set_stored()
}

/// TEXT field stored + indexed with `"raw"` tokenizer.
fn text_stored_raw_indexed() -> TextOptions {
    TextOptions::default().set_stored().set_indexing_options(
        TextFieldIndexing::default()
            .set_tokenizer("raw")
            .set_index_option(IndexRecordOption::Basic),
    )
}

/// TEXT field stored + fast + indexed with `"raw"` tokenizer.
///
/// `set_fast` on TextOptions may not be available in tantivy 0.22; if so the
/// fast attribute is silently omitted (the contract treats it as optional
/// optimisation).
fn text_stored_fast_raw_indexed() -> TextOptions {
    TextOptions::default()
        .set_stored()
        .set_fast(None)
        .set_indexing_options(
            TextFieldIndexing::default()
                .set_tokenizer("raw")
                .set_index_option(IndexRecordOption::Basic),
        )
}

/// TEXT field indexed with a language-specific tokenizer (not stored).
fn text_lang_indexed(tokenizer: &str) -> TextOptions {
    TextOptions::default().set_indexing_options(
        TextFieldIndexing::default()
            .set_tokenizer(tokenizer)
            .set_index_option(IndexRecordOption::WithFreqsAndPositions),
    )
}

/// TEXT field stored + indexed with a given tokenizer.
fn text_stored_indexed(tokenizer: &str) -> TextOptions {
    TextOptions::default().set_stored().set_indexing_options(
        TextFieldIndexing::default()
            .set_tokenizer(tokenizer)
            .set_index_option(IndexRecordOption::WithFreqsAndPositions),
    )
}

/// i64 field: stored + indexed + fast.
fn i64_stored_fast_indexed() -> NumericOptions {
    NumericOptions::default()
        .set_stored()
        .set_indexed()
        .set_fast()
}

/// DATE field: stored + indexed + fast.
fn date_stored_fast_indexed() -> DateOptions {
    DateOptions::default().set_stored().set_indexed().set_fast()
}

// ---------------------------------------------------------------------------
// Schema builders
// ---------------------------------------------------------------------------

/// Add per-language text fields (e.g. `title_en`, `title_zh`, …) to a schema.
fn add_lang_fields(builder: &mut SchemaBuilder, prefix: &str) {
    for &(lang, tokenizer) in SUPPORTED_LANGS {
        let name = format!("{prefix}_{lang}");
        builder.add_text_field(&name, text_lang_indexed(tokenizer));
    }
}

/// Build the **document** index schema per S4 contract.
pub fn build_document_index_schema() -> Schema {
    let mut builder = Schema::builder();

    // Primary key
    builder.add_text_field("doc_id", text_stored_raw_indexed());

    // Title
    builder.add_text_field("title", text_stored_only());
    add_lang_fields(&mut builder, "title");

    // Authors
    builder.add_text_field("authors", text_stored_only());
    builder.add_text_field("authors_en", text_lang_indexed("citeindex_en"));

    // Year
    builder.add_i64_field("year", i64_stored_fast_indexed());

    // DOI
    builder.add_text_field("doi", text_stored_raw_indexed());

    // Abstract
    builder.add_text_field("abstract_text", text_stored_only());
    add_lang_fields(&mut builder, "abstract_text");

    // Venue / doc_type
    builder.add_text_field("venue", text_stored_raw_indexed());
    builder.add_text_field("doc_type", text_stored_raw_indexed());

    // Hierarchy / project
    builder.add_facet_field("hierarchy_path", FacetOptions::default());

    // Quality tier
    builder.add_text_field("quality_tier", text_stored_fast_raw_indexed());

    // Keywords
    builder.add_text_field("keywords", text_stored_indexed("citeindex_en"));

    // Merkle
    builder.add_text_field("merkle_hash", text_stored_only());

    // Project
    builder.add_facet_field("project_id", FacetOptions::default());

    // Timestamps / metadata
    builder.add_date_field("indexed_at", date_stored_fast_indexed());
    builder.add_text_field("language", text_stored_fast_raw_indexed());

    builder.build()
}

/// Build the **memory** index schema per S4 contract.
pub fn build_memory_index_schema() -> Schema {
    let mut builder = Schema::builder();

    builder.add_text_field("memory_id", text_stored_raw_indexed());
    builder.add_text_field("session_id", text_stored_raw_indexed());

    builder.add_text_field("title", text_stored_only());
    add_lang_fields(&mut builder, "title");

    builder.add_text_field("description", text_stored_only());
    add_lang_fields(&mut builder, "description");

    builder.add_text_field("content", text_stored_only());
    add_lang_fields(&mut builder, "content");

    builder.add_facet_field("hierarchy_path", FacetOptions::default());
    builder.add_facet_field("project_id", FacetOptions::default());

    builder.add_date_field("created_at", date_stored_fast_indexed());
    builder.add_text_field("merkle_hash", text_stored_only());

    builder.build()
}

/// Build the **claim** index schema per S4 contract.
pub fn build_claim_index_schema() -> Schema {
    let mut builder = Schema::builder();

    builder.add_text_field("claim_id", text_stored_raw_indexed());
    builder.add_text_field("doc_id", text_stored_raw_indexed());
    builder.add_text_field("section_ref", text_stored_raw_indexed());

    builder.add_text_field("claim_text", text_stored_only());
    add_lang_fields(&mut builder, "claim_text");

    builder.add_text_field("polarity_tag", text_stored_fast_raw_indexed());

    // entities — multi-value TEXT stored + indexed with "raw"
    builder.add_text_field("entities", text_stored_raw_indexed());

    builder.add_facet_field("hierarchy_path", FacetOptions::default());
    builder.add_text_field("quality_tier", text_stored_fast_raw_indexed());

    // verified — represented as i64 (0 or 1) since tantivy has no native bool
    builder.add_i64_field("verified", i64_stored_fast_indexed());

    builder.add_text_field("merkle_hash", text_stored_only());
    builder.add_date_field("created_at", date_stored_fast_indexed());

    builder.build()
}

// ---------------------------------------------------------------------------
// Index lifecycle
// ---------------------------------------------------------------------------

/// Open an existing tantivy index or create a new one at `path`.
///
/// After opening/creating, all CiteIndex tokenizers are registered on the
/// index so that queries and indexing can use the language-specific analyzers.
pub fn open_or_create_index(path: &Path, schema: Schema) -> Result<tantivy::Index> {
    let index = if path.join("meta.json").exists() {
        tantivy::Index::open_in_dir(path)
            .with_context(|| format!("failed to open existing index at {}", path.display()))?
    } else {
        std::fs::create_dir_all(path)
            .with_context(|| format!("failed to create index directory {}", path.display()))?;
        tantivy::Index::create_in_dir(path, schema)
            .with_context(|| format!("failed to create index at {}", path.display()))?
    };

    register_tokenizers(&index);
    Ok(index)
}
