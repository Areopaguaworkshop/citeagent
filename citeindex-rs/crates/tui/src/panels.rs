//! TUI panels — chat window, side panel, document tracker.
//!
//! Matches `frontend_ui_rust.yaml → layout_main`.

/// A single message in the chat window.
#[derive(Debug, Clone)]
pub struct ChatMessage {
    pub role: MessageRole,
    pub content: String,
    pub citations: Vec<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MessageRole {
    User,
    Assistant,
    System,
}

/// Chat window state — scrollable message history.
pub struct ChatWindow {
    pub messages: Vec<ChatMessage>,
    pub scroll_offset: u16,
}

impl ChatWindow {
    pub fn new() -> Self {
        Self {
            messages: vec![ChatMessage {
                role: MessageRole::System,
                content: "Welcome to CiteIndex. Type a message or / for commands.".into(),
                citations: Vec::new(),
            }],
            scroll_offset: 0,
        }
    }

    pub fn push(&mut self, msg: ChatMessage) {
        self.messages.push(msg);
        self.scroll_to_bottom();
    }

    pub fn scroll_up(&mut self, amount: u16) {
        self.scroll_offset = self.scroll_offset.saturating_add(amount);
    }

    pub fn scroll_down(&mut self, amount: u16) {
        self.scroll_offset = self.scroll_offset.saturating_sub(amount);
    }

    pub fn scroll_to_bottom(&mut self) {
        self.scroll_offset = 0;
    }

    pub fn clear(&mut self) {
        self.messages.clear();
        self.scroll_offset = 0;
    }
}

/// Side panel state — recent documents, search results, plugin shortcuts.
pub struct SidePanel {
    pub collapsed: bool,
    pub width_pct: u16,
    pub recent_documents: Vec<SidePanelItem>,
    pub search_results: Vec<SidePanelItem>,
    pub plugin_shortcuts: Vec<SidePanelItem>,
    pub active_section: SidePanelSection,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SidePanelSection {
    RecentDocuments,
    SearchResults,
    PluginShortcuts,
}

#[derive(Debug, Clone)]
pub struct SidePanelItem {
    pub label: String,
    pub detail: String,
}

impl SidePanel {
    pub fn new(collapsed: bool, width_pct: u16) -> Self {
        Self {
            collapsed,
            width_pct,
            recent_documents: Vec::new(),
            search_results: Vec::new(),
            plugin_shortcuts: Vec::new(),
            active_section: SidePanelSection::RecentDocuments,
        }
    }

    pub fn toggle(&mut self) {
        self.collapsed = !self.collapsed;
    }

    pub fn add_recent_document(&mut self, label: String, detail: String) {
        self.recent_documents.push(SidePanelItem { label, detail });
        // Keep last 20
        if self.recent_documents.len() > 20 {
            self.recent_documents.remove(0);
        }
    }

    pub fn set_search_results(&mut self, results: Vec<SidePanelItem>) {
        self.search_results = results;
    }
}

/// Input bar state.
pub struct InputBar {
    pub content: String,
    pub cursor_pos: usize,
    pub history: Vec<String>,
    pub history_index: Option<usize>,
}

impl InputBar {
    pub fn new() -> Self {
        Self {
            content: String::new(),
            cursor_pos: 0,
            history: Vec::new(),
            history_index: None,
        }
    }

    pub fn insert(&mut self, ch: char) {
        self.content.insert(self.cursor_pos, ch);
        self.cursor_pos += ch.len_utf8();
    }

    pub fn backspace(&mut self) {
        if self.cursor_pos > 0 {
            let prev = self.content[..self.cursor_pos]
                .chars()
                .last()
                .map_or(0, |c| c.len_utf8());
            self.cursor_pos -= prev;
            self.content.remove(self.cursor_pos);
        }
    }

    pub fn delete(&mut self) {
        if self.cursor_pos < self.content.len() {
            self.content.remove(self.cursor_pos);
        }
    }

    pub fn move_left(&mut self) {
        if self.cursor_pos > 0 {
            let prev = self.content[..self.cursor_pos]
                .chars()
                .last()
                .map_or(0, |c| c.len_utf8());
            self.cursor_pos -= prev;
        }
    }

    pub fn move_right(&mut self) {
        if self.cursor_pos < self.content.len() {
            let next = self.content[self.cursor_pos..]
                .chars()
                .next()
                .map_or(0, |c| c.len_utf8());
            self.cursor_pos += next;
        }
    }

    pub fn home(&mut self) {
        self.cursor_pos = 0;
    }

    pub fn end(&mut self) {
        self.cursor_pos = self.content.len();
    }

    pub fn take_content(&mut self) -> String {
        let content = self.content.clone();
        if !content.trim().is_empty() {
            self.history.push(content.clone());
        }
        self.content.clear();
        self.cursor_pos = 0;
        self.history_index = None;
        content
    }

    pub fn history_prev(&mut self) {
        if self.history.is_empty() {
            return;
        }
        let idx = match self.history_index {
            Some(i) if i > 0 => i - 1,
            Some(_) => return,
            None => self.history.len() - 1,
        };
        self.history_index = Some(idx);
        self.content = self.history[idx].clone();
        self.cursor_pos = self.content.len();
    }

    pub fn history_next(&mut self) {
        if let Some(idx) = self.history_index {
            if idx + 1 < self.history.len() {
                self.history_index = Some(idx + 1);
                self.content = self.history[idx + 1].clone();
                self.cursor_pos = self.content.len();
            } else {
                self.history_index = None;
                self.content.clear();
                self.cursor_pos = 0;
            }
        }
    }
}

/// A single search result displayed in the popup.
#[derive(Debug, Clone)]
pub struct SearchResultEntry {
    pub title: String,
    pub author: String,
    pub text: String,
    pub formatted_citation: String,
    pub score: f64,
    pub node_id: String,
}

/// A past search query for history.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct SearchHistoryEntry {
    pub timestamp: String,
    pub query: String,
    pub result_count: usize,
}

/// Popup state for browsing search results.
pub struct SearchResultsPopup {
    pub visible: bool,
    pub results: Vec<SearchResultEntry>,
    pub selected: usize,
    pub expanded: bool,
    pub scroll_offset: u16,
    pub history: Vec<SearchHistoryEntry>,
    history_path: Option<std::path::PathBuf>,
}

impl SearchResultsPopup {
    pub fn new(history_dir: Option<&std::path::Path>) -> Self {
        let history_path = history_dir.map(|d| d.join("search_history.jsonl"));
        let history = history_path
            .as_ref()
            .map(|p| Self::load_history(p))
            .unwrap_or_default();
        Self {
            visible: false,
            results: Vec::new(),
            selected: 0,
            expanded: false,
            scroll_offset: 0,
            history,
            history_path,
        }
    }

    pub fn open(&mut self, results: Vec<SearchResultEntry>, query: &str) {
        let entry = SearchHistoryEntry {
            timestamp: chrono::Utc::now()
                .format("%Y-%m-%dT%H:%M:%S+00:00")
                .to_string(),
            query: query.to_string(),
            result_count: results.len(),
        };
        self.history.push(entry.clone());
        self.save_history_entry(&entry);

        self.results = results;
        self.selected = 0;
        self.expanded = false;
        self.scroll_offset = 0;
        self.visible = true;
    }

    pub fn close(&mut self) {
        self.visible = false;
        self.expanded = false;
        self.scroll_offset = 0;
    }

    pub fn toggle_expand(&mut self) {
        self.expanded = !self.expanded;
        self.scroll_offset = 0;
    }

    pub fn next(&mut self) {
        if !self.expanded && !self.results.is_empty() {
            self.selected = (self.selected + 1) % self.results.len();
        }
    }

    pub fn prev(&mut self) {
        if !self.expanded && !self.results.is_empty() {
            self.selected = self
                .selected
                .checked_sub(1)
                .unwrap_or(self.results.len() - 1);
        }
    }

    pub fn scroll_up(&mut self, amount: u16) {
        if self.expanded {
            self.scroll_offset = self.scroll_offset.saturating_add(amount);
        }
    }

    pub fn scroll_down(&mut self, amount: u16) {
        if self.expanded {
            self.scroll_offset = self.scroll_offset.saturating_sub(amount);
        }
    }

    pub fn selected_result(&self) -> Option<&SearchResultEntry> {
        self.results.get(self.selected)
    }

    fn save_history_entry(&self, entry: &SearchHistoryEntry) {
        if let Some(ref path) = self.history_path {
            if let Some(parent) = path.parent() {
                std::fs::create_dir_all(parent).ok();
            }
            if let Ok(mut file) = std::fs::OpenOptions::new()
                .create(true)
                .append(true)
                .open(path)
            {
                if let Ok(line) = serde_json::to_string(entry) {
                    use std::io::Write;
                    let _ = writeln!(file, "{}", line);
                }
            }
        }
    }

    fn load_history(path: &std::path::Path) -> Vec<SearchHistoryEntry> {
        if !path.exists() {
            return Vec::new();
        }
        let file = match std::fs::File::open(path) {
            Ok(f) => f,
            Err(_) => return Vec::new(),
        };
        use std::io::BufRead;
        std::io::BufReader::new(file)
            .lines()
            .filter_map(|l| l.ok())
            .filter(|l| !l.trim().is_empty())
            .filter_map(|l| serde_json::from_str::<SearchHistoryEntry>(&l).ok())
            .collect()
    }
}

/// Playbook panel — displays ACE strategies and adaptation history.
pub struct PlaybookPanel {
    pub strategies: Vec<PlaybookEntry>,
    pub selected: usize,
    pub scroll_offset: u16,
}

/// A single playbook strategy entry.
#[derive(Debug, Clone)]
pub struct PlaybookEntry {
    pub category: String,
    pub key: String,
    pub value: String,
    pub confidence: f32,
    pub source_session: Option<String>,
}

impl PlaybookPanel {
    pub fn new() -> Self {
        Self {
            strategies: Vec::new(),
            selected: 0,
            scroll_offset: 0,
        }
    }

    pub fn set_strategies(&mut self, strategies: Vec<PlaybookEntry>) {
        self.strategies = strategies;
        self.selected = 0;
        self.scroll_offset = 0;
    }

    pub fn next(&mut self) {
        if !self.strategies.is_empty() {
            self.selected = (self.selected + 1) % self.strategies.len();
        }
    }

    pub fn prev(&mut self) {
        if !self.strategies.is_empty() {
            self.selected = self
                .selected
                .checked_sub(1)
                .unwrap_or(self.strategies.len() - 1);
        }
    }

    pub fn scroll_up(&mut self, amount: u16) {
        self.scroll_offset = self.scroll_offset.saturating_add(amount);
    }

    pub fn scroll_down(&mut self, amount: u16) {
        self.scroll_offset = self.scroll_offset.saturating_sub(amount);
    }

    pub fn selected_entry(&self) -> Option<&PlaybookEntry> {
        self.strategies.get(self.selected)
    }
}

/// Structure panel — displays argument flow outlines.
pub struct StructurePanel {
    pub outline: Vec<StructureNode>,
    pub selected: usize,
    pub expanded_nodes: std::collections::HashSet<usize>,
    pub scroll_offset: u16,
}

/// A node in the argument structure outline.
#[derive(Debug, Clone)]
pub struct StructureNode {
    pub depth: usize,
    pub heading: String,
    pub node_type: StructureNodeType,
    pub claim_count: usize,
    pub coverage_score: Option<f32>,
    pub has_contradictions: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StructureNodeType {
    Section,
    Claim,
    Evidence,
    Contradiction,
    Gap,
}

impl StructurePanel {
    pub fn new() -> Self {
        Self {
            outline: Vec::new(),
            selected: 0,
            expanded_nodes: std::collections::HashSet::new(),
            scroll_offset: 0,
        }
    }

    pub fn set_outline(&mut self, outline: Vec<StructureNode>) {
        self.outline = outline;
        self.selected = 0;
        self.expanded_nodes.clear();
        self.scroll_offset = 0;
    }

    pub fn next(&mut self) {
        if !self.outline.is_empty() {
            self.selected = (self.selected + 1) % self.outline.len();
        }
    }

    pub fn prev(&mut self) {
        if !self.outline.is_empty() {
            self.selected = self
                .selected
                .checked_sub(1)
                .unwrap_or(self.outline.len() - 1);
        }
    }

    pub fn toggle_expand(&mut self) {
        if self.expanded_nodes.contains(&self.selected) {
            self.expanded_nodes.remove(&self.selected);
        } else {
            self.expanded_nodes.insert(self.selected);
        }
    }

    pub fn scroll_up(&mut self, amount: u16) {
        self.scroll_offset = self.scroll_offset.saturating_add(amount);
    }

    pub fn scroll_down(&mut self, amount: u16) {
        self.scroll_offset = self.scroll_offset.saturating_sub(amount);
    }

    pub fn selected_node(&self) -> Option<&StructureNode> {
        self.outline.get(self.selected)
    }
}
