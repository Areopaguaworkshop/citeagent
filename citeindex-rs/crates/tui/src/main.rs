//! CiteIndex TUI entry point.

use anyhow::Result;
use clap::Parser;
use std::path::PathBuf;

mod app;
mod input;
mod mode;
mod panels;
mod theme;
mod ui;

/// CiteIndex — AI research knowledge infrastructure (TUI)
#[derive(Parser, Debug)]
#[command(name = "citeindex-tui", version, about)]
struct Cli {
    /// Path to config.toml
    #[arg(long)]
    config: Option<PathBuf>,

    /// Corpus root directory
    #[arg(long, default_value = "corpus")]
    corpus_root: Option<PathBuf>,

    /// Start in a specific mode
    #[arg(long, default_value = "chat")]
    mode: Option<String>,
}

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();

    // Initialize tracing to a log file (not stdout — that's the TUI)
    let log_file = std::fs::File::create("citeindex-tui.log").ok();
    if let Some(file) = log_file {
        tracing_subscriber::fmt()
            .with_writer(file)
            .with_env_filter("info")
            .init();
    }

    let config = match cli.config {
        Some(path) => citeindex_core::config::CiteIndexConfig::load(&path)?,
        None => citeindex_core::config::CiteIndexConfig::discover(),
    };

    let mut application = app::App::new(config);

    if let Some(mode_str) = cli.mode {
        application.set_mode_by_name(&mode_str);
    }

    application.run().await
}
