//! Frame-count-driven animation primitives for the hypervelocity TUI screen.
//!
//! All functions are pure: they take `tick_count` and return values without
//! mutating state. This keeps the renderer deterministic and testable.

use ratatui::style::Color;

/// Sine-wave pulse: 0.0 → 1.0 → 0.0 over `period` ticks.
pub fn pulse(tick: u64, period: u64) -> f64 {
    if period == 0 {
        return 1.0;
    }
    let phase = (tick % period) as f64 / period as f64;
    (phase * std::f64::consts::PI * 2.0).sin().abs()
}

/// Exponential fade from 1.0 to 0.0 over `duration` ticks after `start_tick`.
pub fn spark_fade(tick: u64, start_tick: u64, duration: u64) -> f64 {
    if tick < start_tick {
        return 0.0;
    }
    let elapsed = tick - start_tick;
    if elapsed >= duration {
        return 0.0;
    }
    let t = elapsed as f64 / duration as f64;
    1.0 - t * t // quadratic ease-out
}

/// Slide-in animation: 0.3 → 0.6 → 1.0 over 3 frames after `start_tick`.
pub fn slide_in(tick: u64, start_tick: u64) -> f64 {
    if tick < start_tick {
        return 0.3;
    }
    let elapsed = tick - start_tick;
    if elapsed == 0 {
        0.3
    } else if elapsed == 1 {
        0.6
    } else {
        1.0
    }
}

/// Compute a color for a margin return zone, with optional pulse modulation.
///
/// Zones:
/// - 0-3%: danger (red)
/// - 3-6%: warming (amber)
/// - 6-7.5%: building (green)
/// - 7.5-8%: target (gold) with pulse
/// - >8%: climax (cyan/white hot)
pub fn gradient_color(margin_pct: f64, tick: u64) -> Color {
    let abs_margin = margin_pct.abs();
    let (r, g, b) = if abs_margin < 3.0 {
        // Red zone
        let t = (abs_margin / 3.0).clamp(0.0, 1.0);
        let r = (255.0 * (1.0 - t * 0.4)) as u8;
        let g = (60.0 * t) as u8;
        let b = (60.0 * t) as u8;
        (r, g, b)
    } else if abs_margin < 6.0 {
        // Amber zone
        let t = ((abs_margin - 3.0) / 3.0).clamp(0.0, 1.0);
        let r = 255u8;
        let g = (60.0 + 140.0 * t) as u8;
        let b = (60.0 * (1.0 - t)) as u8;
        (r, g, b)
    } else if abs_margin < 7.5 {
        // Green zone
        let t = ((abs_margin - 6.0) / 1.5).clamp(0.0, 1.0);
        let r = (255.0 * (1.0 - t)) as u8;
        let g = (200.0 + 20.0 * t) as u8;
        let b = (80.0 * (1.0 - t)) as u8;
        (r, g, b)
    } else if abs_margin < 8.0 {
        // Gold zone with pulse
        let pulse_val = pulse(tick, 8);
        let brightness = 0.85 + 0.15 * pulse_val;
        let r = (255.0 * brightness) as u8;
        let g = (215.0 * brightness) as u8;
        let b = ((1.0 - pulse_val) * 80.0) as u8;
        (r, g, b)
    } else {
        // Climax: cyan/white hot
        let r = 100u8;
        let g = 255u8;
        let b = 255u8;
        (r, g, b)
    };
    Color::Rgb(r, g, b)
}

/// Dim a color based on trade age. Older trades fade toward muted.
pub fn aged_color(base: Color, age: usize, max_age: usize) -> Color {
    let t = (age as f64 / max_age as f64).clamp(0.0, 1.0);
    let (br, bg, bb) = match base {
        Color::Rgb(r, g, b) => (r, g, b),
        _ => return base,
    };
    let factor = 1.0 - t * 0.7; // fade to 30% brightness
    Color::Rgb(
        (br as f64 * factor) as u8,
        (bg as f64 * factor) as u8,
        (bb as f64 * factor) as u8,
    )
}

/// Flash brightness multiplier for new liquidity at a depth level.
/// Starts at 1.5x, fades to 1.0x over 4 frames.
pub fn depth_flash(tick: u64, last_change_tick: u64) -> f64 {
    if last_change_tick == 0 || tick < last_change_tick {
        return 1.0;
    }
    let elapsed = tick - last_change_tick;
    if elapsed >= 4 {
        return 1.0;
    }
    1.0 + 0.5 * (1.0 - elapsed as f64 / 4.0)
}

/// Subtle micro-oscillation per level so the ladder feels alive even when static.
/// Amplitude: 5%. Each level has a staggered phase for visual variety.
pub fn bar_breath(tick: u64, level_index: usize) -> f64 {
    let phase_offset = level_index as f64 * 0.7;
    let t = (tick as f64 * 0.3 + phase_offset).sin();
    1.0 + t * 0.05
}
