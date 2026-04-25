"""
Dashboard Service

Provides data aggregation and calculations for dashboard views:
- Dashboard statistics (current month, YTD, categories, trends)
- Sidebar summary widgets (balance, exchange rates, tax info)
"""

import json
import logging
from datetime import datetime

from mysql.connector import Error

from db import get_db_connection
from services.exchange_rate_routes import get_best_rate_today
from services.transaction_service import get_month_summary

logger = logging.getLogger(__name__)


def get_dashboard_stats(user_id):
    """
    Get comprehensive dashboard statistics for a user.
    
    Args:
        user_id: The user's ID
    
    Returns:
        Dictionary containing:
        - current_stats: Current month income, expenses, balance
        - ytd_stats: Year-to-date income and expenses
        - recent_transactions: Last 10 transactions
        - monthly_trend: 12-month trend data
        - income_categories: Top 5 income categories
        - expense_categories: Top 5 expense categories
        
        Returns error dict on failure.
    """
    connection = get_db_connection()
    if not connection:
        return {'error': 'Database connection failed'}
    
    cursor = connection.cursor(dictionary=True)
    try:
        current_year = datetime.now().year
        current_month = datetime.now().month

        # Fetch current-month stats, YTD stats, and top categories
        # in a single round-trip using UNION ALL.
        cursor.execute("""
                       SELECT 'current' AS _section,
                              SUM(debit) AS total_income,
                              SUM(credit) AS total_expenses,
                              NULL AS ytd_income,
                              NULL AS ytd_expenses,
                              NULL AS category,
                              NULL AS amount,
                              NULL AS cat_type
                       FROM transactions t
                                JOIN monthly_records mr ON t.monthly_record_id = mr.id
                       WHERE mr.user_id = %s AND mr.year = %s AND mr.month = %s

                       UNION ALL

                       SELECT 'ytd', NULL, NULL,
                              SUM(debit), SUM(credit),
                              NULL, NULL, NULL
                       FROM transactions t
                                JOIN monthly_records mr ON t.monthly_record_id = mr.id
                       WHERE mr.user_id = %s AND mr.year = %s

                       UNION ALL

                       SELECT 'income_cat', NULL, NULL, NULL, NULL,
                              c.name, SUM(t.debit), NULL
                       FROM transactions t
                                JOIN monthly_records mr ON t.monthly_record_id = mr.id
                                LEFT JOIN categories c ON t.category_id = c.id
                       WHERE mr.user_id = %s AND mr.year = %s AND mr.month = %s AND t.debit > 0
                       GROUP BY c.name
                       ORDER BY amount DESC LIMIT 5
                       """, (user_id, current_year, current_month,
                             user_id, current_year,
                             user_id, current_year, current_month))

        # Parse the UNION ALL result set
        current_stats = {'total_income': 0, 'total_expenses': 0}
        ytd_stats = {'ytd_income': 0, 'ytd_expenses': 0}
        income_categories = []

        for row in cursor.fetchall():
            section = row['_section']
            if section == 'current':
                current_stats = {
                    'total_income': row['total_income'] or 0,
                    'total_expenses': row['total_expenses'] or 0,
                }
            elif section == 'ytd':
                ytd_stats = {
                    'ytd_income': row['ytd_income'] or 0,
                    'ytd_expenses': row['ytd_expenses'] or 0,
                }
            elif section == 'income_cat':
                income_categories.append({'category': row['category'], 'amount': row['amount']})

        current_stats['current_balance'] = (current_stats['total_income'] or 0) - (
                current_stats['total_expenses'] or 0)

        # Second query: expense categories, monthly trend, and recent
        # transactions (these need independent ORDER BY / LIMIT clauses).
        cursor.execute("""
                       SELECT c.name        as category,
                              SUM(t.credit) as amount
                       FROM transactions t
                                JOIN monthly_records mr ON t.monthly_record_id = mr.id
                                LEFT JOIN categories c ON t.category_id = c.id
                       WHERE mr.user_id = %s
                         AND mr.year = %s
                         AND mr.month = %s
                         AND t.credit > 0
                       GROUP BY c.name
                       ORDER BY amount DESC LIMIT 5
                       """, (user_id, current_year, current_month))
        expense_categories = cursor.fetchall()

        cursor.execute("""
                       SELECT mr.year,
                              mr.month,
                              mr.month_name,
                              SUM(t.debit)  as income,
                              SUM(t.credit) as expenses
                       FROM monthly_records mr
                                LEFT JOIN transactions t ON mr.id = t.monthly_record_id
                       WHERE mr.user_id = %s
                       GROUP BY mr.year, mr.month, mr.month_name
                       ORDER BY mr.year DESC, mr.month DESC LIMIT 12
                       """, (user_id,))
        monthly_trend = cursor.fetchall()

        cursor.execute("""
                       SELECT t.description,
                              t.debit,
                              t.credit,
                              t.transaction_date,
                              c.name as category
                       FROM transactions t
                                JOIN monthly_records mr ON t.monthly_record_id = mr.id
                                LEFT JOIN categories c ON t.category_id = c.id
                       WHERE mr.user_id = %s
                       ORDER BY t.created_at DESC LIMIT 10
                       """, (user_id,))
        recent_transactions = cursor.fetchall()

        return {
            'current_stats': current_stats,
            'ytd_stats': ytd_stats,
            'recent_transactions': recent_transactions,
            'monthly_trend': monthly_trend,
            'income_categories': income_categories,
            'expense_categories': expense_categories
        }

    except Error as e:
        logger.error(f"Error fetching dashboard stats for user {user_id}: {str(e)}")
        return {'error': str(e)}
    finally:
        cursor.close()
        connection.close()


def get_sidebar_summary(user_id, current_year, current_month):
    """
    Get summary data for sidebar widgets.
    
    Args:
        user_id: The user's ID
        current_year: Current calendar year
        current_month: Current calendar month (1-12)
    
    Returns:
        Dictionary containing:
        - month_summary: Balance and unpaid transaction count
        - exchange_rate: Best rate for today
        - tax_summary: Active tax calculation with quarterly payment info
    """
    try:
        # Get month summary (balance + unpaid count)
        month_data = get_month_summary(user_id, current_year, current_month)
        
        # Get best exchange rate
        rate_data = get_best_rate_today()
        
        # Get active tax calculation
        tax_data = get_active_tax_summary(user_id, current_year, current_month)
        
        return {
            'month_summary': month_data or {
                'total_income': 0,
                'total_expenses': 0,
                'balance': 0,
                'unpaid_count': 0
            },
            'exchange_rate': rate_data,
            'tax_summary': tax_data
        }
    
    except Exception as e:
        logger.error(f"Error in sidebar_summary for user {user_id}: {str(e)}")
        raise


def get_active_tax_summary(user_id, current_year, current_month):
    """
    Get active tax calculation summary with progressive bracket calculation.
    
    Args:
        user_id: The user's ID
        current_year: Current calendar year
        current_month: Current calendar month (1-12)
    
    Returns:
        Dictionary with tax calculation details or None if no active calculation
    """
    tax_data = None
    connection = get_db_connection()
    
    if not connection:
        logger.warning(f"Database connection failed for tax summary")
        return None
    
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT id, calculation_name, assessment_year, tax_rate, 
                   tax_free_threshold, start_month, monthly_data
            FROM tax_calculations
            WHERE user_id = %s AND is_active = TRUE
            ORDER BY created_at DESC
            LIMIT 1
        """, (user_id,))
        
        tax_calc = cursor.fetchone()
        if tax_calc:
            logger.info(f"Found active tax calculation: ID={tax_calc['id']}, "
                       f"Year={tax_calc['assessment_year']}, Name={tax_calc['calculation_name']}")
            
            # Parse monthly_data to calculate quarterly payment
            monthly_data = json.loads(tax_calc['monthly_data']) if tax_calc.get('monthly_data') else []
            logger.info(f"Monthly data entries: {len(monthly_data)}")
            
            # Calculate total annual income from salary_usd and bonuses
            total_annual_income_lkr = calculate_annual_income(monthly_data)
            tax_free = float(tax_calc.get('tax_free_threshold', 0))
            
            # Calculate tax using PROGRESSIVE BRACKETS (same as frontend)
            total_tax = calculate_progressive_tax(total_annual_income_lkr, tax_free)
            quarterly_payment = total_tax / 4 if total_tax > 0 else 0
            
            # Log calculation details for debugging
            logger.info(f"Tax calculation for {tax_calc['assessment_year']}: "
                       f"Income={total_annual_income_lkr:,.2f}, Tax-Free={tax_free:,.2f}, "
                       f"Total Tax={total_tax:,.2f}, Quarterly={quarterly_payment:,.2f}")
            
            # Determine current quarter based on start_month
            current_quarter = calculate_current_quarter(
                tax_calc.get('start_month', 0), 
                current_month
            )
            
            tax_data = {
                'assessment_year': tax_calc['assessment_year'],
                'quarterly_payment': round(quarterly_payment, 2),
                'total_tax': round(total_tax, 2),
                'current_quarter': current_quarter,
                'total_income': round(total_annual_income_lkr, 2)
            }
        else:
            logger.info("No active tax calculation found for user")
            
    except Exception as e:
        logger.error(f"Error fetching tax data for user {user_id}: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        cursor.close()
        connection.close()
    
    return tax_data


def calculate_annual_income(monthly_data):
    """
    Calculate total annual income from monthly salary and bonuses.
    
    Args:
        monthly_data: List of monthly income entries with salary_usd, salary_rate, and bonuses
    
    Returns:
        Total annual income in LKR
    """
    total_annual_income_lkr = 0
    
    for month_entry in monthly_data:
        # Salary income (USD * exchange rate)
        salary_usd = float(month_entry.get('salary_usd', 0))
        salary_rate = float(month_entry.get('salary_rate', 0))
        salary_lkr = salary_usd * salary_rate
        total_annual_income_lkr += salary_lkr
        
        # Bonus income
        bonuses = month_entry.get('bonuses', [])
        if bonuses and isinstance(bonuses, list):
            for bonus in bonuses:
                bonus_amount = float(bonus.get('amount', 0))
                bonus_rate = float(bonus.get('rate', 0))
                bonus_lkr = bonus_amount * bonus_rate
                total_annual_income_lkr += bonus_lkr
    
    return total_annual_income_lkr


def calculate_progressive_tax(total_income, tax_free_threshold):
    """
    Calculate tax using progressive brackets.
    
    Bracket 1: Up to tax_free_threshold - 0% (Relief)
    Bracket 2: tax_free_threshold+1 to tax_free_threshold+1,000,000 - 6%
    Bracket 3: Above tax_free_threshold+1,000,000 - 15%
    
    Args:
        total_income: Total annual income in LKR
        tax_free_threshold: Tax-free amount
    
    Returns:
        Total tax amount
    """
    total_tax = 0
    
    if total_income > tax_free_threshold:
        bracket_2_upper = tax_free_threshold + 1_000_000
        
        if total_income <= bracket_2_upper:
            # Income is in the 6% bracket
            total_tax = (total_income - tax_free_threshold) * 0.06
        else:
            # Income exceeds bracket 2
            # Tax on first 1,000,000 above tax_free: 6%
            total_tax = 1_000_000 * 0.06  # LKR 60,000
            # Tax on amount above bracket_2_upper: 15%
            total_tax += (total_income - bracket_2_upper) * 0.15
    
    return total_tax


def calculate_current_quarter(start_month_idx, current_month):
    """
    Determine current quarter based on tax year start month.
    
    Args:
        start_month_idx: 0-indexed start month (0=April, 1=May, etc.)
        current_month: Current calendar month (1-12)
    
    Returns:
        Current quarter number (1-4)
    """
    # Convert start_month index to actual month number (0=April -> 4)
    tax_year_start_month = (start_month_idx + 4) % 12
    if tax_year_start_month == 0:
        tax_year_start_month = 12
    
    # Calculate months elapsed since tax year started
    if current_month >= tax_year_start_month:
        # Same calendar year
        months_since_start = current_month - tax_year_start_month
    else:
        # Wrapped to next calendar year
        months_since_start = (12 - tax_year_start_month) + current_month
    
    # Determine quarter (0-2 = Q1, 3-5 = Q2, 6-8 = Q3, 9-11 = Q4)
    current_quarter = (months_since_start // 3) + 1
    
    return current_quarter
