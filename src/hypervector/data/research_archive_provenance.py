"""Schema contract for exact research-archive market-family provenance."""

ARCHIVE_PROVENANCE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS archive_bundle_provenance (
    bundle_id VARCHAR PRIMARY KEY,
    market_family VARCHAR NOT NULL,
    book_only BOOLEAN NOT NULL,
    book_source VARCHAR NOT NULL,
    CHECK (market_family IN ('core', 'hip3'))
);
"""

LEGACY_ARCHIVE_PROVENANCE_SQL = """
INSERT INTO archive_bundle_provenance
SELECT
    bundles.bundle_id,
    'core',
    false,
    '0xarchive_hyperliquid_native_l2'
FROM archive_bundles AS bundles
LEFT JOIN archive_bundle_provenance AS provenance USING (bundle_id)
WHERE provenance.bundle_id IS NULL;
"""
