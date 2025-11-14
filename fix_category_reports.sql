-- ============================================================
-- FIX FOR CATEGORY SPENDING REPORTS
-- ============================================================
-- This file contains all views and fixes for the category reporting feature
-- Run this file to update your database with corrected views
-- ============================================================

-- ============================================================
-- Drop and recreate existing views (if any issues)
-- ============================================================

-- Cash Flow View (existing - keeping for reference)
DROP VIEW IF EXISTS v_cash_flow;
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

-- Top Spending View (existing - keeping for reference)
DROP VIEW IF EXISTS v_top_spending;
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
INNER JOIN categories c ON t.category_id = c.id
WHERE c.type = 'expense' AND t.credit > 0
GROUP BY mr.user_id, mr.year, mr.month, c.id, c.name, c.type;

-- ============================================================
-- NEW VIEW: Category Breakdown by Month
-- ============================================================
-- This view provides pre-aggregated category data by month
-- Excludes transactions without categories
-- Separates income and expense properly
-- ============================================================

DROP VIEW IF EXISTS v_category_breakdown_monthly;
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

-- ============================================================
-- NEW VIEW: Category Breakdown by Year
-- ============================================================
-- This view provides pre-aggregated category data by year
-- ============================================================

DROP VIEW IF EXISTS v_category_breakdown_yearly;
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

-- ============================================================
-- TEST QUERIES
-- ============================================================
-- Use these queries to verify the views are working correctly
-- Replace 1 with your actual user_id
-- ============================================================

-- Test monthly category breakdown for current year
-- SELECT * FROM v_category_breakdown_monthly
-- WHERE user_id = 1 AND year = YEAR(CURDATE())
-- ORDER BY month, type, total_expense DESC, total_income DESC;

-- Test yearly category breakdown
-- SELECT * FROM v_category_breakdown_yearly
-- WHERE user_id = 1
-- ORDER BY year DESC, type, total_expense DESC, total_income DESC;

-- Test category totals for specific month
-- SELECT
--     category,
--     type,
--     total_income,
--     total_expense,
--     transaction_count
-- FROM v_category_breakdown_monthly
-- WHERE user_id = 1 AND year = 2024 AND month = 11
-- ORDER BY type, total_expense DESC, total_income DESC;

-- ============================================================
-- VERIFICATION QUERIES
-- ============================================================
-- Run these to check if your data is correct
-- ============================================================

-- Check for transactions without categories (IMPORTANT - FIX THESE!)
-- SELECT
--     t.id,
--     t.description,
--     t.debit,
--     t.credit,
--     t.transaction_date,
--     mr.year,
--     mr.month
-- FROM transactions t
-- JOIN monthly_records mr ON t.monthly_record_id = mr.id
-- WHERE t.category_id IS NULL
-- ORDER BY t.transaction_date DESC;

-- Count transactions without categories
-- SELECT COUNT(*) as transactions_without_category
-- FROM transactions
-- WHERE category_id IS NULL;

-- Check category distribution (income vs expense)
-- SELECT
--     c.type,
--     c.name,
--     COUNT(t.id) as transaction_count,
--     COALESCE(SUM(CASE WHEN c.type = 'income' THEN t.debit END), 0) as total_income,
--     COALESCE(SUM(CASE WHEN c.type = 'expense' THEN t.credit END), 0) as total_expense
-- FROM transactions t
-- INNER JOIN categories c ON t.category_id = c.id
-- GROUP BY c.id, c.type, c.name
-- ORDER BY c.type, total_expense DESC, total_income DESC;

-- Get list of all categories with their IDs (useful for fixing NULL categories)
-- SELECT id, name, type FROM categories ORDER BY type, name;

-- ============================================================
-- FIX NULL CATEGORIES (Run these if you have transactions without categories)
-- ============================================================

-- First, check which transactions don't have categories
-- SELECT COUNT(*) FROM transactions WHERE category_id IS NULL;

-- Option 1: Assign all NULL income transactions to "Other Income"
-- UPDATE transactions t
-- SET t.category_id = (SELECT id FROM categories WHERE name = 'Other Income' LIMIT 1)
-- WHERE t.category_id IS NULL AND t.debit > 0;

-- Option 2: Assign all NULL expense transactions to "Other Expense"
-- UPDATE transactions t
-- SET t.category_id = (SELECT id FROM categories WHERE name = 'Other Expense' LIMIT 1)
-- WHERE t.category_id IS NULL AND t.credit > 0;

-- Option 3: Manually review and assign specific categories
-- First, see the transactions:
-- SELECT id, description, debit, credit, transaction_date
-- FROM transactions
-- WHERE category_id IS NULL;
-- Then update individually:
-- UPDATE transactions SET category_id = X WHERE id = Y;

-- ============================================================
-- INSTRUCTIONS
-- ============================================================
-- 1. Backup your database before running this script:
--    mysqldump -u username -p database_name > backup.sql
--
-- 2. Run this script to create/update views:
--    mysql -u username -p database_name < fix_category_reports.sql
--
-- 3. Check for transactions without categories:
--    Run the verification queries above (uncomment them)
--
-- 4. Fix transactions without categories:
--    Use the FIX NULL CATEGORIES queries above
--
-- 5. Restart your Flask application:
--    The backend code has been updated to use INNER JOIN and filter NULL categories
--
-- 6. Test the category reports in the web interface:
--    - Navigate to Reports > Category Analysis
--    - Try different date ranges (Weekly, Monthly, Yearly)
--    - Verify income and expense totals match your expectations
--
-- ============================================================
-- WHAT WAS FIXED
-- ============================================================
-- Backend Changes (app.py):
-- 1. Changed LEFT JOIN to INNER JOIN for categories
--    - This excludes transactions without categories from reports
--    - Prevents NULL category names from appearing
--
-- 2. Added WHERE t.category_id IS NOT NULL filter
--    - Double-ensures no NULL categories slip through
--
-- 3. Added HAVING income > 0 OR expense > 0
--    - Only shows categories that have actual amounts
--    - Removes zero-value rows from results
--
-- 4. Wrapped SUM() in COALESCE(..., 0)
--    - Ensures NULL sums become 0 instead of NULL
--    - Prevents JavaScript errors with undefined values
--
-- Frontend Changes (dashboard.js):
-- 1. Now correctly aggregates by category across time periods
-- 2. Separates income and expense into distinct charts
-- 3. Calculates percentages correctly for each category
-- 4. Shows net savings and savings rate
--
-- Database Views:
-- 1. Created v_category_breakdown_monthly for optimized monthly queries
-- 2. Created v_category_breakdown_yearly for optimized yearly queries
-- 3. Both views use INNER JOIN and exclude NULL categories
-- ============================================================
