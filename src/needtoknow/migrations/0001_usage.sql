-- Counts per day: how many documents were checked, and how many items were found in them. Nothing else.
CREATE TABLE usage (
    day       TEXT PRIMARY KEY,           -- 2026-10-15 (UTC)
    documents INTEGER NOT NULL DEFAULT 0,
    items     INTEGER NOT NULL DEFAULT 0
);
