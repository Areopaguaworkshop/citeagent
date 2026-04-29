//! Mode manager — Chat, Ingest, Search, Plugin, Refs, Project, Playbook, Structure.
//!
//! Matches `frontend_ui_rust.yaml → mode_manager`.

/// Operational modes for the TUI.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Mode {
    Chat,
    Ingest,
    Search,
    PageIndex,
    Plugin,
    Refs,
    Project,
    Playbook,
    Structure,
}

impl Mode {
    /// All available modes.
    pub const ALL: &'static [Mode] = &[
        Mode::Chat,
        Mode::Ingest,
        Mode::Search,
        Mode::PageIndex,
        Mode::Plugin,
        Mode::Refs,
        Mode::Project,
        Mode::Playbook,
        Mode::Structure,
    ];

    /// Parse a mode from a slash command or name.
    pub fn from_command(input: &str) -> Option<Mode> {
        let normalized = input.trim_start_matches('/').to_lowercase();
        match normalized.as_str() {
            "chat" => Some(Mode::Chat),
            "ingest" => Some(Mode::Ingest),
            "search" => Some(Mode::Search),
            "pageindex" | "pi" => Some(Mode::PageIndex),
            "plugin" | "plugins" => Some(Mode::Plugin),
            "refs" | "references" => Some(Mode::Refs),
            "proj" | "project" => Some(Mode::Project),
            "playbook" => Some(Mode::Playbook),
            "structure" | "outline" => Some(Mode::Structure),
            _ => None,
        }
    }

    /// Slash command trigger for this mode.
    pub fn command(&self) -> &'static str {
        match self {
            Mode::Chat => "/chat",
            Mode::Ingest => "/ingest",
            Mode::Search => "/search",
            Mode::PageIndex => "/pageindex",
            Mode::Plugin => "/plugin",
            Mode::Refs => "/refs",
            Mode::Project => "/proj",
            Mode::Playbook => "/playbook",
            Mode::Structure => "/structure",
        }
    }

    /// Display name.
    pub fn label(&self) -> &'static str {
        match self {
            Mode::Chat => "Chat",
            Mode::Ingest => "Ingest",
            Mode::Search => "Search",
            Mode::PageIndex => "PageIndex",
            Mode::Plugin => "Plugin",
            Mode::Refs => "Refs",
            Mode::Project => "Project",
            Mode::Playbook => "Playbook",
            Mode::Structure => "Structure",
        }
    }

    /// Short description.
    pub fn description(&self) -> &'static str {
        match self {
            Mode::Chat => "AI chat assistant mode",
            Mode::Ingest => "Ingest PDFs, media, or CSL JSON documents",
            Mode::Search => "Search indexed documents or references",
            Mode::PageIndex => "Reasoning-based search over document tree structures",
            Mode::Plugin => "Invoke internal/external plugin tools",
            Mode::Refs => "Reference manager",
            Mode::Project => "Project explorer",
            Mode::Playbook => "ACE scholar playbook strategies",
            Mode::Structure => "Argument flow outline viewer",
        }
    }

    /// Fuzzy-match available modes for autocomplete.
    pub fn fuzzy_match(query: &str) -> Vec<Mode> {
        use fuzzy_matcher::skim::SkimMatcherV2;
        use fuzzy_matcher::FuzzyMatcher;

        let matcher = SkimMatcherV2::default();
        let query = query.trim_start_matches('/').to_lowercase();

        let mut scored: Vec<(i64, Mode)> = Mode::ALL
            .iter()
            .filter_map(|m| {
                let label = m.label().to_lowercase();
                let cmd = m.command().trim_start_matches('/');
                let score_label = matcher.fuzzy_match(&label, &query);
                let score_cmd = matcher.fuzzy_match(cmd, &query);
                let best = score_label.max(score_cmd);
                best.map(|s| (s, *m))
            })
            .collect();

        scored.sort_by(|a, b| b.0.cmp(&a.0));
        scored.into_iter().map(|(_, m)| m).collect()
    }
}
