//! UI rendering — draws the TUI layout using ratatui.
//!
//! Layout: top bar, scrollable chat window, input bar, collapsible side panel.
//! Matches `frontend_ui_rust.yaml → layout_main`.

use crate::app::App;
use crate::mode::Mode;
use crate::panels::{MessageRole, SidePanelSection};
use crate::theme::Theme;

use ratatui::layout::{Constraint, Direction, Layout, Rect};
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span, Text};
use ratatui::widgets::{
    Block, Borders, Clear, List, ListItem, Paragraph, Scrollbar, ScrollbarOrientation,
    ScrollbarState, Wrap,
};
use ratatui::Frame;

pub fn draw(f: &mut Frame, app: &App) {
    let theme = &app.theme;
    let area = f.area();

    // Fill background
    f.render_widget(Block::default().style(theme.base_style()), area);

    // Main vertical layout: top bar (1), content (dynamic), input (3)
    let main_chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(1), // top bar
            Constraint::Min(5),    // content area
            Constraint::Length(3), // input bar
        ])
        .split(area);

    draw_top_bar(f, app, main_chunks[0]);

    // Content: chat window + optional side panel
    if !app.side_panel.collapsed {
        let content_chunks = Layout::default()
            .direction(Direction::Horizontal)
            .constraints([
                Constraint::Percentage(100 - app.side_panel.width_pct),
                Constraint::Percentage(app.side_panel.width_pct),
            ])
            .split(main_chunks[1]);

        draw_chat_window(f, app, content_chunks[0]);
        draw_side_panel(f, app, content_chunks[1]);
    } else {
        draw_chat_window(f, app, main_chunks[1]);
    }

    draw_input_bar(f, app, main_chunks[2]);

    // Draw autocomplete overlay if visible
    if app.autocomplete.visible {
        draw_autocomplete(f, app, main_chunks[2]);
    }

    // Draw search results popup if visible
    if app.search_popup.visible {
        draw_search_popup(f, app, area);
    }
}

fn draw_top_bar(f: &mut Frame, app: &App, area: Rect) {
    let theme = &app.theme;
    let mode_label = app.mode.label();
    let theme_label = match theme.mode {
        crate::theme::ThemeMode::Dark => "Dark",
        crate::theme::ThemeMode::Light => "Light",
    };

    let spans = vec![
        Span::styled(
            " CiteIndex ",
            theme.accent_style().add_modifier(Modifier::BOLD),
        ),
        Span::styled(" │ ", theme.dim_style()),
        Span::styled(format!("Mode: {} ", mode_label), theme.top_bar_style()),
        Span::styled(" │ ", theme.dim_style()),
        Span::styled(format!("Theme: {} ", theme_label), theme.top_bar_style()),
        Span::styled(" │ ", theme.dim_style()),
        Span::styled(
            " Ctrl+T:Theme  Tab:Complete  Ctrl+B:Panel  /:Commands ",
            theme.dim_style(),
        ),
    ];

    let bar = Paragraph::new(Line::from(spans)).style(theme.top_bar_style());
    f.render_widget(bar, area);
}

fn draw_chat_window(f: &mut Frame, app: &App, area: Rect) {
    let theme = &app.theme;
    let block = Block::default()
        .borders(Borders::ALL)
        .border_style(theme.border_style())
        .title(Span::styled(
            format!(" {} ", app.mode.label()),
            theme.accent_style(),
        ))
        .style(theme.base_style());

    let inner = block.inner(area);
    f.render_widget(block, area);

    // Render messages
    let mut lines: Vec<Line> = Vec::new();
    for msg in &app.chat_window.messages {
        let (prefix, style) = match msg.role {
            MessageRole::User => (
                "You: ",
                Style::default()
                    .fg(theme.accent)
                    .add_modifier(Modifier::BOLD),
            ),
            MessageRole::Assistant => ("AI: ", Style::default().fg(theme.success)),
            MessageRole::System => ("ℹ ", theme.dim_style()),
        };

        lines.push(Line::from(vec![Span::styled(prefix, style)]));

        // Wrap content lines
        for content_line in msg.content.lines() {
            lines.push(Line::from(vec![Span::styled(
                format!("  {}", content_line),
                theme.base_style(),
            )]));
        }

        // Show citations if any
        for citation in &msg.citations {
            lines.push(Line::from(vec![Span::styled(
                format!("  📚 {}", citation),
                theme.dim_style(),
            )]));
        }

        lines.push(Line::from(""));
    }

    // Handle scrolling
    let total_lines = lines.len() as u16;
    let visible_height = inner.height;
    let max_scroll = total_lines.saturating_sub(visible_height);
    let scroll = max_scroll.saturating_sub(app.chat_window.scroll_offset);

    let text = Text::from(lines);
    let paragraph = Paragraph::new(text)
        .wrap(Wrap { trim: false })
        .scroll((scroll, 0));

    f.render_widget(paragraph, inner);
}

fn draw_side_panel(f: &mut Frame, app: &App, area: Rect) {
    let theme = &app.theme;
    let block = Block::default()
        .borders(Borders::ALL)
        .border_style(theme.border_style())
        .title(Span::styled(" Documents ", theme.accent_style()))
        .style(theme.base_style());

    let inner = block.inner(area);
    f.render_widget(block, area);

    let items: Vec<ListItem> = match app.side_panel.active_section {
        SidePanelSection::RecentDocuments => app
            .side_panel
            .recent_documents
            .iter()
            .map(|item| {
                ListItem::new(vec![
                    Line::from(Span::styled(&item.label, theme.accent_style())),
                    Line::from(Span::styled(
                        format!("  {}", item.detail),
                        theme.dim_style(),
                    )),
                ])
            })
            .collect(),
        SidePanelSection::SearchResults => app
            .side_panel
            .search_results
            .iter()
            .map(|item| {
                ListItem::new(vec![
                    Line::from(Span::styled(&item.label, theme.accent_style())),
                    Line::from(Span::styled(
                        format!("  {}", item.detail),
                        theme.dim_style(),
                    )),
                ])
            })
            .collect(),
        SidePanelSection::PluginShortcuts => app
            .side_panel
            .plugin_shortcuts
            .iter()
            .map(|item| ListItem::new(Line::from(Span::styled(&item.label, theme.base_style()))))
            .collect(),
    };

    if items.is_empty() {
        let empty = Paragraph::new("No items").style(theme.dim_style());
        f.render_widget(empty, inner);
    } else {
        let list = List::new(items);
        f.render_widget(list, inner);
    }
}

fn draw_input_bar(f: &mut Frame, app: &App, area: Rect) {
    let theme = &app.theme;
    let block = Block::default()
        .borders(Borders::ALL)
        .border_style(theme.border_style())
        .title(Span::styled(" Input ", theme.dim_style()))
        .style(theme.input_style());

    let inner = block.inner(area);
    f.render_widget(block, area);

    let display_text = if app.input_bar.content.is_empty() {
        Span::styled(
            "Type your message or '/' for commands...",
            theme.dim_style(),
        )
    } else {
        Span::styled(&app.input_bar.content, theme.input_style())
    };

    let paragraph = Paragraph::new(Line::from(vec![display_text]));
    f.render_widget(paragraph, inner);

    // Show cursor
    let cursor_x = inner.x + app.input_bar.cursor_pos as u16;
    let cursor_y = inner.y;
    if cursor_x < inner.x + inner.width {
        f.set_cursor_position((cursor_x, cursor_y));
    }
}

fn draw_autocomplete(f: &mut Frame, app: &App, input_area: Rect) {
    let theme = &app.theme;
    let count = app.autocomplete.suggestions.len().min(8);
    if count == 0 {
        return;
    }

    let height = count as u16 + 2; // +2 for borders
    let popup_area = Rect {
        x: input_area.x + 1,
        y: input_area.y.saturating_sub(height),
        width: input_area.width.min(50),
        height,
    };

    f.render_widget(Clear, popup_area);

    let block = Block::default()
        .borders(Borders::ALL)
        .border_style(theme.accent_style())
        .style(Style::default().bg(theme.bg));

    let items: Vec<ListItem> = app
        .autocomplete
        .suggestions
        .iter()
        .enumerate()
        .take(8)
        .map(|(i, s)| {
            let style = if i == app.autocomplete.selected {
                theme.highlight_style()
            } else {
                theme.base_style()
            };
            ListItem::new(Line::from(vec![
                Span::styled(
                    format!("{:<12}", s.command),
                    style.add_modifier(Modifier::BOLD),
                ),
                Span::styled(format!(" {}", s.description), style),
            ]))
        })
        .collect();

    let list = List::new(items).block(block);
    f.render_widget(list, popup_area);
}

fn draw_search_popup(f: &mut Frame, app: &App, area: Rect) {
    let theme = &app.theme;
    let popup = &app.search_popup;

    // Center the popup: 80% width, 70% height
    let popup_width = (area.width as f32 * 0.80) as u16;
    let popup_height = (area.height as f32 * 0.70) as u16;
    let popup_x = area.x + (area.width.saturating_sub(popup_width)) / 2;
    let popup_y = area.y + (area.height.saturating_sub(popup_height)) / 2;
    let popup_area = Rect {
        x: popup_x,
        y: popup_y,
        width: popup_width,
        height: popup_height,
    };

    f.render_widget(Clear, popup_area);

    if popup.expanded {
        // Expanded detail view for the selected result
        if let Some(entry) = popup.selected_result() {
            let block = Block::default()
                .borders(Borders::ALL)
                .border_style(theme.accent_style())
                .title(Span::styled(
                    " Search Result — Esc: back  ↑↓/PgUp/PgDn: scroll ",
                    theme.accent_style(),
                ))
                .style(Style::default().bg(theme.bg));

            let inner = block.inner(popup_area);
            f.render_widget(block, popup_area);

            let mut lines: Vec<Line> = Vec::new();

            // Title
            lines.push(Line::from(vec![
                Span::styled("Title: ", theme.accent_style()),
                Span::styled(
                    &entry.title,
                    Style::default().fg(theme.fg).add_modifier(Modifier::BOLD),
                ),
            ]));

            // Author
            if !entry.author.is_empty() {
                lines.push(Line::from(vec![
                    Span::styled("Author: ", theme.accent_style()),
                    Span::styled(&entry.author, Style::default().fg(theme.fg)),
                ]));
            }

            // Score
            lines.push(Line::from(vec![
                Span::styled("Score: ", theme.accent_style()),
                Span::styled(
                    format!("{:.4}", entry.score),
                    Style::default().fg(theme.success),
                ),
            ]));

            // Node ID
            lines.push(Line::from(vec![
                Span::styled("Node: ", theme.dim_style()),
                Span::styled(&entry.node_id, theme.dim_style()),
            ]));

            lines.push(Line::from(""));

            // Formatted citation
            if !entry.formatted_citation.is_empty() {
                lines.push(Line::from(Span::styled(
                    "── Citation ──",
                    theme.accent_style(),
                )));
                for line in entry.formatted_citation.lines() {
                    lines.push(Line::from(Span::styled(
                        format!("  {}", line),
                        Style::default().fg(theme.warning),
                    )));
                }
                lines.push(Line::from(""));
            }

            // Full text
            lines.push(Line::from(Span::styled("── Text ──", theme.accent_style())));
            for line in entry.text.lines() {
                lines.push(Line::from(Span::styled(
                    format!("  {}", line),
                    Style::default().fg(theme.fg),
                )));
            }

            let total_lines = lines.len() as u16;
            let visible = inner.height;
            let max_scroll = total_lines.saturating_sub(visible);
            let scroll = max_scroll.saturating_sub(popup.scroll_offset);

            let text = Text::from(lines);
            let paragraph = Paragraph::new(text)
                .wrap(Wrap { trim: false })
                .scroll((scroll, 0));

            f.render_widget(paragraph, inner);
        }
    } else {
        // List view
        let block = Block::default()
            .borders(Borders::ALL)
            .border_style(theme.accent_style())
            .title(Span::styled(
                format!(
                    " Search Results ({}) — ↑↓: select  Enter: expand  q/Esc: close ",
                    popup.results.len()
                ),
                theme.accent_style(),
            ))
            .style(Style::default().bg(theme.bg));

        let inner = block.inner(popup_area);
        f.render_widget(block, popup_area);

        let items: Vec<ListItem> = popup
            .results
            .iter()
            .enumerate()
            .map(|(i, entry)| {
                let style = if i == popup.selected {
                    theme.highlight_style()
                } else {
                    theme.base_style()
                };

                let score_span = Span::styled(
                    format!("[{:.2}] ", entry.score),
                    if i == popup.selected {
                        style
                    } else {
                        Style::default().fg(theme.success)
                    },
                );

                let title_span = Span::styled(
                    if entry.title.is_empty() {
                        "(untitled)"
                    } else {
                        &entry.title
                    },
                    style.add_modifier(Modifier::BOLD),
                );

                let mut row_lines = vec![Line::from(vec![
                    Span::styled(format!("{:>2}. ", i + 1), style),
                    score_span,
                    title_span,
                ])];

                // Show formatted citation preview on second line
                if !entry.formatted_citation.is_empty() {
                    let cite_preview = if entry.formatted_citation.len() > 80 {
                        format!("    📚 {}…", &entry.formatted_citation[..80])
                    } else {
                        format!("    📚 {}", &entry.formatted_citation)
                    };
                    row_lines.push(Line::from(Span::styled(
                        cite_preview,
                        if i == popup.selected {
                            style
                        } else {
                            theme.dim_style()
                        },
                    )));
                }

                ListItem::new(row_lines)
            })
            .collect();

        let list = List::new(items);
        f.render_widget(list, inner);
    }
}
