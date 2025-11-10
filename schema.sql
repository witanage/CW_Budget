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
--
-- Date: 2025-11-09
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
    is_active BOOLEAN DEFAULT TRUE,
    last_login TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_username (username),
    INDEX idx_email (email),
    INDEX idx_is_admin (is_admin),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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
    done_latitude DECIMAL(10, 8) NULL COMMENT 'Latitude when marked as done',
    done_longitude DECIMAL(11, 8) NULL COMMENT 'Longitude when marked as done',
    done_location_accuracy DECIMAL(10, 2) NULL COMMENT 'Location accuracy in meters when marked as done',
    paid_latitude DECIMAL(10, 8) NULL COMMENT 'Latitude when marked as paid',
    paid_longitude DECIMAL(11, 8) NULL COMMENT 'Longitude when marked as paid',
    paid_location_accuracy DECIMAL(10, 2) NULL COMMENT 'Location accuracy in meters when marked as paid',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (monthly_record_id) REFERENCES monthly_records(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL,
    FOREIGN KEY (payment_method_id) REFERENCES payment_methods(id) ON DELETE SET NULL,
    INDEX idx_monthly_record (monthly_record_id),
    INDEX idx_category (category_id),
    INDEX idx_payment_method (payment_method_id),
    INDEX idx_transaction_date (transaction_date),
    INDEX idx_is_done (is_done),
    INDEX idx_is_paid (is_paid)
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
-- Performance Views for New Reports Only
-- ============================================================
-- These views optimize the NEW report queries (cash flow, top spending, forecast)
-- Existing reports remain unchanged
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
JOIN monthly_records mr ON t.monthly_record_id = mr.id
LEFT JOIN categories c ON t.category_id = c.id
WHERE c.type = 'expense' AND t.credit > 0
GROUP BY mr.user_id, mr.year, mr.month, c.id, c.name, c.type;

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
-- ============================================================
