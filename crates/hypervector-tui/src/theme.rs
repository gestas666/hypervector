//! Semantic truecolor theme for hypervector-tui.
//!
//! Mode colors, signed PnL, muted chrome. Degrades to ANSI when truecolor
//! is unavailable (terminal still usable).

use ratatui::style::{Color, Modifier, Style};

/// Execution mode as rendered on the banner.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum ExecMode {
    #[default]
    Shadow,
    Paper,
    Live,
}

impl ExecMode {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Shadow => "SHADOW",
            Self::Paper => "PAPER",
            Self::Live => "LIVE",
        }
    }

    pub fn parse(s: &str) -> Self {
        match s.to_ascii_lowercase().as_str() {
            "live" => Self::Live,
            "paper" => Self::Paper,
            _ => Self::Shadow,
        }
    }
}

/// Semantic palette (tickrs/btop inspired density; not carnival).
#[derive(Debug, Clone)]
pub struct Theme {
    pub bg: Color,
    pub fg: Color,
    pub muted: Color,
    pub border: Color,
    pub border_focus: Color,
    pub title: Color,
    pub mode_shadow: Color,
    pub mode_paper: Color,
    pub mode_live: Color,
    pub mode_live_bg: Color,
    pub positive: Color,
    pub negative: Color,
    pub warning: Color,
    pub accent: Color,
    pub gauge_ok: Color,
    pub gauge_warn: Color,
    pub truecolor: bool,
}

impl Default for Theme {
    fn default() -> Self {
        Self::truecolor()
    }
}

impl Theme {
    /// Full truecolor palette for modern terminals (Ghostty/Kitty/WezTerm).
    pub fn truecolor() -> Self {
        Self {
            bg: Color::Rgb(12, 14, 18),
            fg: Color::Rgb(220, 224, 230),
            muted: Color::Rgb(110, 118, 130),
            border: Color::Rgb(45, 52, 64),
            border_focus: Color::Rgb(88, 166, 255),
            title: Color::Rgb(180, 190, 205),
            mode_shadow: Color::Rgb(210, 180, 80),
            mode_paper: Color::Rgb(80, 180, 220),
            mode_live: Color::Rgb(255, 255, 255),
            mode_live_bg: Color::Rgb(160, 30, 40),
            positive: Color::Rgb(60, 200, 120),
            negative: Color::Rgb(230, 80, 90),
            warning: Color::Rgb(230, 170, 60),
            accent: Color::Rgb(130, 160, 255),
            gauge_ok: Color::Rgb(50, 160, 110),
            gauge_warn: Color::Rgb(210, 140, 40),
            truecolor: true,
        }
    }

    /// ANSI-safe fallback for limited terminals.
    pub fn ansi() -> Self {
        Self {
            bg: Color::Reset,
            fg: Color::White,
            muted: Color::DarkGray,
            border: Color::DarkGray,
            border_focus: Color::Cyan,
            title: Color::Gray,
            mode_shadow: Color::Yellow,
            mode_paper: Color::Cyan,
            mode_live: Color::White,
            mode_live_bg: Color::Red,
            positive: Color::Green,
            negative: Color::Red,
            warning: Color::Yellow,
            accent: Color::Blue,
            gauge_ok: Color::Green,
            gauge_warn: Color::Yellow,
            truecolor: false,
        }
    }

    /// Prefer truecolor; callers can force ANSI via env later.
    pub fn detect() -> Self {
        // COLORTERM=truecolor|24bit is common; also TERM_PROGRAM heuristics.
        let ct = std::env::var("COLORTERM").unwrap_or_default();
        if ct.contains("truecolor") || ct.contains("24bit") {
            return Self::truecolor();
        }
        let term = std::env::var("TERM").unwrap_or_default();
        if term.contains("256color") || term.contains("truecolor") {
            return Self::truecolor();
        }
        // Modern default: try truecolor; ratatui degrades if unsupported.
        Self::truecolor()
    }

    pub fn mode_style(&self, mode: ExecMode) -> Style {
        match mode {
            ExecMode::Shadow => Style::default()
                .fg(self.mode_shadow)
                .add_modifier(Modifier::BOLD),
            ExecMode::Paper => Style::default()
                .fg(self.mode_paper)
                .add_modifier(Modifier::BOLD),
            ExecMode::Live => Style::default()
                .fg(self.mode_live)
                .bg(self.mode_live_bg)
                .add_modifier(Modifier::BOLD),
        }
    }

    pub fn banner_style(&self, mode: ExecMode) -> Style {
        match mode {
            ExecMode::Live => Style::default()
                .fg(self.mode_live)
                .bg(self.mode_live_bg)
                .add_modifier(Modifier::BOLD),
            other => Style::default()
                .fg(match other {
                    ExecMode::Shadow => self.mode_shadow,
                    ExecMode::Paper => self.mode_paper,
                    ExecMode::Live => self.mode_live,
                })
                .add_modifier(Modifier::BOLD),
        }
    }

    pub fn card_border(&self, focused: bool) -> Style {
        if focused {
            Style::default().fg(self.border_focus)
        } else {
            Style::default().fg(self.border)
        }
    }

    pub fn title_style(&self, focused: bool) -> Style {
        if focused {
            Style::default()
                .fg(self.border_focus)
                .add_modifier(Modifier::BOLD)
        } else {
            Style::default().fg(self.title)
        }
    }

    pub fn muted_style(&self) -> Style {
        Style::default().fg(self.muted)
    }

    pub fn fg_style(&self) -> Style {
        Style::default().fg(self.fg)
    }

    pub fn signed_style(&self, v: f64) -> Style {
        if v > 0.0 {
            Style::default().fg(self.positive)
        } else if v < 0.0 {
            Style::default().fg(self.negative)
        } else {
            Style::default().fg(self.muted)
        }
    }
}
