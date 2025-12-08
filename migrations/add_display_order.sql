-- ============================================================
-- Migration: Add display_order column to transactions
-- ============================================================
-- This migration safely adds the display_order column and
-- initializes existing records to preserve their current order
-- ============================================================

-- Step 1: Add the display_order column if it doesn't exist
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS display_order INT NOT NULL DEFAULT 0
COMMENT 'Order for displaying transactions (lower numbers first)';

-- Step 2: Add index for display_order if it doesn't exist
ALTER TABLE transactions
ADD INDEX IF NOT EXISTS idx_display_order (display_order);

-- Step 3: Initialize display_order for existing records
-- This sets display_order based on the current ID order within each monthly_record
-- Records with display_order = 0 are considered uninitialized

SET @row_num = 0;
SET @current_monthly_record = 0;

UPDATE transactions t
JOIN (
    SELECT
        id,
        monthly_record_id,
        @row_num := IF(@current_monthly_record = monthly_record_id, @row_num + 1, 1) AS new_order,
        @current_monthly_record := monthly_record_id
    FROM transactions
    WHERE display_order = 0
    ORDER BY monthly_record_id, id
) AS ordered ON t.id = ordered.id
SET t.display_order = ordered.new_order
WHERE t.display_order = 0;

-- ============================================================
-- Verification Query (run manually to check):
-- SELECT monthly_record_id, id, display_order
-- FROM transactions
-- ORDER BY monthly_record_id, display_order;
-- ============================================================
