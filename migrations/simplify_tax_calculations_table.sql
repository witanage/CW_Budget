-- ============================================================
-- Migration: Simplify tax_calculations table (store input data only)
-- Purpose: Remove calculated fields and normalize to store only income data
-- Date: 2025-11-20
-- ============================================================

-- Drop calculated columns that are no longer needed
-- Calculations will be computed on-the-fly when loading data

ALTER TABLE tax_calculations
DROP COLUMN IF EXISTS monthly_salary_usd,
DROP COLUMN IF EXISTS total_annual_income,
DROP COLUMN IF EXISTS total_tax_liability,
DROP COLUMN IF EXISTS effective_tax_rate;

-- Drop the tax_calculation_details table if it exists
-- This table stored calculated results which we no longer need
DROP TABLE IF EXISTS tax_calculation_details;

-- Verify the changes
SELECT 'Migration completed! tax_calculations table now stores only income input data.' AS status;
SHOW CREATE TABLE tax_calculations;
