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
    // Hypervelocity gradient zone colors
    pub zone_danger: Style,
    pub zone_warming: Style,
    pub zone_building: Style,
    pub zone_target: Style,
    pub zone_climax: Style,
    pub bar_ghost: Style,
    pub bar_neutral: Style,
    pub depth_bid: Style,
    pub depth_ask: Style,
    pub gate_blocked: Style,
}

impl Default for CockpitTheme {
    fn default() -> Self {
        Self {
            bg: Color::Reset,
            border: colored(110, 140, 185),
            border_active: accented(0, 240, 255),
            title: accented(0, 240, 255),
            header: header_style(),
            bull: accented(0, 255, 128),
            bear: accented(255, 45, 85),
            coiling: accented(255, 200, 0),
            carry: accented(190, 80, 255),
            chop: accented(190, 205, 225),
            muted: colored(180, 195, 215),
            gold: accented(255, 215, 0),
            cyan: accented(0, 240, 255),
            highlight: highlight_style(),
            zone_danger: colored(255, 60, 60),
            zone_warming: colored(255, 170, 40),
            zone_building: colored(80, 220, 80),
            zone_target: accented(255, 215, 0),
            zone_climax: accented(100, 255, 255),
            bar_ghost: colored(100, 120, 140),
            bar_neutral: colored(140, 150, 165),
            depth_bid: colored(0, 200, 100),
            depth_ask: colored(220, 50, 70),
            gate_blocked: accented(255, 80, 80),
        }
    }
}

fn colored(red: u8, green: u8, blue: u8) -> Style {
    Style::default().fg(Color::Rgb(red, green, blue))
}

fn accented(red: u8, green: u8, blue: u8) -> Style {
    colored(red, green, blue).add_modifier(Modifier::BOLD)
}

fn header_style() -> Style {
    colored(105, 214, 235)
        .bg(Color::Rgb(9, 19, 33))
        .add_modifier(Modifier::BOLD)
}

fn highlight_style() -> Style {
    colored(118, 224, 242)
        .bg(Color::Rgb(10, 25, 42))
        .add_modifier(Modifier::BOLD)
}
