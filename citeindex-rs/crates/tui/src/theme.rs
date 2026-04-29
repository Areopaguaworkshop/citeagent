//! Theme manager — light/dark toggle with Ctrl+T.

use ratatui::style::{Color, Modifier, Style};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ThemeMode {
    Dark,
    Light,
}

impl ThemeMode {
    pub fn toggle(self) -> Self {
        match self {
            Self::Dark => Self::Light,
            Self::Light => Self::Dark,
        }
    }
}

#[derive(Debug, Clone)]
pub struct Theme {
    pub mode: ThemeMode,
    pub bg: Color,
    pub fg: Color,
    pub accent: Color,
    pub border: Color,
    pub highlight_bg: Color,
    pub highlight_fg: Color,
    pub dim: Color,
    pub error: Color,
    pub success: Color,
    pub warning: Color,
    pub top_bar_bg: Color,
    pub top_bar_fg: Color,
    pub input_bg: Color,
    pub input_fg: Color,
}

impl Theme {
    pub fn dark() -> Self {
        Self {
            mode: ThemeMode::Dark,
            bg: Color::Rgb(22, 22, 30),
            fg: Color::Rgb(220, 220, 230),
            accent: Color::Rgb(100, 180, 255),
            border: Color::Rgb(60, 60, 80),
            highlight_bg: Color::Rgb(40, 40, 60),
            highlight_fg: Color::White,
            dim: Color::Rgb(120, 120, 140),
            error: Color::Rgb(255, 100, 100),
            success: Color::Rgb(100, 220, 100),
            warning: Color::Rgb(255, 200, 80),
            top_bar_bg: Color::Rgb(30, 30, 50),
            top_bar_fg: Color::Rgb(180, 180, 200),
            input_bg: Color::Rgb(28, 28, 40),
            input_fg: Color::Rgb(220, 220, 230),
        }
    }

    pub fn light() -> Self {
        Self {
            mode: ThemeMode::Light,
            bg: Color::Rgb(250, 250, 252),
            fg: Color::Rgb(30, 30, 40),
            accent: Color::Rgb(30, 100, 200),
            border: Color::Rgb(200, 200, 210),
            highlight_bg: Color::Rgb(220, 230, 245),
            highlight_fg: Color::Black,
            dim: Color::Rgb(140, 140, 160),
            error: Color::Rgb(200, 50, 50),
            success: Color::Rgb(30, 160, 30),
            warning: Color::Rgb(200, 150, 20),
            top_bar_bg: Color::Rgb(235, 235, 242),
            top_bar_fg: Color::Rgb(60, 60, 80),
            input_bg: Color::Rgb(245, 245, 250),
            input_fg: Color::Rgb(30, 30, 40),
        }
    }

    pub fn from_mode(mode: ThemeMode) -> Self {
        match mode {
            ThemeMode::Dark => Self::dark(),
            ThemeMode::Light => Self::light(),
        }
    }

    pub fn base_style(&self) -> Style {
        Style::default().fg(self.fg).bg(self.bg)
    }

    pub fn top_bar_style(&self) -> Style {
        Style::default().fg(self.top_bar_fg).bg(self.top_bar_bg)
    }

    pub fn input_style(&self) -> Style {
        Style::default().fg(self.input_fg).bg(self.input_bg)
    }

    pub fn border_style(&self) -> Style {
        Style::default().fg(self.border)
    }

    pub fn accent_style(&self) -> Style {
        Style::default()
            .fg(self.accent)
            .add_modifier(Modifier::BOLD)
    }

    pub fn dim_style(&self) -> Style {
        Style::default().fg(self.dim)
    }

    pub fn highlight_style(&self) -> Style {
        Style::default().fg(self.highlight_fg).bg(self.highlight_bg)
    }
}
