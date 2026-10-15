-- Contract: nothing has read or written the old table since v0.5.0, so it goes.
-- This cannot be undone by deploying an older image. v0.3.0 and v0.4.0 write this table and will fail to count.
DROP TABLE usage;
