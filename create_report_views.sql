-- ============================================================
-- Database Views for New Reports
-- ============================================================
-- This file contains view definitions for optimizing the NEW
-- report queries (cash flow, top spending, forecast)
--
-- Run this file after setting up the main schema
-- ============================================================

-- Cash Flow View
-- Aggregates cash in/out by user, year, and month for cash flow analysis
-- Used by: Cash Flow Report, Forecast Report
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
-- Used by: Top Spending Report, Forecast Report
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

-- ============================================================
-- End of View Definitions
-- ============================================================
