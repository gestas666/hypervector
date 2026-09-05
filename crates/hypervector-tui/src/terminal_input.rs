//! Bounded terminal-input batching for responsive rendering and clean teardown.

use std::io;
use std::time::Duration;

/// Maximum ready events consumed before the TUI renders a new frame.
pub const LIVE_INPUT_BATCH_LIMIT: usize = 1_024;

/// Maximum queued events discarded after mouse reporting is disabled.
pub const SHUTDOWN_INPUT_DRAIN_LIMIT: usize = 16_384;

/// Consume one timed event and then all immediately ready events up to a bound.
pub fn drain_ready_events<T, Poll, Read, Handle>(
    initial_timeout: Duration,
    maximum_events: usize,
    mut poll: Poll,
    mut read: Read,
    mut handle: Handle,
) -> io::Result<usize>
where
    Poll: FnMut(Duration) -> io::Result<bool>,
    Read: FnMut() -> io::Result<T>,
    Handle: FnMut(T) -> bool,
{
    let mut consumed = 0;
    let mut timeout = initial_timeout;
    while consumed < maximum_events && poll(timeout)? {
        consumed += 1;
        if handle(read()?) {
            break;
        }
        timeout = Duration::ZERO;
    }
    Ok(consumed)
}
