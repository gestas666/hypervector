use std::cell::RefCell;
use std::collections::VecDeque;
use std::io;
use std::time::Duration;

use hypervector_tui::terminal_input::{
    LIVE_INPUT_BATCH_LIMIT, SHUTDOWN_INPUT_DRAIN_LIMIT, drain_ready_events,
};

#[test]
fn live_batch_consumes_a_mouse_flood_before_the_next_render() {
    let events = RefCell::new((0..600).collect::<VecDeque<_>>());
    let timeouts = RefCell::new(Vec::new());
    let handled = RefCell::new(Vec::new());

    let count = drain_ready_events(
        Duration::from_secs(2),
        LIVE_INPUT_BATCH_LIMIT,
        |timeout| {
            timeouts.borrow_mut().push(timeout);
            Ok(!events.borrow().is_empty())
        },
        || {
            events
                .borrow_mut()
                .pop_front()
                .ok_or(io::ErrorKind::UnexpectedEof.into())
        },
        |event| {
            handled.borrow_mut().push(event);
            false
        },
    )
    .expect("mouse flood should be readable");

    assert_eq!(count, 600);
    assert_eq!(handled.borrow().len(), 600);
    assert_eq!(timeouts.borrow()[0], Duration::from_secs(2));
    assert!(timeouts.borrow()[1..].iter().all(Duration::is_zero));
}

#[test]
fn shutdown_drain_clears_more_than_the_old_256_event_limit() {
    let events = RefCell::new((0..600).collect::<VecDeque<_>>());

    let count = drain_ready_events(
        Duration::ZERO,
        SHUTDOWN_INPUT_DRAIN_LIMIT,
        |_| Ok(!events.borrow().is_empty()),
        || {
            events
                .borrow_mut()
                .pop_front()
                .ok_or(io::ErrorKind::UnexpectedEof.into())
        },
        |_| false,
    )
    .expect("shutdown queue should be readable");

    assert_eq!(count, 600);
    assert!(events.borrow().is_empty());
}

#[test]
fn batch_stops_immediately_when_handler_requests_exit() {
    let events = RefCell::new(VecDeque::from([1, 2, 3]));

    let count = drain_ready_events(
        Duration::ZERO,
        LIVE_INPUT_BATCH_LIMIT,
        |_| Ok(!events.borrow().is_empty()),
        || {
            events
                .borrow_mut()
                .pop_front()
                .ok_or(io::ErrorKind::UnexpectedEof.into())
        },
        |event| event == 1,
    )
    .expect("quit event should be readable");

    assert_eq!(count, 1);
    assert_eq!(events.borrow().len(), 2);
}
