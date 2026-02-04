-- ============================================================
-- Migration: Remove location columns from transactions
-- ============================================================
-- Drops the six geolocation columns that were previously
-- captured when marking transactions as done or paid.
-- ============================================================

ALTER TABLE transactions
DROP COLUMN IF EXISTS done_latitude,
DROP COLUMN IF EXISTS done_longitude,
DROP COLUMN IF EXISTS done_location_accuracy,
DROP COLUMN IF EXISTS paid_latitude,
DROP COLUMN IF EXISTS paid_longitude,
DROP COLUMN IF EXISTS paid_location_accuracy;

-- ============================================================
-- Verification Query (run manually to check):
-- SHOW COLUMNS FROM transactions;
-- ============================================================
