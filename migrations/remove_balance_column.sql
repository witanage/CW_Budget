-- Migration: Remove balance column from transactions table
-- Balance is now calculated on frontend in real-time

-- Drop balance column from transactions table
ALTER TABLE transactions DROP COLUMN IF EXISTS balance;

-- Note: This is a destructive migration. Make sure you have a backup before running.
