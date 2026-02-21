-- ============================================================
-- Personal Finance Budget - Complete Database Schema
-- ============================================================
-- This file contains the complete database schema for the
-- Personal Finance Budget application.
--
-- Features:
-- - User authentication and management
-- - Admin role-based access control
-- - Transaction tracking with categories
-- - Payment methods management
-- - Monthly financial records
-- - Audit logging for admin actions
-- - Performance views for reporting
-- - Category spending analysis (weekly, monthly, yearly)
-- - Tax calculator with assessment year-wise tracking
--
-- Date: 2025-11-20
-- ============================================================

-- ============================================================
-- Users Table
-- ============================================================
-- Stores user accounts with authentication and admin features
-- New registrations are created in deactivated state (is_active=FALSE)
-- requiring admin approval before login
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(255) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    is_admin BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT FALSE,
    last_login TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_username (username),
    INDEX idx_email (email),
    INDEX idx_is_admin (is_admin),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Tokens Table
-- ============================================================
-- Stores the current JWT token per user for tracking and revocation.
-- One row per user; re-login overwrites the previous token in place.
CREATE TABLE IF NOT EXISTS tokens (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    token VARCHAR(500) NOT NULL UNIQUE,
    is_revoked BOOLEAN DEFAULT FALSE,
    expires_at DATETIME NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE INDEX idx_user_id (user_id),
    INDEX idx_expires_at (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='JWT tokens for session tracking and revocation';

-- ============================================================
-- Categories Table
-- ============================================================
-- Stores income and expense categories for transaction classification
-- ============================================================

CREATE TABLE IF NOT EXISTS categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    type ENUM('income', 'expense') NOT NULL,
    INDEX idx_type (type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Payment Methods Table
-- ============================================================
-- Stores user-defined payment methods (credit cards, bank accounts, etc.)
-- ============================================================

CREATE TABLE IF NOT EXISTS payment_methods (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(50) DEFAULT 'credit_card',
    color VARCHAR(7) DEFAULT '#007bff',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Monthly Records Table
-- ============================================================
-- Tracks monthly financial periods for each user
-- Unique constraint ensures one record per user/year/month combination
-- ============================================================

CREATE TABLE IF NOT EXISTS monthly_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    year INT NOT NULL,
    month INT NOT NULL,
    month_name VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY unique_user_month (user_id, year, month),
    INDEX idx_user_year_month (user_id, year, month)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Transactions Table
-- ============================================================
-- Stores all financial transactions (income and expenses)
-- - debit: Income amounts
-- - credit: Expense amounts
-- - Balance is calculated on frontend in real-time
-- ============================================================

CREATE TABLE IF NOT EXISTS transactions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    monthly_record_id INT NOT NULL,
    description VARCHAR(255) NOT NULL,
    category_id INT NULL,
    debit DECIMAL(15, 2) NULL COMMENT 'Income amount',
    credit DECIMAL(15, 2) NULL COMMENT 'Expense amount',
    transaction_date DATE NOT NULL,
    notes TEXT NULL,
    payment_method_id INT NULL,
    is_done BOOLEAN DEFAULT FALSE,
    is_paid BOOLEAN DEFAULT FALSE,
    marked_done_at TIMESTAMP NULL,
    paid_at TIMESTAMP NULL,
    display_order INT NOT NULL DEFAULT 0 COMMENT 'Order for displaying transactions (lower numbers first)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (monthly_record_id) REFERENCES monthly_records(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL,
    FOREIGN KEY (payment_method_id) REFERENCES payment_methods(id) ON DELETE SET NULL,
    INDEX idx_monthly_record (monthly_record_id),
    INDEX idx_category (category_id),
    INDEX idx_payment_method (payment_method_id),
    INDEX idx_transaction_date (transaction_date),
    INDEX idx_is_done (is_done),
    INDEX idx_is_paid (is_paid),
    INDEX idx_display_order (display_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Audit Logs Table
-- ============================================================
-- Tracks all admin actions for security and compliance
-- Logs user activations, deactivations, deletions, and privilege changes
-- ============================================================

CREATE TABLE IF NOT EXISTS audit_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    admin_user_id INT NOT NULL,
    action VARCHAR(100) NOT NULL,
    target_user_id INT NULL,
    details TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (admin_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (target_user_id) REFERENCES users(id) ON DELETE SET NULL,
    INDEX idx_admin_user (admin_user_id),
    INDEX idx_target_user (target_user_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Transaction Audit Logs Table
-- ============================================================
-- Tracks all changes to transaction records for audit trail
-- Records CREATE, UPDATE, DELETE operations with before/after values
-- ============================================================

CREATE TABLE IF NOT EXISTS transaction_audit_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    transaction_id INT NULL COMMENT 'Reference to transaction (NULL if deleted)',
    user_id INT NOT NULL COMMENT 'User who made the change',
    action VARCHAR(20) NOT NULL COMMENT 'CREATE, UPDATE, DELETE',
    field_name VARCHAR(100) NULL COMMENT 'Field that was changed (NULL for CREATE/DELETE)',
    old_value TEXT NULL COMMENT 'Previous value (NULL for CREATE)',
    new_value TEXT NULL COMMENT 'New value (NULL for DELETE)',
    ip_address VARCHAR(45) NULL COMMENT 'IP address of the user',
    user_agent TEXT NULL COMMENT 'Browser user agent',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_transaction_id (transaction_id),
    INDEX idx_user_id (user_id),
    INDEX idx_action (action),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Performance Views for Reports
-- ============================================================
-- These views optimize report queries and provide pre-aggregated data
-- for cash flow analysis, spending patterns, and category breakdowns
-- ============================================================

-- Cash Flow View
-- Aggregates cash in/out by user, year, and month for cash flow analysis
CREATE OR REPLACE VIEW v_cash_flow AS
SELECT
    mr.user_id,
    mr.year,
    mr.month,
    mr.month_name,
    COALESCE(SUM(t.debit), 0) as cash_in,
    COALESCE(SUM(t.credit), 0) as cash_out,
    COALESCE(SUM(t.debit), 0) - COALESCE(SUM(t.credit), 0) as net_flow
FROM monthly_records mr
LEFT JOIN transactions t ON mr.id = t.monthly_record_id
GROUP BY mr.user_id, mr.year, mr.month, mr.month_name;

-- Top Spending View
-- Pre-aggregates expense categories for top spending analysis
-- Uses INNER JOIN to exclude transactions without categories
CREATE OR REPLACE VIEW v_top_spending AS
SELECT
    mr.user_id,
    mr.year,
    mr.month,
    c.id as category_id,
    c.name as category,
    c.type,
    SUM(t.credit) as total_spent,
    COUNT(t.id) as transaction_count,
    AVG(t.credit) as avg_amount
FROM transactions t
INNER JOIN monthly_records mr ON t.monthly_record_id = mr.id
INNER JOIN categories c ON t.category_id = c.id
WHERE c.type = 'expense' AND t.credit > 0
GROUP BY mr.user_id, mr.year, mr.month, c.id, c.name, c.type;

-- Category Breakdown by Month View
-- Pre-aggregates category totals (income and expense) by month
-- Excludes transactions without categories for accurate reporting
CREATE OR REPLACE VIEW v_category_breakdown_monthly AS
SELECT
    mr.user_id,
    mr.year,
    mr.month,
    mr.month_name,
    c.id as category_id,
    c.name as category,
    c.type,
    COALESCE(SUM(CASE WHEN c.type = 'income' THEN t.debit ELSE 0 END), 0) as total_income,
    COALESCE(SUM(CASE WHEN c.type = 'expense' THEN t.credit ELSE 0 END), 0) as total_expense,
    COUNT(t.id) as transaction_count
FROM transactions t
INNER JOIN monthly_records mr ON t.monthly_record_id = mr.id
INNER JOIN categories c ON t.category_id = c.id
WHERE t.category_id IS NOT NULL
GROUP BY mr.user_id, mr.year, mr.month, mr.month_name, c.id, c.name, c.type;

-- Category Breakdown by Year View
-- Pre-aggregates category totals (income and expense) by year
-- Excludes transactions without categories for accurate reporting
CREATE OR REPLACE VIEW v_category_breakdown_yearly AS
SELECT
    mr.user_id,
    mr.year,
    c.id as category_id,
    c.name as category,
    c.type,
    COALESCE(SUM(CASE WHEN c.type = 'income' THEN t.debit ELSE 0 END), 0) as total_income,
    COALESCE(SUM(CASE WHEN c.type = 'expense' THEN t.credit ELSE 0 END), 0) as total_expense,
    COUNT(t.id) as transaction_count
FROM transactions t
INNER JOIN monthly_records mr ON t.monthly_record_id = mr.id
INNER JOIN categories c ON t.category_id = c.id
WHERE t.category_id IS NOT NULL
GROUP BY mr.user_id, mr.year, c.id, c.name, c.type;

-- Default Categories
-- ============================================================
-- Pre-populate with common income and expense categories
-- ============================================================

INSERT IGNORE INTO categories (name, type) VALUES
-- Income Categories
('Salary', 'income'),
('Freelance', 'income'),
('Investment', 'income'),
('Gift', 'income'),
('Other Income', 'income'),

-- Expense Categories
('Housing', 'expense'),
('Transportation', 'expense'),
('Food', 'expense'),
('Utilities', 'expense'),
('Healthcare', 'expense'),
('Entertainment', 'expense'),
('Shopping', 'expense'),
('Education', 'expense'),
('Insurance', 'expense'),
('Savings', 'expense'),
('Debt Payment', 'expense'),
('Other Expense', 'expense');

-- ============================================================
-- Tax Calculations Table
-- ============================================================
-- Stores income input data for foreign employment tax calculations
--
-- Design Philosophy:
-- - Store ONLY income input data (salaries, exchange rates, bonuses)
-- - Tax calculations (totals, liabilities) computed on-the-fly when loading
-- - Enables tracking across multiple assessment years
-- - One active calculation per user per assessment year
--
-- Monthly Data JSON Structure:
-- [
--   {
--     "month_index": 0-11,
--     "month": "April",
--     "salary_usd": 6000,
--     "salary_rate": 299.50,
--     "salary_rate_date": "2025-11-21" (optional),
--     "bonuses": [{"amount": 5000, "rate": 300, "date": "2025-11-21" (optional)}]
--   },
--   ...
-- ]
-- ============================================================

CREATE TABLE IF NOT EXISTS tax_calculations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    calculation_name VARCHAR(255) NOT NULL,
    assessment_year VARCHAR(20) NOT NULL COMMENT 'Format: YYYY/YYYY (e.g., 2024/2025)',
    tax_rate DECIMAL(5, 2) NOT NULL COMMENT 'Tax rate percentage (e.g., 15.00 for 15%)',
    tax_free_threshold DECIMAL(15, 2) NOT NULL COMMENT 'Annual tax-free threshold in LKR',
    start_month INT NOT NULL COMMENT 'Starting month index: 0=April, 1=May, ..., 11=March',
    monthly_data JSON NOT NULL COMMENT 'Array of 12 months with salaries, exchange rates, and bonuses',
    is_active BOOLEAN DEFAULT FALSE COMMENT 'TRUE if this is the active calculation for the assessment year',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_assessment_year (assessment_year),
    INDEX idx_created_at (created_at),
    INDEX idx_user_assessment_active (user_id, assessment_year, is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Stores income input data only - tax calculations computed on-the-fly when loading';

-- ============================================================
-- Tax Calculation Monthly Details Table (DEPRECATED)
-- ============================================================
-- This table is no longer used. Tax calculations are computed on-the-fly
-- from the income data stored in tax_calculations.monthly_data JSON field.
-- Keeping this commented out for reference in case of rollback.
-- ============================================================

-- CREATE TABLE IF NOT EXISTS tax_calculation_details (
--     id INT AUTO_INCREMENT PRIMARY KEY,
--     tax_calculation_id INT NOT NULL,
--     month_index INT NOT NULL COMMENT '0-11 representing the month order',
--     month_name VARCHAR(20) NOT NULL,
--     exchange_rate DECIMAL(10, 2) NOT NULL,
--     bonus_usd DECIMAL(15, 2) DEFAULT 0,
--     fc_receipts_usd DECIMAL(15, 2) NOT NULL,
--     fc_receipts_lkr DECIMAL(15, 2) NOT NULL,
--     cumulative_income DECIMAL(15, 2) NOT NULL,
--     total_tax_liability DECIMAL(15, 2) NOT NULL,
--     monthly_payment DECIMAL(15, 2) NOT NULL,
--     FOREIGN KEY (tax_calculation_id) REFERENCES tax_calculations(id) ON DELETE CASCADE,
--     INDEX idx_tax_calculation (tax_calculation_id),
--     INDEX idx_month_index (month_index)
-- ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Initial Setup Notes
-- ============================================================
-- After running this schema:
-- 1. The first user to register will need to be manually set as admin:
--    UPDATE users SET is_admin = TRUE, is_active = TRUE WHERE id = 1;
--
-- 2. New user registrations will be created with is_active = FALSE
--    and require admin approval before they can log in.
--
-- 3. Admins can manage users through the Admin Panel at /admin
--
-- 4. All transactions should have a category assigned for accurate reporting.
--    Transactions without categories are excluded from category reports.
--    To assign categories to transactions without one:
--    -- For income transactions:
--    UPDATE transactions SET category_id = (SELECT id FROM categories WHERE name = 'Other Income' LIMIT 1)
--    WHERE category_id IS NULL AND debit > 0;
--    -- For expense transactions:
--    UPDATE transactions SET category_id = (SELECT id FROM categories WHERE name = 'Other Expense' LIMIT 1)
--    WHERE category_id IS NULL AND credit > 0;
--
-- 5. The following views are available for optimized reporting:
--    - v_cash_flow: Monthly cash in/out analysis
--    - v_top_spending: Top expense categories
--    - v_category_breakdown_monthly: Category totals by month
--    - v_category_breakdown_yearly: Category totals by year
--
-- 6. Tax Calculator Feature:
--    - Stores ONLY income input data (monthly salaries, exchange rates, bonuses)
--    - Tax calculations are computed on-the-fly when loading saved calculations
--    - Supports multiple calculations per assessment year
--    - One "active" calculation per user per assessment year
--    - Monthly data stored as JSON array for flexibility
--    - Access via the Tax Calculator page in the dashboard
-- ============================================================

-- ============================================================
-- Exchange Rates Table
-- ============================================================
-- Stores USD to LKR exchange rates from CBSL
-- Can be populated via CSV import or API fetch
-- ============================================================

CREATE TABLE IF NOT EXISTS exchange_rates (
    id INT AUTO_INCREMENT PRIMARY KEY,
    date DATE NOT NULL COMMENT 'Date for the exchange rate',
    buy_rate DECIMAL(10, 4) NOT NULL COMMENT 'USD to LKR buy rate',
    sell_rate DECIMAL(10, 4) NOT NULL COMMENT 'USD to LKR sell rate',
    source VARCHAR(50) DEFAULT 'CBSL' COMMENT 'Source of the rate (CBSL, HNB, Manual, CSV)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_date_source (date, source),
    INDEX idx_date (date),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Stores USD to LKR exchange rates (one row per bank per date)';

-- ============================================================
-- App Settings Table
-- ============================================================
-- Runtime key-value store for tuneable application settings.
-- The background scheduler reads exchange_rate_refresh_interval_minutes
-- after every job run and reschedules itself if the value changed —
-- no application restart required.
-- ============================================================

CREATE TABLE IF NOT EXISTS app_settings (
    setting_key VARCHAR(100) PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Runtime application settings (key-value store)';

-- Seed defaults (INSERT IGNORE preserves any previously customised value)
INSERT IGNORE INTO app_settings (setting_key, value, description) VALUES
('exchange_rate_refresh_interval_minutes', '60',
 'How often (in minutes) the background scheduler fetches fresh exchange rates from all banks'),
('exchange_rate_refresh_mode', 'background',
 'How exchange rates are refreshed: background = automatic scheduler, manual = on-demand via admin only');

-- ============================================================
-- Exchange-Rate Refresh Logs Table
-- ============================================================
-- One row per source per scheduler run.  Captures whether the
-- fetch succeeded or failed, the rates that were stored (or the
-- error message), and the wall-clock time the attempt took.
-- ============================================================

CREATE TABLE IF NOT EXISTS exchange_rate_refresh_logs (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    source        VARCHAR(50)  NOT NULL COMMENT 'Bank / API source (HNB, PB, CBSL)',
    status        ENUM('success','failure') NOT NULL COMMENT 'Outcome of the fetch attempt',
    buy_rate      DECIMAL(10,4) NULL COMMENT 'Buy rate that was stored (NULL on failure)',
    sell_rate     DECIMAL(10,4) NULL COMMENT 'Sell rate that was stored (NULL on failure)',
    error_message TEXT          NULL COMMENT 'Error detail when status = failure',
    duration_ms   INT UNSIGNED  NULL COMMENT 'Wall-clock time of the fetch in milliseconds',
    created_at    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_source     (source),
    INDEX idx_status     (status),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Logs every exchange-rate refresh attempt made by the background scheduler';

-- ============================================================
-- Category Keywords Table
-- ============================================================
-- Stores keyword-to-category mappings for auto-categorization.
-- Each row is one keyword that maps to an expense category.
-- Moving these out of code allows editing without redeployment.
-- ============================================================

CREATE TABLE IF NOT EXISTS category_keywords (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    category_id INT          NOT NULL,
    keyword     VARCHAR(100) NOT NULL,
    created_at  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY  uk_keyword   (keyword),
    INDEX       idx_category (category_id),
    CONSTRAINT  fk_ck_category FOREIGN KEY (category_id) REFERENCES categories(id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Keyword-to-category mappings for auto-categorizing transactions';

-- Seed category keywords
INSERT IGNORE INTO category_keywords (category_id, keyword) VALUES
-- Groceries (7)
(7,'grocery'),(7,'groceries'),(7,'supermarket'),(7,'keells'),(7,'cargills'),
(7,'arpico'),(7,'food city'),(7,'spar'),(7,'glomark'),(7,'laugfs'),(7,'market'),
-- Housing (8)
(8,'rent'),(8,'mortgage'),(8,'housing'),(8,'landlord'),(8,'lease'),
-- Utilities (9)
(9,'utility'),(9,'utilities'),(9,'electricity'),(9,'water bill'),(9,'gas bill'),
(9,'ceb'),(9,'leco'),(9,'water board'),(9,'nwsdb'),
-- Transport (10)
(10,'transport'),(10,'bus'),(10,'train'),(10,'uber'),(10,'pickme'),
(10,'grab'),(10,'taxi'),(10,'parking'),(10,'toll'),(10,'highway'),
-- Healthcare (11)
(11,'healthcare'),(11,'medical'),(11,'hospital'),(11,'doctor'),(11,'clinic'),
(11,'pharmacy'),(11,'medicine'),(11,'channeling'),(11,'lab test'),(11,'dental'),
(11,'optician'),(11,'health'),
-- Insurance (12)
(12,'insurance'),(12,'premium'),(12,'policy'),(12,'life insurance'),
(12,'vehicle insurance'),(12,'ceylinco'),(12,'sri lanka insurance'),
(12,'aia'),(12,'allianz'),
-- Entertainment (13)
(13,'entertainment'),(13,'movie'),(13,'cinema'),(13,'concert'),(13,'netflix'),
(13,'spotify'),(13,'game'),(13,'gaming'),(13,'hobby'),(13,'recreation'),
(13,'theme park'),(13,'zoo'),
-- Shopping (14)
(14,'shopping'),(14,'clothing'),(14,'clothes'),(14,'shoes'),(14,'electronics'),
(14,'fashion'),(14,'mall'),(14,'odel'),(14,'nolimit'),(14,'cool planet'),
(14,'softlogic'),(14,'abans'),(14,'singer'),(14,'amazon'),(14,'aliexpress'),
(14,'daraz'),
-- Education (15)
(15,'education'),(15,'tuition'),(15,'school'),(15,'university'),(15,'college'),
(15,'course'),(15,'book'),(15,'training'),(15,'exam'),(15,'tutorial'),
(15,'udemy'),(15,'coursera'),(15,'class fee'),
-- Savings (16)
(16,'saving'),(16,'savings'),(16,'fd'),(16,'fixed deposit'),(16,'transfer to savings'),
-- Loan (17)
(17,'loan'),(17,'emi'),(17,'repayment'),(17,'installment'),(17,'leasing'),
(17,'finance company'),
-- Phone/Internet (18)
(18,'phone bill'),(18,'mobile bill'),(18,'internet bill'),(18,'broadband'),
(18,'dialog'),(18,'mobitel'),(18,'airtel'),(18,'hutch'),(18,'slt'),
(18,'lanka bell'),(18,'fiber'),(18,'wifi'),
-- Subscriptions (19)
(19,'subscription'),(19,'netflix'),(19,'spotify'),(19,'youtube premium'),
(19,'apple music'),(19,'disney'),(19,'hbo'),(19,'prime video'),(19,'icloud'),
(19,'google one'),(19,'membership'),
-- Household (20)
(20,'household'),(20,'home repair'),(20,'maintenance'),(20,'plumber'),
(20,'electrician'),(20,'cleaning'),(20,'furniture'),(20,'appliance'),(20,'hardware'),
-- Personal Care (21)
(21,'personal care'),(21,'salon'),(21,'barber'),(21,'haircut'),(21,'grooming'),
(21,'spa'),(21,'beauty'),(21,'toiletries'),(21,'cosmetics'),
-- Gift/Donation (22)
(22,'gift'),(22,'donation'),(22,'charity'),(22,'temple'),(22,'church'),
(22,'mosque'),(22,'alms'),(22,'wedding gift'),(22,'birthday gift'),
-- Travel (23)
(23,'travel'),(23,'vacation'),(23,'holiday'),(23,'hotel'),(23,'flight'),
(23,'airline'),(23,'airbnb'),(23,'booking'),(23,'trip'),(23,'tour'),
(23,'resort'),(23,'passport'),(23,'visa fee'),(23,'expressway'),
-- Restaurant (24)
(24,'restaurant'),(24,'dining'),(24,'cafe'),(24,'coffee'),(24,'kfc'),
(24,'mcdonald'),(24,'pizza hut'),(24,'domino'),(24,'burger king'),
(24,'starbucks'),(24,'eat'),(24,'lunch'),(24,'dinner'),(24,'breakfast'),
(24,'takeaway'),(24,'food delivery'),(24,'ubereats'),
-- Miscellaneous (25)
(25,'miscellaneous'),(25,'other'),(25,'misc'),
-- HSBC CC Fee (28)
(28,'hsbc cc fee'),(28,'hsbc credit card fee'),(28,'hsbc annual fee'),
-- Fuel (29)
(29,'fuel'),(29,'petrol'),(29,'diesel'),(29,'ceypetco'),(29,'ioc'),
(29,'gas station'),(29,'filling station'),(29,'lanka ioc'),
-- Income Tax (30)
(30,'income tax'),(30,'tax payment'),(30,'ird'),(30,'inland revenue'),
-- Vehicle (31)
(31,'vehicle'),(31,'car service'),(31,'vehicle service'),(31,'tyre'),
(31,'tire'),(31,'mechanic'),(31,'car wash'),(31,'revenue license'),
(31,'registration'),
-- HSBC Balancing (32)
(32,'hsbc cc balanc'),(32,'hsbv cc balanc'),(32,'hsbc balancing'),
-- Penalty (34)
(34,'penalty'),(34,'fine'),(34,'late fee'),(34,'overdue fee'),(34,'penalty fee'),
-- HNB CC Fee (35)
(35,'hnb cc fee'),(35,'hnb credit card fee'),(35,'hnb annual fee'),
-- HNB Fee (36)
(36,'hnb fee'),(36,'hnb bank fee'),(36,'hnb charge'),
-- Cash Out (37)
(37,'cash out'),(37,'withdrawal'),(37,'atm withdrawal'),(37,'cash withdraw'),
-- CEFT Fee (41)
(41,'ceft fee'),(41,'ceft charge'),(41,'transfer fee'),(41,'ceft');

