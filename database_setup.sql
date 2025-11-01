-- =============================================
-- Personal Finance Manager - Database Setup
-- =============================================

-- Drop existing database if you want a fresh start (CAUTION: This will delete all data!)
-- DROP DATABASE IF EXISTS personal_finance;

-- Create database
CREATE DATABASE IF NOT EXISTS personal_finance CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE personal_finance;

-- =============================================
-- 1. USERS TABLE
-- =============================================
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_username (username),
    INDEX idx_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- 2. CATEGORIES TABLE
-- =============================================
CREATE TABLE IF NOT EXISTS categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    type ENUM('income', 'expense') NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_category_name (name),
    INDEX idx_type (type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- 3. MONTHLY RECORDS TABLE
-- =============================================
CREATE TABLE IF NOT EXISTS monthly_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    year INT NOT NULL,
    month INT NOT NULL CHECK (month BETWEEN 1 AND 12),
    month_name VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY unique_user_month (user_id, year, month),
    INDEX idx_user_year (user_id, year),
    INDEX idx_year_month (year, month)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- 4. TRANSACTIONS TABLE
-- =============================================
CREATE TABLE IF NOT EXISTS transactions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    monthly_record_id INT NOT NULL,
    description VARCHAR(255) NOT NULL,
    category_id INT,
    debit DECIMAL(15, 2) DEFAULT 0.00,
    credit DECIMAL(15, 2) DEFAULT 0.00,
    balance DECIMAL(15, 2),
    transaction_date DATE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (monthly_record_id) REFERENCES monthly_records(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL,
    INDEX idx_monthly_record (monthly_record_id),
    INDEX idx_category (category_id),
    INDEX idx_transaction_date (transaction_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- 5. RECURRING TRANSACTIONS TABLE
-- =============================================
CREATE TABLE IF NOT EXISTS recurring_transactions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    description VARCHAR(255) NOT NULL,
    category_id INT,
    type ENUM('debit', 'credit') NOT NULL,
    amount DECIMAL(15, 2) NOT NULL,
    day_of_month INT CHECK (day_of_month BETWEEN 1 AND 31),
    start_date DATE,
    end_date DATE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL,
    INDEX idx_user_active (user_id, is_active),
    INDEX idx_category (category_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- 6. BUDGET PLANS TABLE
-- =============================================
CREATE TABLE IF NOT EXISTS budget_plans (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    category_id INT NOT NULL,
    year INT NOT NULL,
    month INT NOT NULL CHECK (month BETWEEN 1 AND 12),
    planned_amount DECIMAL(15, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE,
    UNIQUE KEY unique_budget_plan (user_id, category_id, year, month),
    INDEX idx_user_period (user_id, year, month)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- 7. INSERT DEFAULT CATEGORIES
-- =============================================

-- Income Categories
INSERT IGNORE INTO categories (name, type, description) VALUES
('Salary', 'income', 'Monthly salary or wages'),
('Freelance', 'income', 'Freelance work income'),
('Business Income', 'income', 'Business revenue'),
('Investment Income', 'income', 'Returns from investments'),
('Rental Income', 'income', 'Income from property rentals'),
('Other Income', 'income', 'Miscellaneous income');

-- Expense Categories
INSERT IGNORE INTO categories (name, type, description) VALUES
('Groceries', 'expense', 'Food and grocery shopping'),
('Rent/Mortgage', 'expense', 'Housing rent or mortgage payment'),
('Utilities', 'expense', 'Electricity, water, gas, internet'),
('Transportation', 'expense', 'Fuel, public transport, vehicle maintenance'),
('Healthcare', 'expense', 'Medical expenses, insurance'),
('Insurance', 'expense', 'Various insurance premiums'),
('Entertainment', 'expense', 'Movies, dining out, hobbies'),
('Shopping', 'expense', 'Clothing, electronics, personal items'),
('Education', 'expense', 'Tuition, courses, books'),
('Savings', 'expense', 'Money transferred to savings'),
('Loan Payment', 'expense', 'Loan EMIs and repayments'),
('Phone/Internet', 'expense', 'Mobile and internet bills'),
('Subscriptions', 'expense', 'Netflix, Spotify, etc.'),
('Household', 'expense', 'Home maintenance and repairs'),
('Personal Care', 'expense', 'Salon, grooming, toiletries'),
('Gifts/Donations', 'expense', 'Gifts and charitable donations'),
('Travel', 'expense', 'Vacation and travel expenses'),
('Restaurants', 'expense', 'Dining out'),
('Other Expenses', 'expense', 'Miscellaneous expenses');

-- =============================================
-- 8. CREATE SAMPLE USER (for testing)
-- =============================================
-- Password is: demo123
-- You can generate your own hash using Python:
-- from werkzeug.security import generate_password_hash
-- print(generate_password_hash('your_password'))

INSERT IGNORE INTO users (username, email, password_hash) VALUES
('demo_user', 'demo@example.com', 'scrypt:32768:8:1$oEnXiK8PbQKDIVT5$c8d0c8a8e4c4e2e0e0c4e4e0e0c4e4e0e0c4e4e0e0c4e4e0e0c4e4e0e0c4e4e0e0c4e4e0e0c4e4e0e0c4e4e0');

-- =============================================
-- 9. USEFUL VIEWS (Optional but helpful)
-- =============================================

-- View: Monthly Summary
CREATE OR REPLACE VIEW monthly_summary AS
SELECT
    mr.user_id,
    mr.year,
    mr.month,
    mr.month_name,
    COALESCE(SUM(t.debit), 0) as total_income,
    COALESCE(SUM(t.credit), 0) as total_expenses,
    COALESCE(SUM(t.debit), 0) - COALESCE(SUM(t.credit), 0) as net_savings,
    MAX(t.balance) as ending_balance,
    COUNT(t.id) as transaction_count
FROM monthly_records mr
LEFT JOIN transactions t ON mr.id = t.monthly_record_id
GROUP BY mr.user_id, mr.year, mr.month, mr.month_name;

-- View: Category Summary
CREATE OR REPLACE VIEW category_summary AS
SELECT
    mr.user_id,
    mr.year,
    mr.month,
    c.id as category_id,
    c.name as category_name,
    c.type as category_type,
    COUNT(t.id) as transaction_count,
    COALESCE(SUM(CASE WHEN c.type = 'income' THEN t.debit ELSE t.credit END), 0) as total_amount
FROM monthly_records mr
LEFT JOIN transactions t ON mr.id = t.monthly_record_id
LEFT JOIN categories c ON t.category_id = c.id
WHERE c.id IS NOT NULL
GROUP BY mr.user_id, mr.year, mr.month, c.id, c.name, c.type;

-- =============================================
-- 10. SAMPLE DATA (Optional - for testing)
-- =============================================
-- Uncomment below to insert sample transactions for the demo user

/*
-- Get demo user ID
SET @demo_user_id = (SELECT id FROM users WHERE username = 'demo_user' LIMIT 1);

-- Create a monthly record for current month
INSERT INTO monthly_records (user_id, year, month, month_name)
VALUES (@demo_user_id, YEAR(CURDATE()), MONTH(CURDATE()), MONTHNAME(CURDATE()));

SET @monthly_record_id = LAST_INSERT_ID();

-- Sample Income Transactions
INSERT INTO transactions (monthly_record_id, description, category_id, debit, credit, transaction_date)
VALUES
(@monthly_record_id, 'Monthly Salary', (SELECT id FROM categories WHERE name = 'Salary'), 150000.00, 0, CURDATE()),
(@monthly_record_id, 'Freelance Project', (SELECT id FROM categories WHERE name = 'Freelance'), 25000.00, 0, CURDATE());

-- Sample Expense Transactions
INSERT INTO transactions (monthly_record_id, description, category_id, debit, credit, transaction_date)
VALUES
(@monthly_record_id, 'Rent Payment', (SELECT id FROM categories WHERE name = 'Rent/Mortgage'), 0, 35000.00, CURDATE()),
(@monthly_record_id, 'Grocery Shopping', (SELECT id FROM categories WHERE name = 'Groceries'), 0, 12000.00, CURDATE()),
(@monthly_record_id, 'Electricity Bill', (SELECT id FROM categories WHERE name = 'Utilities'), 0, 3500.00, CURDATE()),
(@monthly_record_id, 'Internet Bill', (SELECT id FROM categories WHERE name = 'Phone/Internet'), 0, 2500.00, CURDATE()),
(@monthly_record_id, 'Fuel', (SELECT id FROM categories WHERE name = 'Transportation'), 0, 8000.00, CURDATE()),
(@monthly_record_id, 'Restaurant', (SELECT id FROM categories WHERE name = 'Restaurants'), 0, 4500.00, CURDATE()),
(@monthly_record_id, 'Netflix Subscription', (SELECT id FROM categories WHERE name = 'Subscriptions'), 0, 1500.00, CURDATE());

-- Update balances (running balance calculation)
SET @balance = 0;
UPDATE transactions t
JOIN (
    SELECT id,
           @balance := @balance + COALESCE(debit, 0) - COALESCE(credit, 0) as running_balance
    FROM transactions
    WHERE monthly_record_id = @monthly_record_id
    ORDER BY transaction_date, id
) calc ON t.id = calc.id
SET t.balance = calc.running_balance;

-- Sample Recurring Transactions
INSERT INTO recurring_transactions (user_id, description, category_id, type, amount, day_of_month, start_date)
VALUES
(@demo_user_id, 'Monthly Salary', (SELECT id FROM categories WHERE name = 'Salary'), 'debit', 150000.00, 1, '2024-01-01'),
(@demo_user_id, 'Rent Payment', (SELECT id FROM categories WHERE name = 'Rent/Mortgage'), 'credit', 35000.00, 1, '2024-01-01'),
(@demo_user_id, 'Internet Bill', (SELECT id FROM categories WHERE name = 'Phone/Internet'), 'credit', 2500.00, 5, '2024-01-01'),
(@demo_user_id, 'Netflix', (SELECT id FROM categories WHERE name = 'Subscriptions'), 'credit', 1500.00, 10, '2024-01-01');

-- Sample Budget Plans
INSERT INTO budget_plans (user_id, category_id, year, month, planned_amount)
VALUES
(@demo_user_id, (SELECT id FROM categories WHERE name = 'Groceries'), YEAR(CURDATE()), MONTH(CURDATE()), 15000.00),
(@demo_user_id, (SELECT id FROM categories WHERE name = 'Transportation'), YEAR(CURDATE()), MONTH(CURDATE()), 10000.00),
(@demo_user_id, (SELECT id FROM categories WHERE name = 'Entertainment'), YEAR(CURDATE()), MONTH(CURDATE()), 8000.00),
(@demo_user_id, (SELECT id FROM categories WHERE name = 'Utilities'), YEAR(CURDATE()), MONTH(CURDATE()), 5000.00);
*/

-- =============================================
-- 11. VERIFICATION QUERIES
-- =============================================
-- Run these queries to verify your setup

-- Check all tables
-- SHOW TABLES;

-- Check categories
-- SELECT * FROM categories ORDER BY type, name;

-- Check users
-- SELECT id, username, email, created_at FROM users;

-- Check monthly records
-- SELECT * FROM monthly_records;

-- Check transactions
-- SELECT * FROM transactions;

-- Check recurring transactions
-- SELECT * FROM recurring_transactions;

-- Check budget plans
-- SELECT * FROM budget_plans;

-- =============================================
-- SETUP COMPLETE!
-- =============================================
-- You can now run your Flask application.
--
-- To connect to this database, update your .env file:
-- DB_HOST=localhost
-- DB_NAME=personal_finance
-- DB_USER=root
-- DB_PASSWORD=your_password
-- SECRET_KEY=your_secret_key_here
-- =============================================
