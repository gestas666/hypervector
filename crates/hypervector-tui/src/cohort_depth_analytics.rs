//! Dense snapshot-derived order-book analytics for the cohort depth screen.

use ratatui::{
    Frame,
    layout::{Constraint, Layout, Rect},
    text::{Line, Span},
    widgets::Paragraph,
};

use crate::app::App;
use crate::backend_cohort::{CohortBookLevel, CohortBookSnapshot};
use crate::cohort_widgets::panel;

const SWEEP_NOTIONALS_USD: [f64; 7] = [25.0, 50.0, 100.0, 250.0, 500.0, 1_000.0, 2_500.0];

#[derive(Debug, Clone, Copy)]
struct SweepEstimate {
    impact_bps: f64,
    coverage: f64,
    complete: bool,
}

#[derive(Debug, Clone, Copy)]
struct WallMetric<'a> {
    level: usize,
    value: &'a CohortBookLevel,
    side_share: f64,
    distance_bps: f64,
}

/// Render multi-level pressure, executable impact, and liquidity concentration.
pub(crate) fn render(frame: &mut Frame, app: &App, area: Rect, book: &CohortBookSnapshot) {
    let columns = Layout::horizontal([
        Constraint::Ratio(34, 100),
        Constraint::Length(1),
        Constraint::Ratio(39, 100),
        Constraint::Length(1),
        Constraint::Ratio(27, 100),
    ])
    .split(area);
    render_imbalance_curve(frame, app, columns[0], book);
    render_sweep_cost(frame, app, columns[2], book);
    render_concentration(frame, app, columns[4], book);
}

/// Render a wide lower deck as two balanced rows instead of narrow vertical strips.
pub(crate) fn render_balanced(frame: &mut Frame, app: &App, area: Rect, book: &CohortBookSnapshot) {
    let rows = Layout::vertical([
        Constraint::Ratio(1, 2),
        Constraint::Length(1),
        Constraint::Ratio(1, 2),
    ])
    .split(area);
    let upper = Layout::horizontal([
        Constraint::Ratio(1, 2),
        Constraint::Length(2),
        Constraint::Ratio(1, 2),
    ])
    .split(rows[0]);
    let lower = Layout::horizontal([
        Constraint::Ratio(1, 2),
        Constraint::Length(2),
        Constraint::Ratio(1, 2),
    ])
    .split(rows[2]);
    render_imbalance_curve(frame, app, upper[0], book);
    render_sweep_cost(frame, app, upper[2], book);
    render_concentration(frame, app, lower[0], book);
    crate::cohort_hip3_roster::render(frame, app, lower[2]);
}

fn render_imbalance_curve(frame: &mut Frame, app: &App, area: Rect, book: &CohortBookSnapshot) {
    let block = panel(" IMBALANCE CURVE // MULTI-LEVEL ", app);
    let inner = block.inner(area);
    frame.render_widget(block, area);
    let maximum_levels = book.bids.len().max(book.asks.len());
    let group_capacity = usize::from(inner.height / 3).max(1);
    let checkpoints = selected_checkpoints(maximum_levels, group_capacity);
    let width = usize::from(inner.width.saturating_sub(9) / 2).max(2);
    let mut lines = Vec::with_capacity(checkpoints.len() * 3);
    for level in checkpoints {
        let bid = cumulative_size(&book.bids, level);
        let ask = cumulative_size(&book.asks, level);
        let imbalance = normalized_difference(bid, ask);
        lines.push(Line::from(format!(
            "L{level:02}  I {imbalance:+.3}  B {bid:.4} / A {ask:.4}"
        )));
        let band = paired_depth_band(app, bid, ask, width);
        lines.push(band.clone());
        lines.push(band);
    }
    frame.render_widget(Paragraph::new(lines), inner);
}

fn render_sweep_cost(frame: &mut Frame, app: &App, area: Rect, book: &CohortBookSnapshot) {
    let block = panel(" VISIBLE SWEEP COST // BOOK-LIMITED ", app);
    let inner = block.inner(area);
    frame.render_widget(block, area);
    let bid_notional = visible_notional(&book.bids);
    let ask_notional = visible_notional(&book.asks);
    let mut lines = vec![Line::from(format!(
        "VISIBLE  BID ${bid_notional:.0} / ASK ${ask_notional:.0}"
    ))];
    let fixed_rows = 3_usize;
    let capacity = usize::from(inner.height).saturating_sub(fixed_rows);
    for target in SWEEP_NOTIONALS_USD.iter().take(capacity) {
        let buy = sweep_estimate(&book.asks, book.mid_px, *target, true);
        let sell = sweep_estimate(&book.bids, book.mid_px, *target, false);
        lines.push(Line::from(format!(
            "${target:<4.0} {}  {}",
            format_sweep("BUY", buy),
            format_sweep("SELL", sell),
        )));
    }
    lines.push(position_exit_line(app, book));
    lines.push(Line::from(Span::styled(
        "COV = visible levels; no extrapolation",
        app.theme.muted,
    )));
    frame.render_widget(Paragraph::new(lines), inner);
}

fn render_concentration(frame: &mut Frame, app: &App, area: Rect, book: &CohortBookSnapshot) {
    let block = panel(" LIQUIDITY CONCENTRATION ", app);
    let inner = block.inner(area);
    frame.render_widget(block, area);
    let bid_total = total_size(&book.bids);
    let ask_total = total_size(&book.asks);
    let bid_wall = wall_metric(&book.bids, book.mid_px, bid_total);
    let ask_wall = wall_metric(&book.asks, book.mid_px, ask_total);
    let microprice = microprice(book);
    let micro_delta = ((microprice / book.mid_px) - 1.0) * 10_000.0;
    if inner.height <= 5 {
        frame.render_widget(
            Paragraph::new(compact_concentration_lines(
                app,
                book,
                bid_wall,
                ask_wall,
                microprice,
                micro_delta,
            )),
            inner,
        );
        return;
    }
    let mut lines = vec![
        Line::from(format!("BID/ASK RATIO {:.3}", book.bid_depth_ratio)),
        Line::from(format!("ORDER PRESSURE OPI {:+.3}", book.opi)),
        Line::from(format!("MICROPRICE {microprice:.6} Δ{micro_delta:+.3}bps")),
        Line::from(format!(
            "TOP1 SHARE B{:.1}% / A{:.1}%",
            book.bids[0].size / bid_total * 100.0,
            book.asks[0].size / ask_total * 100.0,
        )),
        wall_line("B", bid_wall),
        wall_line("A", ask_wall),
        Line::from(format!("TOTAL ORDERS {}", order_counts(book))),
        Line::from(format!(
            "REACH B{:.2} / A{:.2}bps",
            farthest_distance_bps(&book.bids, book.mid_px),
            farthest_distance_bps(&book.asks, book.mid_px),
        )),
        Line::from(Span::styled(
            "PRESSURE IS TELEMETRY // NO GATE",
            app.theme.muted,
        )),
    ];
    let remaining = usize::from(inner.height).saturating_sub(lines.len());
    lines.extend(level_map_lines(app, book, inner.width, remaining));
    frame.render_widget(Paragraph::new(lines), inner);
}

fn compact_concentration_lines(
    app: &App,
    book: &CohortBookSnapshot,
    bid_wall: WallMetric<'_>,
    ask_wall: WallMetric<'_>,
    microprice: f64,
    micro_delta: f64,
) -> Vec<Line<'static>> {
    vec![
        Line::from(format!(
            "BID/ASK RATIO {:.3} // ORDER PRESSURE OPI {:+.3}",
            book.bid_depth_ratio, book.opi,
        )),
        Line::from(format!("MICROPRICE {microprice:.6} Δ{micro_delta:+.3}bps")),
        Line::from(format!(
            "TOP1 SHARE B{:.1}% / A{:.1}%",
            book.bids[0].size / total_size(&book.bids) * 100.0,
            book.asks[0].size / total_size(&book.asks) * 100.0,
        )),
        Line::from(format!(
            "WALLS B L{:02} {:.3}/{:.2}bps // A L{:02} {:.3}/{:.2}bps",
            bid_wall.level,
            bid_wall.value.size,
            bid_wall.distance_bps,
            ask_wall.level,
            ask_wall.value.size,
            ask_wall.distance_bps,
        )),
        Line::from(vec![
            Span::raw(format!("TOTAL ORDERS {} // ", order_counts(book))),
            Span::styled("PRESSURE IS TELEMETRY", app.theme.muted),
        ]),
    ]
}

fn selected_checkpoints(maximum: usize, capacity: usize) -> Vec<usize> {
    if maximum <= capacity {
        return (1..=maximum).collect();
    }
    if capacity == 1 {
        return vec![maximum];
    }
    (0..capacity)
        .map(|index| 1 + (index * maximum.saturating_sub(1) + (capacity - 1) / 2) / (capacity - 1))
        .collect()
}

fn paired_depth_band(app: &App, bid: f64, ask: f64, width: usize) -> Line<'static> {
    let maximum = bid.max(ask);
    Line::from(vec![
        Span::styled("B ", app.theme.depth_bid),
        Span::styled(depth_bar(bid, maximum, width), app.theme.depth_bid),
        Span::raw(" │ "),
        Span::styled("A ", app.theme.depth_ask),
        Span::styled(depth_bar(ask, maximum, width), app.theme.depth_ask),
    ])
}

fn level_map_lines(
    app: &App,
    book: &CohortBookSnapshot,
    area_width: u16,
    capacity: usize,
) -> Vec<Line<'static>> {
    if capacity == 0 {
        return Vec::new();
    }
    let count = book.bids.len().max(book.asks.len()).min(capacity);
    let maximum = book
        .bids
        .iter()
        .chain(&book.asks)
        .map(|level| level.size)
        .fold(0.0_f64, f64::max);
    let width = usize::from(area_width.saturating_sub(14) / 2).max(1);
    (0..count)
        .map(|index| {
            let bid = book.bids.get(index).map_or(0.0, |level| level.size);
            let ask = book.asks.get(index).map_or(0.0, |level| level.size);
            Line::from(vec![
                Span::raw(format!("L{:02} ", index + 1)),
                Span::styled(depth_bar(bid, maximum, width), app.theme.depth_bid),
                Span::raw(" │ "),
                Span::styled(depth_bar(ask, maximum, width), app.theme.depth_ask),
            ])
        })
        .collect()
}

fn position_exit_line(app: &App, book: &CohortBookSnapshot) -> Line<'static> {
    let Some(asset) = app
        .backend
        .cohort
        .assets
        .iter()
        .find(|asset| asset.symbol == book.symbol)
    else {
        return Line::from("OPEN EXIT N/A");
    };
    let Some(side) = asset.position_side.as_deref() else {
        return Line::from("OPEN EXIT FLAT");
    };
    let target = asset.position_size_signed.abs() * book.mid_px;
    let (label, estimate) = if side == "long" {
        (
            "SELL",
            sweep_estimate(&book.bids, book.mid_px, target, false),
        )
    } else {
        ("BUY", sweep_estimate(&book.asks, book.mid_px, target, true))
    };
    Line::from(format!(
        "OPEN EXIT ${target:.0}  {}",
        format_sweep(label, estimate)
    ))
}

fn sweep_estimate(
    levels: &[CohortBookLevel],
    mid_price: f64,
    target_notional: f64,
    buy: bool,
) -> SweepEstimate {
    if target_notional <= 0.0 {
        return SweepEstimate {
            impact_bps: 0.0,
            coverage: 1.0,
            complete: true,
        };
    }
    let mut remaining = target_notional;
    let mut notional = 0.0;
    let mut quantity = 0.0;
    for level in levels {
        let consumed = remaining.min(level.price * level.size);
        notional += consumed;
        quantity += consumed / level.price;
        remaining -= consumed;
        if remaining <= f64::EPSILON {
            break;
        }
    }
    let coverage = (notional / target_notional).clamp(0.0, 1.0);
    let vwap = if quantity > 0.0 {
        notional / quantity
    } else {
        mid_price
    };
    let impact_bps = if buy {
        (vwap / mid_price - 1.0) * 10_000.0
    } else {
        (1.0 - vwap / mid_price) * 10_000.0
    };
    SweepEstimate {
        impact_bps,
        coverage,
        complete: remaining <= f64::EPSILON,
    }
}

fn format_sweep(side: &str, estimate: SweepEstimate) -> String {
    if estimate.complete {
        format!("{side} {:+.3}bps", estimate.impact_bps)
    } else {
        format!("{side} COV{:.0}%", estimate.coverage * 100.0)
    }
}

fn wall_metric<'a>(levels: &'a [CohortBookLevel], mid_price: f64, total: f64) -> WallMetric<'a> {
    let (index, value) = levels
        .iter()
        .enumerate()
        .max_by(|left, right| left.1.size.total_cmp(&right.1.size))
        .expect("validated books contain at least one level");
    WallMetric {
        level: index + 1,
        value,
        side_share: value.size / total,
        distance_bps: (value.price / mid_price - 1.0).abs() * 10_000.0,
    }
}

fn wall_line(side: &str, wall: WallMetric<'_>) -> Line<'static> {
    Line::from(format!(
        "WALL {side} L{:02} {:.3} ({:.0}%) {:.2}bps",
        wall.level,
        wall.value.size,
        wall.side_share * 100.0,
        wall.distance_bps,
    ))
}

fn microprice(book: &CohortBookSnapshot) -> f64 {
    let bid = &book.bids[0];
    let ask = &book.asks[0];
    (ask.price * bid.size + bid.price * ask.size) / (bid.size + ask.size)
}

fn order_counts(book: &CohortBookSnapshot) -> String {
    let bids = book
        .bids
        .iter()
        .map(|level| level.orders)
        .sum::<Option<u64>>();
    let asks = book
        .asks
        .iter()
        .map(|level| level.orders)
        .sum::<Option<u64>>();
    match (bids, asks) {
        (Some(bid), Some(ask)) => format!("B{bid}/A{ask}"),
        _ => "B N/A/A N/A".into(),
    }
}

fn cumulative_size(levels: &[CohortBookLevel], count: usize) -> f64 {
    levels.iter().take(count).map(|level| level.size).sum()
}

fn total_size(levels: &[CohortBookLevel]) -> f64 {
    levels.iter().map(|level| level.size).sum()
}

fn visible_notional(levels: &[CohortBookLevel]) -> f64 {
    levels.iter().map(|level| level.price * level.size).sum()
}

fn normalized_difference(bid: f64, ask: f64) -> f64 {
    if bid + ask > 0.0 {
        (bid - ask) / (bid + ask)
    } else {
        0.0
    }
}

fn farthest_distance_bps(levels: &[CohortBookLevel], mid_price: f64) -> f64 {
    levels.last().map_or(0.0, |level| {
        (level.price / mid_price - 1.0).abs() * 10_000.0
    })
}

fn depth_bar(value: f64, maximum: f64, width: usize) -> String {
    let filled = if maximum <= 0.0 {
        0
    } else {
        ((value / maximum) * width as f64).round() as usize
    };
    format!(
        "{}{}",
        "█".repeat(filled.min(width)),
        "░".repeat(width.saturating_sub(filled)),
    )
}
