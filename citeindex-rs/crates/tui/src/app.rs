//! Main TUI application — event loop, state management, runtime dispatch.

use crate::input::{self, AutocompleteState, ParsedInput};
use crate::mode::Mode;
use crate::panels::{
    ChatMessage, ChatWindow, InputBar, MessageRole, PlaybookPanel, SearchResultEntry,
    SearchResultsPopup, SidePanel, SidePanelItem, StructurePanel,
};
use crate::theme::{Theme, ThemeMode};
use crate::ui;

use citeindex_core::config::CiteIndexConfig;
use citeindex_core::engine::Engine;
use citeindex_plugins::manager::PluginManager;

use anyhow::Result;
use crossterm::event::{self, Event, KeyCode, KeyEvent, KeyModifiers};
use crossterm::terminal::{
    disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen,
};
use crossterm::ExecutableCommand;
use ratatui::backend::CrosstermBackend;
use ratatui::Terminal;
use std::io::stdout;
use std::time::Duration;

/// Top-level application state.
pub struct App {
    pub config: CiteIndexConfig,
    pub engine: Engine,
    pub plugin_manager: PluginManager,
    pub mode: Mode,
    pub theme: Theme,
    pub chat_window: ChatWindow,
    pub input_bar: InputBar,
    pub side_panel: SidePanel,
    pub autocomplete: AutocompleteState,
    pub search_popup: SearchResultsPopup,
    pub playbook_panel: PlaybookPanel,
    pub structure_panel: StructurePanel,
    pub running: bool,
    pub busy: bool,
    thread_id: String,
}

impl App {
    pub fn new(config: CiteIndexConfig) -> Self {
        let theme_mode = if config.tui.theme == "light" {
            ThemeMode::Light
        } else {
            ThemeMode::Dark
        };
        let theme = Theme::from_mode(theme_mode);

        let engine = Engine::new(config.clone());

        let plugins_dir = config.plugins.directory.clone();
        let mut plugin_manager = PluginManager::new(&plugins_dir);
        plugin_manager.discover();

        let side_panel = SidePanel::new(
            config.tui.side_panel_collapsed,
            config.tui.side_panel_width_pct,
        );

        let history_dir = config.corpus_root.join(".search_history");
        let search_popup = SearchResultsPopup::new(Some(&history_dir));

        Self {
            config,
            engine,
            plugin_manager,
            mode: Mode::Chat,
            theme,
            chat_window: ChatWindow::new(),
            input_bar: InputBar::new(),
            side_panel,
            autocomplete: AutocompleteState::new(),
            search_popup,
            playbook_panel: PlaybookPanel::new(),
            structure_panel: StructurePanel::new(),
            running: true,
            busy: false,
            thread_id: "default".into(),
        }
    }

    /// Set mode by name string.
    pub fn set_mode_by_name(&mut self, name: &str) {
        if let Some(mode) = Mode::from_command(name) {
            self.mode = mode;
        }
    }

    /// Main event loop.
    pub async fn run(&mut self) -> Result<()> {
        enable_raw_mode()?;
        stdout().execute(EnterAlternateScreen)?;

        let backend = CrosstermBackend::new(stdout());
        let mut terminal = Terminal::new(backend)?;
        terminal.clear()?;

        while self.running {
            terminal.draw(|f| ui::draw(f, self))?;

            // Poll for events
            if event::poll(Duration::from_millis(50))? {
                if let Event::Key(key) = event::read()? {
                    self.handle_key(key).await;
                }
            }
        }

        if let Err(e) = self.engine.shutdown().await {
            tracing::warn!("Failed to shut down engine agents cleanly: {}", e);
        }

        disable_raw_mode()?;
        stdout().execute(LeaveAlternateScreen)?;
        Ok(())
    }

    async fn handle_key(&mut self, key: KeyEvent) {
        // Global shortcuts
        match (key.modifiers, key.code) {
            (KeyModifiers::CONTROL, KeyCode::Char('c')) => {
                self.running = false;
                return;
            }
            (KeyModifiers::CONTROL, KeyCode::Char('t')) => {
                self.theme = Theme::from_mode(self.theme.mode.toggle());
                return;
            }
            (KeyModifiers::CONTROL, KeyCode::Char('b')) => {
                self.side_panel.toggle();
                return;
            }
            _ => {}
        }

        // Search popup navigation (takes priority)
        if self.search_popup.visible {
            match key.code {
                KeyCode::Up => {
                    if self.search_popup.expanded {
                        self.search_popup.scroll_up(1);
                    } else {
                        self.search_popup.prev();
                    }
                    return;
                }
                KeyCode::Down => {
                    if self.search_popup.expanded {
                        self.search_popup.scroll_down(1);
                    } else {
                        self.search_popup.next();
                    }
                    return;
                }
                KeyCode::Enter => {
                    self.search_popup.toggle_expand();
                    return;
                }
                KeyCode::Esc | KeyCode::Char('q') => {
                    if self.search_popup.expanded {
                        self.search_popup.expanded = false;
                        self.search_popup.scroll_offset = 0;
                    } else {
                        self.search_popup.close();
                    }
                    return;
                }
                KeyCode::PageUp => {
                    self.search_popup.scroll_up(5);
                    return;
                }
                KeyCode::PageDown => {
                    self.search_popup.scroll_down(5);
                    return;
                }
                _ => return,
            }
        }

        // Autocomplete navigation
        if self.autocomplete.visible {
            match key.code {
                KeyCode::Tab | KeyCode::Down => {
                    self.autocomplete.next();
                    return;
                }
                KeyCode::BackTab | KeyCode::Up => {
                    self.autocomplete.prev();
                    return;
                }
                KeyCode::Enter => {
                    if let Some(cmd) = self.autocomplete.accept() {
                        self.input_bar.content = format!("{} ", cmd);
                        self.input_bar.cursor_pos = self.input_bar.content.len();
                    }
                    return;
                }
                KeyCode::Esc => {
                    self.autocomplete.visible = false;
                    return;
                }
                _ => {
                    // Fall through to normal input handling
                    self.autocomplete.visible = false;
                }
            }
        }

        match key.code {
            KeyCode::Enter => {
                let content = self.input_bar.take_content();
                self.handle_submit(content).await;
            }
            KeyCode::Char(c) => {
                self.input_bar.insert(c);
                self.update_autocomplete();
            }
            KeyCode::Backspace => {
                self.input_bar.backspace();
                self.update_autocomplete();
            }
            KeyCode::Delete => {
                self.input_bar.delete();
            }
            KeyCode::Left => {
                self.input_bar.move_left();
            }
            KeyCode::Right => {
                self.input_bar.move_right();
            }
            KeyCode::Home => {
                self.input_bar.home();
            }
            KeyCode::End => {
                self.input_bar.end();
            }
            KeyCode::Up => {
                if key.modifiers.contains(KeyModifiers::SHIFT) {
                    self.chat_window.scroll_up(3);
                } else {
                    self.input_bar.history_prev();
                }
            }
            KeyCode::Down => {
                if key.modifiers.contains(KeyModifiers::SHIFT) {
                    self.chat_window.scroll_down(3);
                } else {
                    self.input_bar.history_next();
                }
            }
            KeyCode::PageUp => {
                self.chat_window.scroll_up(10);
            }
            KeyCode::PageDown => {
                self.chat_window.scroll_down(10);
            }
            KeyCode::Tab => {
                if self.input_bar.content.starts_with('/') {
                    self.update_autocomplete();
                    self.autocomplete.visible = true;
                }
            }
            KeyCode::Esc => {
                // If in a non-chat mode, switch back to chat
                if self.mode != Mode::Chat {
                    self.mode = Mode::Chat;
                }
            }
            _ => {}
        }
    }

    fn update_autocomplete(&mut self) {
        let plugin_cmds: Vec<(String, String)> = self
            .plugin_manager
            .all_commands()
            .iter()
            .map(|(name, cmd, _)| (name.clone(), cmd.clone()))
            .collect();
        self.autocomplete
            .update(&self.input_bar.content, &plugin_cmds);
    }

    async fn handle_submit(&mut self, content: String) {
        let parsed = input::parse_input(&content);

        match parsed {
            ParsedInput::Quit => {
                self.running = false;
            }
            ParsedInput::Empty => {}
            ParsedInput::Command(cmd, args) => {
                self.handle_command(&cmd, &args).await;
            }
            ParsedInput::ChatMessage(text) => {
                self.handle_chat_message(&text).await;
            }
        }
    }

    async fn handle_command(&mut self, command: &str, args: &[String]) {
        let cmd = command.trim_start_matches('/');

        // Mode switch
        if let Some(mode) = Mode::from_command(cmd) {
            self.mode = mode;
            self.chat_window.push(ChatMessage {
                role: MessageRole::System,
                content: format!("Switched to {} mode", mode.label()),
                citations: Vec::new(),
            });
            return;
        }

        match cmd {
            "help" => {
                let help_text = Mode::ALL
                    .iter()
                    .map(|m| format!("  {:<12} {}", m.command(), m.description()))
                    .collect::<Vec<_>>()
                    .join("\n");
                self.chat_window.push(ChatMessage {
                    role: MessageRole::System,
                    content: format!(
                        "Available commands:\n{}\n  /quit         Exit CiteIndex\n  /help         Show this help\n  /memory       Search memory\n  /clear        Clear chat",
                        help_text
                    ),
                    citations: Vec::new(),
                });
            }
            "clear" => {
                self.chat_window.clear();
            }
            "memory" => {
                let query = args.join(" ");
                if query.is_empty() {
                    self.chat_window.push(ChatMessage {
                        role: MessageRole::System,
                        content: "Usage: /memory <search query>".into(),
                        citations: Vec::new(),
                    });
                } else {
                    let results = self.engine.memory_search(&query, None);
                    if results.is_empty() {
                        self.chat_window.push(ChatMessage {
                            role: MessageRole::System,
                            content: "No memory entries found.".into(),
                            citations: Vec::new(),
                        });
                    } else {
                        let mut text = format!("Found {} memory entries:\n", results.len());
                        for (i, entry) in results.iter().take(10).enumerate() {
                            text.push_str(&format!(
                                "\n{}. [{}] Q: {}\n   A: {}\n",
                                i + 1,
                                entry.timestamp,
                                truncate(&entry.query, 80),
                                truncate(&entry.response, 120),
                            ));
                        }
                        self.chat_window.push(ChatMessage {
                            role: MessageRole::System,
                            content: text,
                            citations: Vec::new(),
                        });
                    }
                }
            }
            "search-history" => {
                if self.search_popup.history.is_empty() {
                    self.chat_window.push(ChatMessage {
                        role: MessageRole::System,
                        content: "No search history.".into(),
                        citations: Vec::new(),
                    });
                } else {
                    let mut text = format!(
                        "Search history ({} entries):\n",
                        self.search_popup.history.len()
                    );
                    for (i, entry) in self.search_popup.history.iter().rev().take(20).enumerate() {
                        text.push_str(&format!(
                            "\n{}. [{}] \"{}\" → {} results",
                            i + 1,
                            entry.timestamp,
                            entry.query,
                            entry.result_count
                        ));
                    }
                    self.chat_window.push(ChatMessage {
                        role: MessageRole::System,
                        content: text,
                        citations: Vec::new(),
                    });
                }
            }
            _ => {
                // Try plugin commands
                let plugin_cmds = self.plugin_manager.all_commands();
                if let Some((_, cmd_value, dir)) =
                    plugin_cmds.iter().find(|(name, _, _)| name == cmd)
                {
                    self.chat_window.push(ChatMessage {
                        role: MessageRole::System,
                        content: format!("Running plugin command: {} ...", cmd),
                        citations: Vec::new(),
                    });
                    let runner = citeindex_plugins::runner::PluginRunner::new(dir);
                    let full_cmd = if args.is_empty() {
                        cmd_value.clone()
                    } else {
                        format!("{} {}", cmd_value, args.join(" "))
                    };
                    match runner.run_command_sync(&full_cmd) {
                        Ok(output) => {
                            self.chat_window.push(ChatMessage {
                                role: MessageRole::System,
                                content: if output.success {
                                    output.stdout
                                } else {
                                    format!(
                                        "Plugin error (exit {}): {}",
                                        output.exit_code, output.stderr
                                    )
                                },
                                citations: Vec::new(),
                            });
                        }
                        Err(e) => {
                            self.chat_window.push(ChatMessage {
                                role: MessageRole::System,
                                content: format!("Plugin execution failed: {}", e),
                                citations: Vec::new(),
                            });
                        }
                    }
                } else {
                    self.chat_window.push(ChatMessage {
                        role: MessageRole::System,
                        content: format!("Unknown command: /{}. Type /help for commands.", cmd),
                        citations: Vec::new(),
                    });
                }
            }
        }
    }

    async fn handle_chat_message(&mut self, text: &str) {
        // Show user message
        self.chat_window.push(ChatMessage {
            role: MessageRole::User,
            content: text.to_string(),
            citations: Vec::new(),
        });

        self.busy = true;

        // Dispatch based on mode
        match self.mode {
            Mode::Chat => {
                self.chat_window.push(ChatMessage {
                    role: MessageRole::System,
                    content: "Thinking...".into(),
                    citations: Vec::new(),
                });

                match self.engine.chat(text, &self.thread_id).await {
                    Ok(response) => {
                        // Remove "Thinking..." message
                        self.chat_window.messages.pop();

                        let answer = response
                            .get("answer_human")
                            .and_then(|v| v.as_str())
                            .unwrap_or("(no answer)");

                        let citations: Vec<String> = response
                            .get("answer_machine")
                            .and_then(|m| m.get("evidence"))
                            .and_then(|e| e.as_array())
                            .map(|arr| {
                                arr.iter()
                                    .filter_map(|v| {
                                        v.get("citation_rendered")
                                            .and_then(|c| c.as_str())
                                            .map(String::from)
                                    })
                                    .collect()
                            })
                            .unwrap_or_default();

                        self.chat_window.push(ChatMessage {
                            role: MessageRole::Assistant,
                            content: answer.to_string(),
                            citations,
                        });
                    }
                    Err(e) => {
                        self.chat_window.messages.pop();
                        self.chat_window.push(ChatMessage {
                            role: MessageRole::System,
                            content: format!("Error: {}", e),
                            citations: Vec::new(),
                        });
                    }
                }
            }
            Mode::Search => {
                let query_text = text.to_string();
                match self.engine.search(text).await {
                    Ok(response) => {
                        let results = response.get("results").and_then(|r| r.as_array());

                        if let Some(results) = results {
                            let count = results.len();
                            let mut popup_entries = Vec::new();
                            let mut side_items = Vec::new();

                            for r in results.iter() {
                                let node_id =
                                    r.get("node_id").and_then(|v| v.as_str()).unwrap_or("?");
                                let node_text =
                                    r.get("text").and_then(|v| v.as_str()).unwrap_or("");
                                let score =
                                    r.get("total_score").and_then(|v| v.as_f64()).unwrap_or(0.0);
                                let title = r.get("title").and_then(|v| v.as_str()).unwrap_or("");
                                let author = r.get("author").and_then(|v| v.as_str()).unwrap_or("");
                                let citation = r
                                    .get("formatted_citation")
                                    .and_then(|v| v.as_str())
                                    .unwrap_or("");

                                popup_entries.push(SearchResultEntry {
                                    title: title.to_string(),
                                    author: author.to_string(),
                                    text: node_text.to_string(),
                                    formatted_citation: citation.to_string(),
                                    score,
                                    node_id: node_id.to_string(),
                                });

                                side_items.push(SidePanelItem {
                                    label: truncate(title, 30).to_string(),
                                    detail: format!("score: {:.2}", score),
                                });
                            }

                            self.side_panel.set_search_results(side_items);
                            self.search_popup.open(popup_entries, &query_text);

                            self.chat_window.push(ChatMessage {
                                role: MessageRole::System,
                                content: format!("Found {} results. Use ↑↓ to navigate, Enter to expand, Esc to close.", count),
                                citations: Vec::new(),
                            });
                        } else {
                            self.chat_window.push(ChatMessage {
                                role: MessageRole::System,
                                content: "No results found.".into(),
                                citations: Vec::new(),
                            });
                        }
                    }
                    Err(e) => {
                        self.chat_window.push(ChatMessage {
                            role: MessageRole::System,
                            content: format!("Search error: {}", e),
                            citations: Vec::new(),
                        });
                    }
                }
            }
            Mode::Ingest => {
                // Treat input as a file path to ingest
                self.chat_window.push(ChatMessage {
                    role: MessageRole::System,
                    content: format!("Ingesting: {} ...", text),
                    citations: Vec::new(),
                });

                match self.engine.ingest(text, &[]).await {
                    Ok(response) => {
                        let status = response
                            .get("status")
                            .and_then(|v| v.as_str())
                            .unwrap_or("unknown");
                        let doc_path = response
                            .get("document_path")
                            .and_then(|v| v.as_str())
                            .unwrap_or("");

                        let msg = if status == "ok" {
                            self.side_panel
                                .add_recent_document(text.to_string(), doc_path.to_string());
                            format!("Ingestion complete: {}", doc_path)
                        } else {
                            format!("Ingestion failed: {}", status)
                        };

                        self.chat_window.push(ChatMessage {
                            role: MessageRole::System,
                            content: msg,
                            citations: Vec::new(),
                        });
                    }
                    Err(e) => {
                        self.chat_window.push(ChatMessage {
                            role: MessageRole::System,
                            content: format!("Ingestion error: {}", e),
                            citations: Vec::new(),
                        });
                    }
                }
            }
            Mode::PageIndex => {
                self.chat_window.push(ChatMessage {
                    role: MessageRole::System,
                    content: format!("PageIndex reasoning search: {} ...", text),
                    citations: Vec::new(),
                });

                match self.engine.search(text).await {
                    Ok(response) => {
                        let results = response.get("results").and_then(|r| r.as_array());

                        if let Some(results) = results {
                            let count = results.len();
                            self.chat_window.push(ChatMessage {
                                role: MessageRole::System,
                                content: format!("PageIndex found {} relevant sections.", count),
                                citations: Vec::new(),
                            });
                            for r in results.iter().take(5) {
                                let heading = r.get("section_path")
                                    .and_then(|v| v.as_str())
                                    .unwrap_or("(unknown section)");
                                let text_preview = r.get("text")
                                    .and_then(|v| v.as_str())
                                    .unwrap_or("");
                                let preview = truncate(text_preview, 120);
                                self.chat_window.push(ChatMessage {
                                    role: MessageRole::Assistant,
                                    content: format!("§ {}\n{}", heading, preview),
                                    citations: Vec::new(),
                                });
                            }
                        } else {
                            self.chat_window.push(ChatMessage {
                                role: MessageRole::System,
                                content: "No relevant sections found.".into(),
                                citations: Vec::new(),
                            });
                        }
                    }
                    Err(e) => {
                        self.chat_window.push(ChatMessage {
                            role: MessageRole::System,
                            content: format!("PageIndex search error: {}", e),
                            citations: Vec::new(),
                        });
                    }
                }
            }
            _ => {
                self.chat_window.push(ChatMessage {
                    role: MessageRole::System,
                    content: format!(
                        "{} mode: processing '{}' not yet implemented in TUI",
                        self.mode.label(),
                        text
                    ),
                    citations: Vec::new(),
                });
            }
        }

        self.busy = false;
    }
}

fn truncate(s: &str, max: usize) -> &str {
    if s.len() <= max {
        s
    } else {
        let mut end = max;
        while !s.is_char_boundary(end) && end > 0 {
            end -= 1;
        }
        &s[..end]
    }
}
