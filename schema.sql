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
-- Notifications Table
-- ============================================================
-- Stores user notifications for various system events:
-- - Bill due date reminders
-- - Budget limit alerts
-- - Unusual spending detection
-- - Goal milestone celebrations
-- ============================================================

CREATE TABLE IF NOT EXISTS notifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    type ENUM('bill_reminder', 'budget_alert', 'unusual_spending', 'goal_milestone', 'system') NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    severity ENUM('info', 'warning', 'success', 'danger') DEFAULT 'info',
    is_read BOOLEAN DEFAULT FALSE,
    action_url VARCHAR(255) NULL,
    related_transaction_id INT NULL,
    related_data JSON NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    read_at TIMESTAMP NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (related_transaction_id) REFERENCES transactions(id) ON DELETE SET NULL,
    INDEX idx_user_id (user_id),
    INDEX idx_is_read (is_read),
    INDEX idx_type (type),
    INDEX idx_created_at (created_at),
    INDEX idx_user_unread (user_id, is_read, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- User Preferences Table
-- ============================================================
-- Stores user-specific notification and alert preferences
-- ============================================================

CREATE TABLE IF NOT EXISTS user_preferences (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,
    enable_bill_reminders BOOLEAN DEFAULT TRUE,
    bill_reminder_days_before INT DEFAULT 3,
    enable_budget_alerts BOOLEAN DEFAULT TRUE,
    monthly_budget_limit DECIMAL(15,2) NULL,
    enable_unusual_spending_detection BOOLEAN DEFAULT TRUE,
    unusual_spending_threshold_percentage INT DEFAULT 150,
    enable_email_notifications BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
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
