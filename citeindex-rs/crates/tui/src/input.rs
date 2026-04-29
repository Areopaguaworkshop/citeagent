//! Input handling — keyboard events, command parsing, autocomplete.
//!
//! Matches `frontend_ui_rust.yaml → input_parser` and `command_autocomplete`.

use crate::mode::Mode;

/// Parsed user input — either a command or chat text.
#[derive(Debug)]
pub enum ParsedInput {
    /// A slash command (mode switch or action).
    Command(String, Vec<String>),
    /// Chat text to send to the LLM.
    ChatMessage(String),
    /// Quit the application.
    Quit,
    /// Empty input.
    Empty,
}

/// Parse raw input text into a command or chat message.
pub fn parse_input(raw: &str) -> ParsedInput {
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return ParsedInput::Empty;
    }

    if trimmed == "/quit" || trimmed == "/exit" || trimmed == "/q" {
        return ParsedInput::Quit;
    }

    if trimmed.starts_with('/') {
        let parts: Vec<&str> = trimmed.splitn(2, ' ').collect();
        let command = parts[0].to_string();
        let args: Vec<String> = if parts.len() > 1 {
            parts[1].split_whitespace().map(String::from).collect()
        } else {
            Vec::new()
        };
        return ParsedInput::Command(command, args);
    }

    ParsedInput::ChatMessage(trimmed.to_string())
}

/// Autocomplete suggestions for a partial slash command.
pub struct AutocompleteState {
    pub suggestions: Vec<AutocompleteSuggestion>,
    pub selected: usize,
    pub visible: bool,
}

pub struct AutocompleteSuggestion {
    pub command: String,
    pub label: String,
    pub description: String,
}

impl AutocompleteState {
    pub fn new() -> Self {
        Self {
            suggestions: Vec::new(),
            selected: 0,
            visible: false,
        }
    }

    /// Update suggestions based on current input.
    pub fn update(&mut self, input: &str, plugin_commands: &[(String, String)]) {
        if !input.starts_with('/') || input.contains(' ') {
            self.visible = false;
            self.suggestions.clear();
            return;
        }

        let query = &input[1..];
        self.suggestions.clear();

        // Mode commands
        let modes = Mode::fuzzy_match(query);
        for mode in modes {
            self.suggestions.push(AutocompleteSuggestion {
                command: mode.command().to_string(),
                label: mode.label().to_string(),
                description: mode.description().to_string(),
            });
        }

        // Plugin commands
        for (cmd, desc) in plugin_commands {
            let full_cmd = format!("/{}", cmd);
            if cmd.to_lowercase().contains(&query.to_lowercase()) {
                self.suggestions.push(AutocompleteSuggestion {
                    command: full_cmd,
                    label: cmd.clone(),
                    description: desc.clone(),
                });
            }
        }

        // Built-in commands
        for (cmd, desc) in [
            ("/quit", "Exit CiteIndex"),
            ("/help", "Show help"),
            ("/memory", "Search memory"),
            ("/clear", "Clear chat"),
            ("/search-history", "Show search history"),
        ] {
            if cmd[1..].contains(&query.to_lowercase()) {
                self.suggestions.push(AutocompleteSuggestion {
                    command: cmd.to_string(),
                    label: cmd.to_string(),
                    description: desc.to_string(),
                });
            }
        }

        self.visible = !self.suggestions.is_empty();
        self.selected = 0;
    }

    pub fn next(&mut self) {
        if !self.suggestions.is_empty() {
            self.selected = (self.selected + 1) % self.suggestions.len();
        }
    }

    pub fn prev(&mut self) {
        if !self.suggestions.is_empty() {
            self.selected = self
                .selected
                .checked_sub(1)
                .unwrap_or(self.suggestions.len() - 1);
        }
    }

    pub fn accept(&mut self) -> Option<String> {
        if self.visible && self.selected < self.suggestions.len() {
            let cmd = self.suggestions[self.selected].command.clone();
            self.visible = false;
            self.suggestions.clear();
            Some(cmd)
        } else {
            None
        }
    }
}
