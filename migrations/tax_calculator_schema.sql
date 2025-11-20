-- ============================================================
-- Tax Calculator Schema - Complete Table Definition
-- ============================================================
-- This script creates the tax_calculations table with all necessary columns
-- Run this on your database to set up the tax calculator feature
-- ============================================================

-- Drop existing table if you want a fresh start (WARNING: This deletes all data!)
-- DROP TABLE IF EXISTS tax_calculations;

-- Create tax_calculations table
CREATE TABLE IF NOT EXISTS tax_calculations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    calculation_name VARCHAR(255) NOT NULL,
    assessment_year VARCHAR(20) NOT NULL,
    tax_rate DECIMAL(5, 2) NOT NULL,
    tax_free_threshold DECIMAL(15, 2) NOT NULL,
    start_month INT NOT NULL COMMENT '0=April, 11=March',
    monthly_data JSON NOT NULL COMMENT 'Income details: array of 12 months with salaries, exchange rates and bonuses',
    is_active BOOLEAN DEFAULT FALSE COMMENT 'Indicates if this is the active calculation for the assessment year',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_assessment_year (assessment_year),
    INDEX idx_created_at (created_at),
    INDEX idx_user_assessment_active (user_id, assessment_year, is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Stores only income input data - tax calculations are computed on-the-fly';

-- For existing installations that need to migrate from old schema:
-- Run these ALTER TABLE commands if the table already exists

-- Add is_active column if it doesn't exist
ALTER TABLE tax_calculations
ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT FALSE
COMMENT 'Indicates if this is the active calculation for the assessment year';

-- Add monthly_data column if it doesn't exist
ALTER TABLE tax_calculations
ADD COLUMN IF NOT EXISTS monthly_data JSON
COMMENT 'Income details: array of 12 months with salaries, exchange rates and bonuses';

-- Drop old calculated columns if they exist
ALTER TABLE tax_calculations
DROP COLUMN IF EXISTS monthly_salary_usd,
DROP COLUMN IF EXISTS total_annual_income,
DROP COLUMN IF EXISTS total_tax_liability,
DROP COLUMN IF EXISTS effective_tax_rate;

-- Create index for better query performance
CREATE INDEX IF NOT EXISTS idx_user_assessment_active
ON tax_calculations(user_id, assessment_year, is_active);

-- Drop deprecated table if it exists
DROP TABLE IF EXISTS tax_calculation_details;

-- Verification
SELECT 'Tax calculator schema updated successfully!' AS status;
SHOW CREATE TABLE tax_calculations;
