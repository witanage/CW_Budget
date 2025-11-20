-- ============================================================
-- Migration: Add is_active column to tax_calculations
-- Purpose: Support assessment year-wise data organization
-- Date: 2025-11-20
-- ============================================================

-- Add is_active column to track the current/active calculation per assessment year
ALTER TABLE tax_calculations
ADD COLUMN is_active BOOLEAN DEFAULT FALSE COMMENT 'Indicates if this is the active calculation for the assessment year';

-- Add index for efficient querying of active calculations
CREATE INDEX idx_user_assessment_active ON tax_calculations(user_id, assessment_year, is_active);

-- Note: We don't add a UNIQUE constraint on (user_id, assessment_year, is_active=TRUE)
-- because MySQL doesn't support partial unique indexes. Instead, we'll enforce this
-- constraint in the application logic.

-- Set the most recent calculation for each user/year combination as active
UPDATE tax_calculations t1
SET is_active = TRUE
WHERE id IN (
    SELECT id FROM (
        SELECT id,
               ROW_NUMBER() OVER (PARTITION BY user_id, assessment_year ORDER BY created_at DESC) as rn
        FROM tax_calculations
    ) t2
    WHERE t2.rn = 1
);
