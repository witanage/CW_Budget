-- ============================================================
-- Migration: Enforce one token row per user
-- ============================================================
-- Deduplicates the tokens table (keeps the most recent row per
-- user) then adds a UNIQUE constraint on user_id so that future
-- logins hit ON DUPLICATE KEY UPDATE instead of inserting.
-- ============================================================

-- Step 1: Delete duplicate rows, keeping only the latest per user.
-- The nested subquery is required because MySQL does not allow a
-- DELETE to reference the same table in a plain subquery.
DELETE FROM tokens
WHERE id NOT IN (
    SELECT latest_id FROM (
        SELECT MAX(id) AS latest_id FROM tokens GROUP BY user_id
    ) AS keep
);

-- Step 2: Add the UNIQUE index and drop the old non-unique index in
-- a single ALTER TABLE.  The FK on user_id requires at least one
-- index to exist at all times; splitting into two statements causes
-- "Error 1553: Cannot drop index needed in a foreign key constraint".
ALTER TABLE tokens
    ADD UNIQUE INDEX idx_user_id_unique (user_id),
    DROP INDEX idx_user_id;

-- Step 3: Rename back to the original index name.
ALTER TABLE tokens RENAME INDEX idx_user_id_unique TO idx_user_id;

-- ============================================================
-- Verification Query (run manually to check):
-- SELECT user_id, COUNT(*) AS cnt FROM tokens GROUP BY user_id HAVING cnt > 1;
-- (should return zero rows)
-- ============================================================
