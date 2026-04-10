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
                    # Get yearly cash flow using view
                    cursor.execute("""
                                   SELECT
                                       year, SUM (cash_in) as cash_in, SUM (cash_out) as cash_out, SUM (net_flow) as net_flow
                                   FROM v_cash_flow
                                   WHERE user_id = %s
                                   GROUP BY year
                                   ORDER BY year
                                   """, (user_id,))
                else:  # monthly (default)
                    # Get monthly cash flow using view
                    cursor.execute("""
                                   SELECT
                                       year, month, month_name, cash_in, cash_out, net_flow
                                   FROM v_cash_flow
                                   WHERE user_id = %s
                                     AND year = %s
                                   ORDER BY month
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
                    # Get top spending for the specified month using view
                    cursor.execute("""
                                   SELECT category,
                                          type,
                                          total_spent,
                                          transaction_count,
                                          avg_amount
                                   FROM v_top_spending
                                   WHERE user_id = %s AND year = %s AND month = %s
                                   ORDER BY total_spent DESC
                                       LIMIT %s
                                   """, (user_id, year, month, limit))
                elif range_type == 'yearly':
                    # Get top spending for the specified year using view
                    cursor.execute("""
                                   SELECT category,
                                          type,
                                          SUM(total_spent)       as total_spent,
                                          SUM(transaction_count) as transaction_count,
                                          AVG(avg_amount)        as avg_amount
                                   FROM v_top_spending
                                   WHERE user_id = %s AND year = %s
                                   GROUP BY category_id, category, type
                                   ORDER BY total_spent DESC
                                       LIMIT %s
                                   """, (user_id, year, limit))
                else:  # monthly
                    # Get top spending for the specified month using view
                    cursor.execute("""
                                   SELECT category,
                                          type,
                                          total_spent,
                                          transaction_count,
                                          avg_amount
                                   FROM v_top_spending
                                   WHERE user_id = %s AND year = %s AND month = %s
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

                # Get historical data for the last N months using view
                cursor.execute("""
                               SELECT
                                   year, month, month_name, cash_in as total_income, cash_out as total_expenses, net_flow as net_savings
                               FROM v_cash_flow
                               WHERE user_id = %s
                               ORDER BY year DESC, month DESC
                                   LIMIT %s
                               """, (user_id, months_to_analyze))

                historical_data = cursor.fetchall()

                # Get category-wise spending patterns using view
                cursor.execute("""
                               SELECT category,
                                      AVG(total_spent)    as avg_monthly_spending,
                                      MIN(total_spent)    as min_spending,
                                      MAX(total_spent)    as max_spending,
                                      STDDEV(total_spent) as std_deviation
                               FROM v_top_spending
                               WHERE user_id = %s
                               GROUP BY category_id, category
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
