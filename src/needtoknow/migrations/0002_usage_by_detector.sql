-- Expand: counts per day AND detector, so we can compare detectors after we switch.
-- SQLite cannot change a table's primary key, so this is a new table. The old one stays (and v0.3.0, which writes
-- it, keeps working) until a later release drops it.
CREATE TABLE usage_by_detector (
    day       TEXT NOT NULL,
    detector  TEXT NOT NULL,
    documents INTEGER NOT NULL DEFAULT 0,
    items     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, detector)
);

-- Copy what we have. Everything counted so far was found by the regex detector, the only one we have deployed.
INSERT INTO usage_by_detector (day, detector, documents, items)
SELECT day, 'regex', documents, items FROM usage;
