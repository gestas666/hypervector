//! App state, two-view navigation, refresh loop helpers.

use std::path::PathBuf;
use std::time::{Duration, Instant};

use crossterm::event::{self, Event, KeyCode, KeyEvent, KeyEventKind, KeyModifiers};
use ratatui::widgets::TableState;
use ratatui::DefaultTerminal;

use crate::cli_args::{CliArgs, TapeMode};
use crate::model::{
    AppSnapshot, CardId, GatesSnapshot, RegimeSnapshot, StatusSnapshot,
};
use crate::read::{
    load_decision_rows, load_fixture_json, probe_json, resolve_tape_path,
};
use crate::theme::Theme;
use crate::ui::{effects, render_floor, render_focus};

/// At most two views (SRS_HV5_TWO_VIEWS).
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum View {
    Floor,
    Focus { card: CardId },
}

pub struct App {
    pub args: CliArgs,
    pub snap: AppSnapshot,
    pub theme: Theme,
    pub view: View,
    pub focus_card: CardId,
    pub tape_state: TableState,
    pub show_help: bool,
    pub show_toast: Option<(String, Instant)>,
    pub should_quit: bool,
    pub last_refresh: Instant,
    pub last_regime: Instant,
    python: Option<PathBuf>,
}

impl App {
    pub fn new(args: CliArgs) -> Self {
        let theme = Theme::detect();
        let snap = AppSnapshot::cold(args.data_root.clone(), args.tape);
        let python = args.python.clone();
        let mut app = Self {
            args,
            snap,
            theme,
            view: View::Floor,
            focus_card: CardId::Gates,
            tape_state: TableState::default(),
            show_help: false,
            show_toast: None,
            should_quit: false,
            last_refresh: Instant::now() - Duration::from_secs(3600),
            last_regime: Instant::now() - Duration::from_secs(3600),
            python,
        };
        app.refresh_all(true);
        app
    }

    pub fn run(mut self, terminal: &mut DefaultTerminal) -> color_eyre::Result<()> {
        let refresh = Duration::from_millis(self.args.refresh_ms.max(200));
        let regime_every = Duration::from_secs(60);

        while !self.should_quit {
            terminal.draw(|frame| self.draw(frame))?;

            let timeout = refresh
                .checked_sub(self.last_refresh.elapsed())
                .unwrap_or(Duration::from_millis(16));

            if event::poll(timeout)? {
                if let Event::Key(key) = event::read()? {
                    // Crossterm may emit Press+Release; handle Press only.
                    if key.kind == KeyEventKind::Press || key.kind == KeyEventKind::Repeat {
                        self.on_key(key);
                    }
                }
            }

            if self.last_refresh.elapsed() >= refresh {
                self.refresh_hot();
                self.last_refresh = Instant::now();
            }
            if self.last_regime.elapsed() >= regime_every {
                self.refresh_regime();
                self.last_regime = Instant::now();
            }

            // Expire toast after 4s.
            if let Some((_, t)) = &self.show_toast {
                if t.elapsed() > Duration::from_secs(4) {
                    self.show_toast = None;
                }
            }
        }
        Ok(())
    }

    fn draw(&mut self, frame: &mut ratatui::Frame) {
        let area = frame.area();
        match self.view {
            View::Floor => {
                if self.snap.health.first_load && self.snap.health.refreshing {
                    effects::render_skeleton(frame, area, &self.theme);
                } else {
                    render_floor(
                        frame,
                        area,
                        &self.snap,
                        &self.theme,
                        self.focus_card,
                        &mut self.tape_state,
                    );
                }
            }
            View::Focus { card } => {
                render_focus(
                    frame,
                    area,
                    &self.snap,
                    &self.theme,
                    card,
                    &mut self.tape_state,
                );
            }
        }
        if self.show_help {
            effects::render_help(frame, area, &self.theme);
        }
        if let Some((msg, _)) = &self.show_toast {
            effects::render_toast(frame, area, &self.theme, msg);
        }
    }

    fn on_key(&mut self, key: KeyEvent) {
        if key.code == KeyCode::Char('c') && key.modifiers.contains(KeyModifiers::CONTROL) {
            self.should_quit = true;
            return;
        }

        if self.show_help {
            if matches!(
                key.code,
                KeyCode::Esc | KeyCode::Char('?') | KeyCode::Char('q')
            ) {
                if key.code == KeyCode::Char('q') {
                    self.should_quit = true;
                } else {
                    self.show_help = false;
                }
            }
            return;
        }

        match key.code {
            KeyCode::Char('q') => self.should_quit = true,
            KeyCode::Char('?') => self.show_help = true,
            KeyCode::Esc => {
                if matches!(self.view, View::Focus { .. }) {
                    self.view = View::Floor;
                }
            }
            KeyCode::Enter => {
                if matches!(self.view, View::Floor) {
                    self.view = View::Focus {
                        card: self.focus_card,
                    };
                }
            }
            KeyCode::Tab | KeyCode::Right | KeyCode::Down => {
                if matches!(self.view, View::Floor) {
                    self.focus_card = self.focus_card.next();
                } else if let View::Focus { card } = self.view {
                    // Scroll tape in focus
                    if card == CardId::Tape {
                        self.tape_select_delta(1);
                    }
                }
            }
            KeyCode::BackTab | KeyCode::Left | KeyCode::Up => {
                if matches!(self.view, View::Floor) {
                    self.focus_card = self.focus_card.prev();
                } else if let View::Focus { card } = self.view {
                    if card == CardId::Tape {
                        self.tape_select_delta(-1);
                    }
                }
            }
            KeyCode::Char('r') => {
                self.refresh_all(false);
            }
            KeyCode::Char('R') => {
                self.refresh_regime();
            }
            KeyCode::Char('p') => {
                self.args.tape = TapeMode::Paper;
                self.snap.tape_mode = TapeMode::Paper;
                self.refresh_tape();
            }
            KeyCode::Char('l') => {
                self.args.tape = TapeMode::Live;
                self.snap.tape_mode = TapeMode::Live;
                self.refresh_tape();
            }
            KeyCode::Char('a') => {
                self.args.tape = TapeMode::Auto;
                self.snap.tape_mode = TapeMode::Auto;
                self.refresh_tape();
            }
            _ => {}
        }
    }

    fn tape_select_delta(&mut self, delta: i32) {
        let n = self.snap.decisions.len();
        if n == 0 {
            return;
        }
        let cur = self.tape_state.selected().unwrap_or(0) as i32;
        let next = (cur + delta).clamp(0, (n as i32) - 1) as usize;
        self.tape_state.select(Some(next));
    }

    pub fn refresh_all(&mut self, first: bool) {
        self.snap.health.refreshing = true;
        self.refresh_status_gates();
        self.refresh_tape();
        if first {
            self.refresh_regime();
        }
        self.snap.health.refreshing = false;
        self.snap.health.first_load = false;
        self.snap.health.refreshed_at = Instant::now();
        self.last_refresh = Instant::now();
    }

    fn refresh_hot(&mut self) {
        self.refresh_tape();
        // Lightweight: re-probe status less often — every 5th hot tick via age.
        if self.snap.health.age_secs() >= 3 {
            self.refresh_status_gates();
            self.snap.health.refreshed_at = Instant::now();
        }
    }

    fn refresh_status_gates(&mut self) {
        // Fixtures for offline demos / tests.
        if let Some(ref p) = self.args.fixture_status {
            match load_fixture_json(p) {
                Ok(v) => match StatusSnapshot::from_value(&v) {
                    Ok(s) => {
                        self.snap.health.paper_no_submit = s.paper.no_submit;
                        self.snap.health.live_fail_closed = s.honesty.live_run_fail_closed;
                        self.snap.health.secrets_never_printed =
                            s.honesty.secret_values_never_printed;
                        self.snap.status = s;
                    }
                    Err(e) => self.toast(format!("status parse: {e}")),
                },
                Err(e) => self.toast(format!("status fixture: {e}")),
            }
        } else {
            match probe_json(
                "status",
                &self.args.data_root,
                self.python.as_deref(),
                &[],
                Duration::from_secs(15),
            ) {
                Ok(v) => match StatusSnapshot::from_value(&v) {
                    Ok(s) => {
                        self.snap.health.paper_no_submit = s.paper.no_submit;
                        self.snap.health.live_fail_closed = s.honesty.live_run_fail_closed;
                        self.snap.health.secrets_never_printed =
                            s.honesty.secret_values_never_printed;
                        self.snap.status = s;
                    }
                    Err(e) => self.toast(format!("status parse: {e}")),
                },
                Err(e) => {
                    // Soft failure — keep previous; toast once.
                    self.toast(format!("status: {e}"));
                }
            }
        }

        let mut gates = GatesSnapshot::default();
        if let Some(ref p) = self.args.fixture_paper_check {
            if let Ok(v) = load_fixture_json(p) {
                gates = GatesSnapshot::from_paper_check(&v);
            }
        } else if let Ok(v) = probe_json(
            "paper-check",
            &self.args.data_root,
            self.python.as_deref(),
            &[],
            Duration::from_secs(15),
        ) {
            gates = GatesSnapshot::from_paper_check(&v);
        }

        if let Some(ref p) = self.args.fixture_live_check {
            if let Ok(v) = load_fixture_json(p) {
                gates.merge_live_check(&v);
            }
        } else if let Ok(v) = probe_json(
            "live-check",
            &self.args.data_root,
            self.python.as_deref(),
            &[],
            Duration::from_secs(15),
        ) {
            gates.merge_live_check(&v);
        }

        // Layout existence from filesystem.
        let paper_dec = self.args.data_root.join("paper").join("decisions");
        gates.layout_ok = paper_dec.is_dir() || self.args.data_root.join("paper").is_dir();
        self.snap.gates = gates;
        self.snap.recompute_mode();
    }

    fn refresh_tape(&mut self) {
        match resolve_tape_path(&self.args.data_root, self.args.tape) {
            Ok((source, path)) => {
                self.snap.tape_source = source;
                self.snap.tape_path = Some(path.clone());
                match load_decision_rows(&path, 200) {
                    Ok(rows) => {
                        self.snap.decisions = rows;
                        self.snap.recompute_tape_agg();
                        self.snap.recompute_mode();
                        if self.tape_state.selected().is_none() && !self.snap.decisions.is_empty()
                        {
                            self.tape_state.select(Some(0));
                        }
                    }
                    Err(e) => self.toast(format!("tape: {e}")),
                }
            }
            Err(e) => self.toast(format!("tape path: {e}")),
        }
    }

    fn refresh_regime(&mut self) {
        self.snap.health.regime_refreshing = true;
        if let Some(ref p) = self.args.fixture_regime {
            match load_fixture_json(p) {
                Ok(v) => {
                    let mut r = RegimeSnapshot::from_regime_json(&v);
                    r.age_secs = Some(0);
                    self.snap.regime = r;
                }
                Err(e) => self.toast(format!("regime fixture: {e}")),
            }
            self.snap.health.regime_refreshing = false;
            return;
        }

        match probe_json(
            "regime",
            &self.args.data_root,
            self.python.as_deref(),
            &[],
            Duration::from_secs(90),
        ) {
            Ok(v) => {
                let mut r = RegimeSnapshot::from_regime_json(&v);
                r.age_secs = Some(0);
                self.snap.regime = r;
                self.snap.health.clear_error();
            }
            Err(e) => {
                // Keep previous metrics on failure.
                self.toast(format!("regime: {e}"));
            }
        }
        self.snap.health.regime_refreshing = false;
        self.last_regime = Instant::now();
    }

    fn toast(&mut self, msg: impl Into<String>) {
        let mut h = crate::model::HealthSnapshot::default();
        h.set_error(msg);
        let msg = h.last_error.unwrap_or_else(|| "error".into());
        self.snap.health.set_error(msg.clone());
        self.show_toast = Some((msg, Instant::now()));
    }
}

/// Ensure View has only two variants (compile-time shape for SRS).
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_two_views() {
        let floor = View::Floor;
        let focus = View::Focus {
            card: CardId::Tape,
        };
        assert_ne!(floor, focus);
        // Exhaustive match must compile with only two arms.
        match floor {
            View::Floor => {}
            View::Focus { .. } => panic!("unexpected"),
        }
    }

    #[test]
    fn card_cycle_wraps() {
        let mut c = CardId::Mode;
        for _ in 0..CardId::ALL.len() {
            c = c.next();
        }
        assert_eq!(c, CardId::Mode);
    }
}
