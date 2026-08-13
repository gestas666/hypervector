//! Selected-coin scope for the regime screen's open-lifecycle panel.

/// Return open-lifecycle indexes with the selected coin first.
pub(crate) fn selected_open_indices<'a>(
    symbols: impl IntoIterator<Item = &'a str>,
    selected_symbol: Option<&str>,
) -> Vec<usize> {
    let indexed = symbols.into_iter().enumerate().collect::<Vec<_>>();
    let Some(selected) = selected_symbol else {
        return indexed.into_iter().map(|(index, _)| index).collect();
    };
    indexed
        .iter()
        .filter(|(_, symbol)| *symbol == selected)
        .chain(indexed.iter().filter(|(_, symbol)| *symbol != selected))
        .map(|(index, _)| *index)
        .collect()
}

#[cfg(test)]
mod tests {
    use super::selected_open_indices;

    #[test]
    fn selected_coin_leads_other_open_lifecycles() {
        let symbols = ["BTC", "HYPE"];

        assert_eq!(selected_open_indices(symbols, Some("HYPE")), vec![1, 0]);
    }

    #[test]
    fn flat_selected_coin_retains_available_open_lifecycles() {
        let symbols = ["BTC", "HYPE"];

        assert_eq!(selected_open_indices(symbols, Some("ETH")), vec![0, 1]);
    }
}
