"""
Report Service Module

Handles all report-related routes including:
- Monthly summary reports
- Category breakdown reports
- Cash flow analysis
- Top spending categories
- Financial forecasting
"""

import logging
from datetime import datetime

from flask import request, jsonify, session
from mysql.connector import Error

from db import get_db_connection

logger = logging.getLogger(__name__)


def register_report_routes(app, login_required):
    """Register all report-related routes.

    Args:
        app: Flask application instance
        login_required: Decorator function for login protection
    """

    @app.route('/api/reports/monthly-summary')
    @login_required
    def monthly_summary_report():
        """Get monthly summary report."""
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            try:
                user_id = session['user_id']
                year = request.args.get('year', datetime.now().year, type=int)

                cursor.execute("""
                               SELECT mr.year,
                                      mr.month,
                                      mr.month_name,
                                      COALESCE(SUM(t.debit), 0)                              as total_income,
                                      COALESCE(SUM(t.credit), 0)                             as total_expenses,
                                      COALESCE(SUM(t.debit), 0) - COALESCE(SUM(t.credit), 0) as net_savings
                               FROM monthly_records mr
                                        LEFT JOIN transactions t ON mr.id = t.monthly_record_id
                               WHERE mr.user_id = %s
                                 AND mr.year = %s
                               GROUP BY mr.year, mr.month, mr.month_name
                               ORDER BY mr.month
                               """, (user_id, year))

                summary = cursor.fetchall()
                return jsonify(summary)

            except Error as e:
                return jsonify({'error': str(e)}), 500
            finally:
                cursor.close()
                connection.close()

        return jsonify({'error': 'Database connection failed'}), 500

    @app.route('/api/reports/category-breakdown')
    @login_required
    def category_breakdown_report():
        """Get category breakdown report with weekly, monthly, or yearly views."""
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            try:
                user_id = session['user_id']
                range_type = request.args.get('range', 'monthly')  # weekly, monthly, yearly
                year = request.args.get('year', datetime.now().year, type=int)
                month = request.args.get('month', datetime.now().month, type=int)

                if range_type == 'weekly':
                    # Get category spending by week for the specified month
                    cursor.execute("""
                                   SELECT WEEK(t.transaction_date, 1)                                             as week_num,
                                          DATE_FORMAT(MIN(t.transaction_date), '%%Y-%%m-%%d')                     as week_start,
                                          DATE_FORMAT(MAX(t.transaction_date), '%%Y-%%m-%%d')                     as week_end,
                                          c.name                                                                  as category,
                                          c.type,
                                          COALESCE(SUM(CASE WHEN c.type = 'income' THEN t.debit ELSE 0 END), 0)   as income,
                                          COALESCE(SUM(CASE WHEN c.type = 'expense' THEN t.credit ELSE 0 END), 0) as expense
                                   FROM transactions t
                                            INNER JOIN monthly_records mr ON t.monthly_record_id = mr.id
                                            INNER JOIN categories c ON t.category_id = c.id
                                   WHERE mr.user_id = %s
                                     AND mr.year = %s
                                     AND mr.month = %s
                                     AND t.category_id IS NOT NULL
                                   GROUP BY WEEK(t.transaction_date, 1), c.id, c.name, c.type
                                   HAVING income > 0
                                       OR expense > 0
                                   ORDER BY week_num, c.type, expense DESC, income DESC
                                   """, (user_id, year, month))
                elif range_type == 'yearly':
                    # Get category spending by year (all years)
                    cursor.execute("""
                                   SELECT mr.year,
                                          c.name                                                                  as category,
                                          c.type,
                                          COALESCE(SUM(CASE WHEN c.type = 'income' THEN t.debit ELSE 0 END), 0)   as income,
                                          COALESCE(SUM(CASE WHEN c.type = 'expense' THEN t.credit ELSE 0 END), 0) as expense
                                   FROM transactions t
                                            INNER JOIN monthly_records mr ON t.monthly_record_id = mr.id
                                            INNER JOIN categories c ON t.category_id = c.id
                                   WHERE mr.user_id = %s
                                     AND t.category_id IS NOT NULL
                                   GROUP BY mr.year, c.id, c.name, c.type
                                   HAVING income > 0
                                       OR expense > 0
                                   ORDER BY mr.year DESC, c.type, expense DESC, income DESC
                                   """, (user_id,))
                else:  # monthly (default)
                    # Get category spending for the specific selected month
                    cursor.execute("""
                                   SELECT mr.year,
                                          mr.month,
                                          mr.month_name,
                                          c.name                                                                  as category,
                                          c.type,
                                          COALESCE(SUM(CASE WHEN c.type = 'income' THEN t.debit ELSE 0 END), 0)   as income,
                                          COALESCE(SUM(CASE WHEN c.type = 'expense' THEN t.credit ELSE 0 END), 0) as expense
                                   FROM transactions t
                                            INNER JOIN monthly_records mr ON t.monthly_record_id = mr.id
                                            INNER JOIN categories c ON t.category_id = c.id
                                   WHERE mr.user_id = %s
                                     AND mr.year = %s
                                     AND mr.month = %s
                                     AND t.category_id IS NOT NULL
                                   GROUP BY mr.year, mr.month, mr.month_name, c.id, c.name, c.type
                                   HAVING income > 0
                                       OR expense > 0
                                   ORDER BY c.type, expense DESC, income DESC
                                   """, (user_id, year, month))

                breakdown = cursor.fetchall()
                return jsonify(breakdown)

            except Error as e:
                return jsonify({'error': str(e)}), 500
            finally:
                cursor.close()
                connection.close()

        return jsonify({'error': 'Database connection failed'}), 500

    @app.route('/api/reports/cash-flow')
    @login_required
    def cash_flow_report():
        """Get cash flow analysis report with customizable date ranges using view."""
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            try:
                user_id = session['user_id']
                range_type = request.args.get('range', 'monthly')  # weekly, monthly, yearly
                year = request.args.get('year', datetime.now().year, type=int)
                month = request.args.get('month', datetime.now().month, type=int)

                if range_type == 'weekly':
                    # Get weekly cash flow for the specified month
                    cursor.execute("""
                                   SELECT WEEK(t.transaction_date)                               as week_num,
                                          DATE_FORMAT(MIN(t.transaction_date), '%%Y-%%m-%%d')    as week_start,
                                          DATE_FORMAT(MAX(t.transaction_date), '%%Y-%%m-%%d')    as week_end,
                                          COALESCE(SUM(t.debit), 0)                              as cash_in,
                                          COALESCE(SUM(t.credit), 0)                             as cash_out,
                                          COALESCE(SUM(t.debit), 0) - COALESCE(SUM(t.credit), 0) as net_flow
                                   FROM transactions t
                                            JOIN monthly_records mr ON t.monthly_record_id = mr.id
                                   WHERE mr.user_id = %s
                                     AND mr.year = %s
                                     AND mr.month = %s
                                   GROUP BY WEEK(t.transaction_date)
                                   ORDER BY week_num
                                   """, (user_id, year, month))
                elif range_type == 'yearly':
                    # Get yearly cash flow
                    cursor.execute("""
                                   SELECT mr.year,
                                          COALESCE(SUM(t.debit), 0)                              as cash_in,
                                          COALESCE(SUM(t.credit), 0)                             as cash_out,
                                          COALESCE(SUM(t.debit), 0) - COALESCE(SUM(t.credit), 0) as net_flow
                                   FROM monthly_records mr
                                            LEFT JOIN transactions t ON mr.id = t.monthly_record_id
                                   WHERE mr.user_id = %s
                                   GROUP BY mr.year
                                   ORDER BY mr.year
                                   """, (user_id,))
                else:  # monthly (default)
                    # Get monthly cash flow
                    cursor.execute("""
                                   SELECT mr.year,
                                          mr.month,
                                          mr.month_name,
                                          COALESCE(SUM(t.debit), 0)                              as cash_in,
                                          COALESCE(SUM(t.credit), 0)                             as cash_out,
                                          COALESCE(SUM(t.debit), 0) - COALESCE(SUM(t.credit), 0) as net_flow
                                   FROM monthly_records mr
                                            LEFT JOIN transactions t ON mr.id = t.monthly_record_id
                                   WHERE mr.user_id = %s
                                     AND mr.year = %s
                                   GROUP BY mr.year, mr.month, mr.month_name
                                   ORDER BY mr.month
                                   """, (user_id, year))

                cash_flow = cursor.fetchall()
                return jsonify(cash_flow)

            except Error as e:
                return jsonify({'error': str(e)}), 500
            finally:
                cursor.close()
                connection.close()

        return jsonify({'error': 'Database connection failed'}), 500

    @app.route('/api/reports/top-spending')
    @login_required
    def top_spending_report():
        """Get top spending categories with customizable date ranges."""
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            try:
                user_id = session['user_id']
                range_type = request.args.get('range', 'monthly')
                year = request.args.get('year', datetime.now().year, type=int)
                month = request.args.get('month', datetime.now().month, type=int)
                limit = request.args.get('limit', 10, type=int)

                if range_type == 'weekly':
                    # Get top spending for the specified month
                    cursor.execute("""
                                   SELECT c.name                as category,
                                          c.type,
                                          SUM(t.credit)         as total_spent,
                                          COUNT(t.id)           as transaction_count,
                                          AVG(t.credit)         as avg_amount
                                   FROM transactions t
                                            INNER JOIN monthly_records mr ON t.monthly_record_id = mr.id
                                            INNER JOIN categories c ON t.category_id = c.id
                                   WHERE mr.user_id = %s
                                     AND mr.year = %s
                                     AND mr.month = %s
                                     AND c.type = 'expense'
                                     AND t.credit > 0
                                   GROUP BY c.id, c.name, c.type
                                   ORDER BY total_spent DESC
                                       LIMIT %s
                                   """, (user_id, year, month, limit))
                elif range_type == 'yearly':
                    # Get top spending for the specified year
                    cursor.execute("""
                                   SELECT c.name                as category,
                                          c.type,
                                          SUM(t.credit)         as total_spent,
                                          COUNT(t.id)           as transaction_count,
                                          AVG(t.credit)         as avg_amount
                                   FROM transactions t
                                            INNER JOIN monthly_records mr ON t.monthly_record_id = mr.id
                                            INNER JOIN categories c ON t.category_id = c.id
                                   WHERE mr.user_id = %s
                                     AND mr.year = %s
                                     AND c.type = 'expense'
                                     AND t.credit > 0
                                   GROUP BY c.id, c.name, c.type
                                   ORDER BY total_spent DESC
                                       LIMIT %s
                                   """, (user_id, year, limit))
                else:  # monthly
                    # Get top spending for the specified month
                    cursor.execute("""
                                   SELECT c.name                as category,
                                          c.type,
                                          SUM(t.credit)         as total_spent,
                                          COUNT(t.id)           as transaction_count,
                                          AVG(t.credit)         as avg_amount
                                   FROM transactions t
                                            INNER JOIN monthly_records mr ON t.monthly_record_id = mr.id
                                            INNER JOIN categories c ON t.category_id = c.id
                                   WHERE mr.user_id = %s
                                     AND mr.year = %s
                                     AND mr.month = %s
                                     AND c.type = 'expense'
                                     AND t.credit > 0
                                   GROUP BY c.id, c.name, c.type
                                   ORDER BY total_spent DESC
                                       LIMIT %s
                                   """, (user_id, year, month, limit))

                top_spending = cursor.fetchall()
                return jsonify(top_spending)

            except Error as e:
                return jsonify({'error': str(e)}), 500
            finally:
                cursor.close()
                connection.close()

        return jsonify({'error': 'Database connection failed'}), 500

    @app.route('/api/reports/forecast')
    @login_required
    def forecast_report():
        """Predict next month's spending based on historical data."""
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            try:
                user_id = session['user_id']
                months_to_analyze = request.args.get('months', 6, type=int)

                # Get historical data for the last N months
                cursor.execute("""
                               SELECT mr.year,
                                      mr.month,
                                      mr.month_name,
                                      COALESCE(SUM(t.debit), 0)                              as total_income,
                                      COALESCE(SUM(t.credit), 0)                             as total_expenses,
                                      COALESCE(SUM(t.debit), 0) - COALESCE(SUM(t.credit), 0) as net_savings
                               FROM monthly_records mr
                                        LEFT JOIN transactions t ON mr.id = t.monthly_record_id
                               WHERE mr.user_id = %s
                               GROUP BY mr.year, mr.month, mr.month_name
                               ORDER BY mr.year DESC, mr.month DESC
                                   LIMIT %s
                               """, (user_id, months_to_analyze))

                historical_data = cursor.fetchall()

                # Get category-wise spending patterns
                cursor.execute("""
                               SELECT c.name                 as category,
                                      AVG(t.credit)          as avg_monthly_spending,
                                      MIN(t.credit)          as min_spending,
                                      MAX(t.credit)          as max_spending,
                                      STDDEV(t.credit)       as std_deviation
                               FROM transactions t
                                        INNER JOIN monthly_records mr ON t.monthly_record_id = mr.id
                                        INNER JOIN categories c ON t.category_id = c.id
                               WHERE mr.user_id = %s
                                 AND c.type = 'expense'
                                 AND t.credit > 0
                               GROUP BY c.id, c.name
                               ORDER BY avg_monthly_spending DESC
                               """, (user_id,))

                category_forecast = cursor.fetchall()

                # Calculate simple averages for forecasting
                if historical_data:
                    avg_income = sum(float(row['total_income']) for row in historical_data) / len(historical_data)
                    avg_expenses = sum(float(row['total_expenses']) for row in historical_data) / len(historical_data)
                    avg_savings = sum(float(row['net_savings']) for row in historical_data) / len(historical_data)

                    # Calculate trend (simple linear)
                    if len(historical_data) >= 2:
                        recent_avg_expenses = sum(float(row['total_expenses']) for row in historical_data[:3]) / min(3,
                                                                                                                     len(historical_data))
                        older_avg_expenses = sum(float(row['total_expenses']) for row in historical_data[-3:]) / min(3,
                                                                                                                     len(historical_data))
                        trend = ((
                                         recent_avg_expenses - older_avg_expenses) / older_avg_expenses * 100) if older_avg_expenses > 0 else 0
                    else:
                        trend = 0

                    forecast = {
                        'next_month_forecast': {
                            'predicted_income': round(avg_income, 2),
                            'predicted_expenses': round(avg_expenses, 2),
                            'predicted_savings': round(avg_savings, 2),
                            'expense_trend': round(trend, 2),
                            'confidence': 'medium' if len(historical_data) >= 3 else 'low'
                        },
                        'historical_average': {
                            'avg_income': round(avg_income, 2),
                            'avg_expenses': round(avg_expenses, 2),
                            'avg_savings': round(avg_savings, 2)
                        },
                        'category_forecast': category_forecast,
                        'based_on_months': len(historical_data)
                    }
                else:
                    forecast = {
                        'next_month_forecast': {
                            'predicted_income': 0,
                            'predicted_expenses': 0,
                            'predicted_savings': 0,
                            'expense_trend': 0,
                            'confidence': 'no_data'
                        },
                        'historical_average': {
                            'avg_income': 0,
                            'avg_expenses': 0,
                            'avg_savings': 0
                        },
                        'category_forecast': [],
                        'based_on_months': 0
                    }

                return jsonify(forecast)

            except Error as e:
                return jsonify({'error': str(e)}), 500
            finally:
                cursor.close()
                connection.close()

        return jsonify({'error': 'Database connection failed'}), 500

    @app.route('/api/reports/payment-method-analysis')
    @login_required
    def payment_method_analysis_report():
        """Get spending/income breakdown by payment method."""
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            try:
                user_id = session['user_id']
                range_type = request.args.get('range', 'monthly')
                year = request.args.get('year', datetime.now().year, type=int)
                month = request.args.get('month', datetime.now().month, type=int)

                if range_type == 'yearly':
                    # Get payment method breakdown for the year
                    cursor.execute("""
                                   SELECT pm.name                                                         as payment_method,
                                          pm.color,
                                          COALESCE(SUM(t.debit), 0)                                       as total_income,
                                          COALESCE(SUM(t.credit), 0)                                      as total_expenses,
                                          COUNT(t.id)                                                     as transaction_count,
                                          COALESCE(AVG(CASE WHEN t.credit > 0 THEN t.credit END), 0)     as avg_expense,
                                          COALESCE(AVG(CASE WHEN t.debit > 0 THEN t.debit END), 0)       as avg_income
                                   FROM transactions t
                                            INNER JOIN monthly_records mr ON t.monthly_record_id = mr.id
                                            LEFT JOIN payment_methods pm ON t.payment_method_id = pm.id
                                   WHERE mr.user_id = %s
                                     AND mr.year = %s
                                   GROUP BY pm.id, pm.name, pm.color
                                   ORDER BY total_expenses DESC
                                   """, (user_id, year))
                else:  # monthly (default)
                    # Get payment method breakdown for the month
                    cursor.execute("""
                                   SELECT pm.name                                                         as payment_method,
                                          pm.color,
                                          COALESCE(SUM(t.debit), 0)                                       as total_income,
                                          COALESCE(SUM(t.credit), 0)                                      as total_expenses,
                                          COUNT(t.id)                                                     as transaction_count,
                                          COALESCE(AVG(CASE WHEN t.credit > 0 THEN t.credit END), 0)     as avg_expense,
                                          COALESCE(AVG(CASE WHEN t.debit > 0 THEN t.debit END), 0)       as avg_income
                                   FROM transactions t
                                            INNER JOIN monthly_records mr ON t.monthly_record_id = mr.id
                                            LEFT JOIN payment_methods pm ON t.payment_method_id = pm.id
                                   WHERE mr.user_id = %s
                                     AND mr.year = %s
                                     AND mr.month = %s
                                   GROUP BY pm.id, pm.name, pm.color
                                   ORDER BY total_expenses DESC
                                   """, (user_id, year, month))

                result = cursor.fetchall()
                return jsonify(result)

            except Error as e:
                return jsonify({'error': str(e)}), 500
            finally:
                cursor.close()
                connection.close()

        return jsonify({'error': 'Database connection failed'}), 500

    @app.route('/api/reports/spending-heatmap')
    @login_required
    def spending_heatmap_report():
        """Get spending patterns by day of week."""
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            try:
                user_id = session['user_id']
                range_type = request.args.get('range', 'monthly')
                year = request.args.get('year', datetime.now().year, type=int)
                month = request.args.get('month', datetime.now().month, type=int)

                if range_type == 'yearly':
                    # Get spending by day of week for the year
                    cursor.execute("""
                                   SELECT DAYOFWEEK(t.transaction_date)     as day_of_week,
                                          DAYNAME(t.transaction_date)       as day_name,
                                          COALESCE(SUM(t.credit), 0)        as total_spending,
                                          COUNT(t.id)                       as transaction_count,
                                          COALESCE(AVG(t.credit), 0)        as avg_amount
                                   FROM transactions t
                                            INNER JOIN monthly_records mr ON t.monthly_record_id = mr.id
                                   WHERE mr.user_id = %s
                                     AND mr.year = %s
                                     AND t.credit > 0
                                   GROUP BY DAYOFWEEK(t.transaction_date), DAYNAME(t.transaction_date)
                                   ORDER BY day_of_week
                                   """, (user_id, year))
                else:  # monthly (default)
                    # Get spending by day of week for the month
                    cursor.execute("""
                                   SELECT DAYOFWEEK(t.transaction_date)     as day_of_week,
                                          DAYNAME(t.transaction_date)       as day_name,
                                          COALESCE(SUM(t.credit), 0)        as total_spending,
                                          COUNT(t.id)                       as transaction_count,
                                          COALESCE(AVG(t.credit), 0)        as avg_amount
                                   FROM transactions t
                                            INNER JOIN monthly_records mr ON t.monthly_record_id = mr.id
                                   WHERE mr.user_id = %s
                                     AND mr.year = %s
                                     AND mr.month = %s
                                     AND t.credit > 0
                                   GROUP BY DAYOFWEEK(t.transaction_date), DAYNAME(t.transaction_date)
                                   ORDER BY day_of_week
                                   """, (user_id, year, month))

                result = cursor.fetchall()
                return jsonify(result)

            except Error as e:
                return jsonify({'error': str(e)}), 500
            finally:
                cursor.close()
                connection.close()

        return jsonify({'error': 'Database connection failed'}), 500

    @app.route('/api/reports/year-over-year')
    @login_required
    def year_over_year_report():
        """Get year-over-year comparison of income and expenses."""
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            try:
                user_id = session['user_id']

                # Get all years with month-by-month breakdown
                cursor.execute("""
                               SELECT mr.year,
                                      mr.month,
                                      mr.month_name,
                                      COALESCE(SUM(t.debit), 0)                              as total_income,
                                      COALESCE(SUM(t.credit), 0)                             as total_expenses,
                                      COALESCE(SUM(t.debit), 0) - COALESCE(SUM(t.credit), 0) as net_savings
                               FROM monthly_records mr
                                        LEFT JOIN transactions t ON mr.id = t.monthly_record_id
                               WHERE mr.user_id = %s
                               GROUP BY mr.year, mr.month, mr.month_name
                               ORDER BY mr.year, mr.month
                               """, (user_id,))

                result = cursor.fetchall()
                return jsonify(result)

            except Error as e:
                return jsonify({'error': str(e)}), 500
            finally:
                cursor.close()
                connection.close()

        return jsonify({'error': 'Database connection failed'}), 500

    @app.route('/api/reports/income-sources')
    @login_required
    def income_sources_report():
        """Get income breakdown by category."""
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            try:
                user_id = session['user_id']
                range_type = request.args.get('range', 'monthly')
                year = request.args.get('year', datetime.now().year, type=int)
                month = request.args.get('month', datetime.now().month, type=int)

                if range_type == 'yearly':
                    # Get income by category for all years
                    cursor.execute("""
                                   SELECT mr.year,
                                          c.name                        as category,
                                          COALESCE(SUM(t.debit), 0)     as total_income,
                                          COUNT(t.id)                   as transaction_count,
                                          COALESCE(AVG(t.debit), 0)     as avg_amount
                                   FROM transactions t
                                            INNER JOIN monthly_records mr ON t.monthly_record_id = mr.id
                                            INNER JOIN categories c ON t.category_id = c.id
                                   WHERE mr.user_id = %s
                                     AND c.type = 'income'
                                     AND t.debit > 0
                                   GROUP BY mr.year, c.id, c.name
                                   ORDER BY mr.year DESC, total_income DESC
                                   """, (user_id,))
                else:  # monthly (default)
                    # Get income by category for the specified month
                    cursor.execute("""
                                   SELECT mr.year,
                                          mr.month,
                                          mr.month_name,
                                          c.name                        as category,
                                          COALESCE(SUM(t.debit), 0)     as total_income,
                                          COUNT(t.id)                   as transaction_count,
                                          COALESCE(AVG(t.debit), 0)     as avg_amount
                                   FROM transactions t
                                            INNER JOIN monthly_records mr ON t.monthly_record_id = mr.id
                                            INNER JOIN categories c ON t.category_id = c.id
                                   WHERE mr.user_id = %s
                                     AND mr.year = %s
                                     AND mr.month = %s
                                     AND c.type = 'income'
                                     AND t.debit > 0
                                   GROUP BY mr.year, mr.month, mr.month_name, c.id, c.name
                                   ORDER BY total_income DESC
                                   """, (user_id, year, month))

                result = cursor.fetchall()
                return jsonify(result)

            except Error as e:
                return jsonify({'error': str(e)}), 500
            finally:
                cursor.close()
                connection.close()

        return jsonify({'error': 'Database connection failed'}), 500

    @app.route('/api/reports/transaction-status')
    @login_required
    def transaction_status_report():
        """Get transaction status breakdown (done/paid)."""
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            try:
                user_id = session['user_id']
                range_type = request.args.get('range', 'monthly')
                year = request.args.get('year', datetime.now().year, type=int)
                month = request.args.get('month', datetime.now().month, type=int)

                if range_type == 'yearly':
                    # Get transaction status for the year
                    cursor.execute("""
                                   SELECT mr.year,
                                          COUNT(t.id)                                           as total_transactions,
                                          SUM(CASE WHEN t.is_done = 1 THEN 1 ELSE 0 END)       as completed_count,
                                          SUM(CASE WHEN t.is_done = 0 THEN 1 ELSE 0 END)       as pending_count,
                                          SUM(CASE WHEN t.is_paid = 1 THEN 1 ELSE 0 END)       as paid_count,
                                          SUM(CASE WHEN t.is_paid = 0 THEN 1 ELSE 0 END)       as unpaid_count,
                                          COALESCE(SUM(CASE WHEN t.is_paid = 0 AND t.credit > 0 THEN t.credit ELSE 0 END), 0) as unpaid_expenses,
                                          COALESCE(SUM(CASE WHEN t.is_paid = 0 AND t.debit > 0 THEN t.debit ELSE 0 END), 0)  as unpaid_income
                                   FROM transactions t
                                            INNER JOIN monthly_records mr ON t.monthly_record_id = mr.id
                                   WHERE mr.user_id = %s
                                     AND mr.year = %s
                                   GROUP BY mr.year
                                   """, (user_id, year))
                else:  # monthly (default)
                    # Get transaction status for the month
                    cursor.execute("""
                                   SELECT mr.year,
                                          mr.month,
                                          mr.month_name,
                                          COUNT(t.id)                                           as total_transactions,
                                          SUM(CASE WHEN t.is_done = 1 THEN 1 ELSE 0 END)       as completed_count,
                                          SUM(CASE WHEN t.is_done = 0 THEN 1 ELSE 0 END)       as pending_count,
                                          SUM(CASE WHEN t.is_paid = 1 THEN 1 ELSE 0 END)       as paid_count,
                                          SUM(CASE WHEN t.is_paid = 0 THEN 1 ELSE 0 END)       as unpaid_count,
                                          COALESCE(SUM(CASE WHEN t.is_paid = 0 AND t.credit > 0 THEN t.credit ELSE 0 END), 0) as unpaid_expenses,
                                          COALESCE(SUM(CASE WHEN t.is_paid = 0 AND t.debit > 0 THEN t.debit ELSE 0 END), 0)  as unpaid_income
                                   FROM transactions t
                                            INNER JOIN monthly_records mr ON t.monthly_record_id = mr.id
                                   WHERE mr.user_id = %s
                                     AND mr.year = %s
                                     AND mr.month = %s
                                   GROUP BY mr.year, mr.month, mr.month_name
                                   """, (user_id, year, month))

                result = cursor.fetchall()
                return jsonify(result)

            except Error as e:
                return jsonify({'error': str(e)}), 500
            finally:
                cursor.close()
                connection.close()

        return jsonify({'error': 'Database connection failed'}), 500

    @app.route('/api/reports/expense-growth')
    @login_required
    def expense_growth_report():
        """Get month-over-month expense growth rate by category."""
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            try:
                user_id = session['user_id']
                year = request.args.get('year', datetime.now().year, type=int)

                # Get monthly category spending for the year
                cursor.execute("""
                               SELECT mr.year,
                                      mr.month,
                                      mr.month_name,
                                      c.name                            as category,
                                      COALESCE(SUM(t.credit), 0)        as total_spent
                               FROM transactions t
                                        INNER JOIN monthly_records mr ON t.monthly_record_id = mr.id
                                        INNER JOIN categories c ON t.category_id = c.id
                               WHERE mr.user_id = %s
                                 AND mr.year = %s
                                 AND c.type = 'expense'
                                 AND t.credit > 0
                               GROUP BY mr.year, mr.month, mr.month_name, c.id, c.name
                               ORDER BY mr.month, c.name
                               """, (user_id, year))

                result = cursor.fetchall()
                return jsonify(result)

            except Error as e:
                return jsonify({'error': str(e)}), 500
            finally:
                cursor.close()
                connection.close()

        return jsonify({'error': 'Database connection failed'}), 500

    @app.route('/api/reports/savings-rate')
    @login_required
    def savings_rate_report():
        """Get savings rate trend over time."""
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            try:
                user_id = session['user_id']
                range_type = request.args.get('range', 'monthly')
                year = request.args.get('year', datetime.now().year, type=int)

                if range_type == 'yearly':
                    # Get yearly savings rate
                    cursor.execute("""
                                   SELECT mr.year,
                                          COALESCE(SUM(t.debit), 0)                              as total_income,
                                          COALESCE(SUM(t.credit), 0)                             as total_expenses,
                                          COALESCE(SUM(t.debit), 0) - COALESCE(SUM(t.credit), 0) as net_savings
                                   FROM monthly_records mr
                                            LEFT JOIN transactions t ON mr.id = t.monthly_record_id
                                   WHERE mr.user_id = %s
                                   GROUP BY mr.year
                                   ORDER BY mr.year
                                   """, (user_id,))
                else:  # monthly (default)
                    # Get monthly savings rate for the year
                    cursor.execute("""
                                   SELECT mr.year,
                                          mr.month,
                                          mr.month_name,
                                          COALESCE(SUM(t.debit), 0)                              as total_income,
                                          COALESCE(SUM(t.credit), 0)                             as total_expenses,
                                          COALESCE(SUM(t.debit), 0) - COALESCE(SUM(t.credit), 0) as net_savings
                                   FROM monthly_records mr
                                            LEFT JOIN transactions t ON mr.id = t.monthly_record_id
                                   WHERE mr.user_id = %s
                                     AND mr.year = %s
                                   GROUP BY mr.year, mr.month, mr.month_name
                                   ORDER BY mr.month
                                   """, (user_id, year))

                result = cursor.fetchall()
                return jsonify(result)

            except Error as e:
                return jsonify({'error': str(e)}), 500
            finally:
                cursor.close()
                connection.close()

        return jsonify({'error': 'Database connection failed'}), 500
