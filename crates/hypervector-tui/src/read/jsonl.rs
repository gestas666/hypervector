//! Tail-load decisions.jsonl (last N lines).

use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::Path;

use crate::model::DecisionRow;

/// Load up to `max_n` decision rows from the end of a JSONL file.
///
/// Missing file → empty vec (cold/empty state, not error).
pub fn load_decision_rows(path: &Path, max_n: usize) -> Result<Vec<DecisionRow>, std::io::Error> {
    if max_n == 0 {
        return Ok(Vec::new());
    }
    if !path.is_file() {
        return Ok(Vec::new());
    }

    let file = File::open(path)?;
    let meta = file.metadata()?;
    let size = meta.len();

    // Read a tail window large enough for ~max_n JSON lines (cap 2 MiB).
    let window = std::cmp::min(size, 2 * 1024 * 1024);
    let mut file = file;
    file.seek(SeekFrom::Start(size.saturating_sub(window)))?;
    let mut buf = String::new();
    file.read_to_string(&mut buf)?;

    // If we started mid-line, drop first partial line.
    let text = if size > window {
        buf.find('\n').map(|i| &buf[i + 1..]).unwrap_or(buf.as_str())
    } else {
        buf.as_str()
    };

    let mut rows: Vec<DecisionRow> = Vec::new();
    for line in text.lines() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        match serde_json::from_str::<DecisionRow>(line) {
            Ok(row) => rows.push(row),
            Err(_) => {
                // Skip corrupt lines; do not panic (ops terminal must stay up).
                continue;
            }
        }
    }

    if rows.len() > max_n {
        let skip = rows.len() - max_n;
        rows = rows.split_off(skip);
    }
    Ok(rows)
}



#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::tempdir;

    #[test]
    fn loads_last_n() {
        let dir = tempdir().unwrap();
        let p = dir.path().join("decisions.jsonl");
        let mut f = File::create(&p).unwrap();
        for i in 0..5 {
            writeln!(
                f,
                r#"{{"execution_mode":"shadow","action":"hold","submitted":false,"feed_ts":"{i}"}}"#
            )
            .unwrap();
        }
        let rows = load_decision_rows(&p, 3).unwrap();
        assert_eq!(rows.len(), 3);
        assert_eq!(rows[0].timestamp_display(), "2");
        assert_eq!(rows[2].timestamp_display(), "4");
    }

    #[test]
    fn missing_file_is_empty() {
        let rows = load_decision_rows(Path::new("/no/such/decisions.jsonl"), 10).unwrap();
        assert!(rows.is_empty());
    }
}
