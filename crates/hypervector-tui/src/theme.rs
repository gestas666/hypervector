//! Theme module for Quant TA & Microstructure Regime Detector Cockpit.

use ratatui::style::{Color, Modifier, Style};

#[derive(Debug, Clone)]
pub struct CockpitTheme {
    pub bg: Color,
    pub border: Style,
    pub border_active: Style,
    pub title: Style,
    pub header: Style,
    pub bull: Style,
    pub bear: Style,
    pub coiling: Style,
    pub carry: Style,
    pub chop: Style,
    pub muted: Style,
    pub gold: Style,
    pub cyan: Style,
    pub highlight: Style,
}

impl Default for CockpitTheme {
    fn default() -> Self {
        Self {
            bg: Color::Reset,
            border: Style::default().fg(Color::Rgb(110, 140, 185)),
            border_active: Style::default().fg(Color::Rgb(0, 240, 255)).add_modifier(Modifier::BOLD),
            title: Style::default().fg(Color::Rgb(0, 240, 255)).add_modifier(Modifier::BOLD),
            header: Style::default().fg(Color::Rgb(255, 255, 255)).bg(Color::Rgb(25, 38, 65)).add_modifier(Modifier::BOLD),
            bull: Style::default().fg(Color::Rgb(0, 255, 128)).add_modifier(Modifier::BOLD),
            bear: Style::default().fg(Color::Rgb(255, 45, 85)).add_modifier(Modifier::BOLD),
            coiling: Style::default().fg(Color::Rgb(255, 200, 0)).add_modifier(Modifier::BOLD),
            carry: Style::default().fg(Color::Rgb(190, 80, 255)).add_modifier(Modifier::BOLD),
            chop: Style::default().fg(Color::Rgb(190, 205, 225)).add_modifier(Modifier::BOLD),
            muted: Style::default().fg(Color::Rgb(180, 195, 215)),
            gold: Style::default().fg(Color::Rgb(255, 215, 0)).add_modifier(Modifier::BOLD),
            cyan: Style::default().fg(Color::Rgb(0, 240, 255)).add_modifier(Modifier::BOLD),
            highlight: Style::default().fg(Color::Rgb(255, 255, 255)).bg(Color::Rgb(0, 120, 210)).add_modifier(Modifier::BOLD),
        }
    }
}
