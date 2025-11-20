-- ============================================================
-- Tax Calculator Tables - Add to existing database
-- ============================================================
-- Run this SQL script to add tax calculation tables
-- You can run this using your database management tool or CLI:
-- mysql -h ll206l.h.filess.io -P 3307 -u CWDB_typedozen -p CWDB_typedozen < tax_tables_schema.sql
-- ============================================================

-- Table: tax_calculations
-- Stores foreign employment income tax calculations for trend analysis
CREATE TABLE IF NOT EXISTS tax_calculations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    calculation_name VARCHAR(255) NOT NULL,
    assessment_year VARCHAR(20) NOT NULL,
    monthly_salary_usd DECIMAL(15, 2) NOT NULL,
    tax_rate DECIMAL(5, 2) NOT NULL,
    tax_free_threshold DECIMAL(15, 2) NOT NULL,
    start_month INT NOT NULL COMMENT '0=April, 11=March',
    monthly_data JSON NOT NULL COMMENT 'Array of 12 months with exchange rates and bonuses',
    total_annual_income DECIMAL(15, 2) NOT NULL,
    total_tax_liability DECIMAL(15, 2) NOT NULL,
    effective_tax_rate DECIMAL(5, 2) NOT NULL,
    is_active BOOLEAN DEFAULT FALSE COMMENT 'Indicates if this is the active calculation for the assessment year',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_assessment_year (assessment_year),
    INDEX idx_created_at (created_at),
    INDEX idx_user_assessment_active (user_id, assessment_year, is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: tax_calculation_details
-- Stores detailed monthly breakdown for each tax calculation
CREATE TABLE IF NOT EXISTS tax_calculation_details (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tax_calculation_id INT NOT NULL,
    month_index INT NOT NULL COMMENT '0-11 representing the month order',
    month_name VARCHAR(20) NOT NULL,
    exchange_rate DECIMAL(10, 2) NOT NULL,
    bonus_usd DECIMAL(15, 2) DEFAULT 0,
    fc_receipts_usd DECIMAL(15, 2) NOT NULL,
    fc_receipts_lkr DECIMAL(15, 2) NOT NULL,
    cumulative_income DECIMAL(15, 2) NOT NULL,
    total_tax_liability DECIMAL(15, 2) NOT NULL,
    monthly_payment DECIMAL(15, 2) NOT NULL,
    FOREIGN KEY (tax_calculation_id) REFERENCES tax_calculations(id) ON DELETE CASCADE,
    INDEX idx_tax_calculation (tax_calculation_id),
    INDEX idx_month_index (month_index)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Verify tables were created
SELECT 'Tax calculation tables created successfully!' AS status;
SHOW TABLES LIKE 'tax_%';
