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
            border: Style::default().fg(Color::Rgb(110, 140, 185)),
            border_active: Style::default()
                .fg(Color::Rgb(0, 240, 255))
                .add_modifier(Modifier::BOLD),
            title: Style::default()
                .fg(Color::Rgb(0, 240, 255))
                .add_modifier(Modifier::BOLD),
            header: Style::default()
                .fg(Color::Rgb(255, 255, 255))
                .bg(Color::Rgb(25, 38, 65))
                .add_modifier(Modifier::BOLD),
            bull: Style::default()
                .fg(Color::Rgb(0, 255, 128))
                .add_modifier(Modifier::BOLD),
            bear: Style::default()
                .fg(Color::Rgb(255, 45, 85))
                .add_modifier(Modifier::BOLD),
            coiling: Style::default()
                .fg(Color::Rgb(255, 200, 0))
                .add_modifier(Modifier::BOLD),
            carry: Style::default()
                .fg(Color::Rgb(190, 80, 255))
                .add_modifier(Modifier::BOLD),
            chop: Style::default()
                .fg(Color::Rgb(190, 205, 225))
                .add_modifier(Modifier::BOLD),
            muted: Style::default().fg(Color::Rgb(180, 195, 215)),
            gold: Style::default()
                .fg(Color::Rgb(255, 215, 0))
                .add_modifier(Modifier::BOLD),
            cyan: Style::default()
                .fg(Color::Rgb(0, 240, 255))
                .add_modifier(Modifier::BOLD),
            highlight: Style::default()
                .fg(Color::Rgb(255, 255, 255))
                .bg(Color::Rgb(0, 120, 210))
                .add_modifier(Modifier::BOLD),
            zone_danger: Style::default().fg(Color::Rgb(255, 60, 60)),
            zone_warming: Style::default().fg(Color::Rgb(255, 170, 40)),
            zone_building: Style::default().fg(Color::Rgb(80, 220, 80)),
            zone_target: Style::default()
                .fg(Color::Rgb(255, 215, 0))
                .add_modifier(Modifier::BOLD),
            zone_climax: Style::default()
                .fg(Color::Rgb(100, 255, 255))
                .add_modifier(Modifier::BOLD),
            bar_ghost: Style::default().fg(Color::Rgb(100, 120, 140)),
            bar_neutral: Style::default().fg(Color::Rgb(140, 150, 165)),
            depth_bid: Style::default().fg(Color::Rgb(0, 200, 100)),
            depth_ask: Style::default().fg(Color::Rgb(220, 50, 70)),
            gate_blocked: Style::default()
                .fg(Color::Rgb(255, 80, 80))
                .add_modifier(Modifier::BOLD),
        }
    }
}
