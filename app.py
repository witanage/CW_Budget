import os
import json
from datetime import datetime, timedelta
from decimal import Decimal
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
from mysql.connector import Error
from functools import wraps
import calendar

# Custom JSON provider to handle Decimal objects
class DecimalJSONProvider(DefaultJSONProvider):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)

# Flask app configuration
app = Flask(__name__)
app.json = DecimalJSONProvider(app)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-change-in-production')
CORS(app)

# Database configuration
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'database': os.environ.get('DB_NAME', 'personal_finance'),
    'user': os.environ.get('DB_USER', 'root'),
    'password': os.environ.get('DB_PASSWORD', ''),
    'charset': 'utf8mb4',
    'use_unicode': True
}

def get_db_connection():
    """Create a database connection."""
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        return connection
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

def login_required(f):
    """Decorator to require login for routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Utility function to serialize Decimal for JSON
def decimal_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError

# Routes
@app.route('/')
def index():
    """Landing page."""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration."""
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor()
            try:
                # Check if user already exists
                cursor.execute("SELECT id FROM users WHERE username = %s OR email = %s", 
                             (username, email))
                if cursor.fetchone():
                    return jsonify({'error': 'Username or email already exists'}), 400
                
                # Create new user
                password_hash = generate_password_hash(password)
                cursor.execute(
                    "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)",
                    (username, email, password_hash)
                )
                connection.commit()
                
                return jsonify({'message': 'Registration successful'}), 201
            except Error as e:
                return jsonify({'error': str(e)}), 500
            finally:
                cursor.close()
                connection.close()
        
        return jsonify({'error': 'Database connection failed'}), 500
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login."""
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        username = data.get('username')
        password = data.get('password')
        
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            try:
                # Check if username is an email or username
                cursor.execute("SELECT * FROM users WHERE username = %s OR email = %s",
                             (username, username))
                user = cursor.fetchone()
                
                if user and check_password_hash(user['password_hash'], password):
                    session['user_id'] = user['id']
                    session['username'] = user['username']
                    return jsonify({'message': 'Login successful'}), 200
                else:
                    return jsonify({'error': 'Invalid credentials'}), 401
            except Error as e:
                return jsonify({'error': str(e)}), 500
            finally:
                cursor.close()
                connection.close()
        
        return jsonify({'error': 'Database connection failed'}), 500
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """User logout."""
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard."""
    return render_template('dashboard.html', username=session.get('username'))

@app.route('/api/dashboard-stats')
@login_required
def dashboard_stats():
    """Get dashboard statistics."""
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor(dictionary=True)
        try:
            user_id = session['user_id']
            
            # Get current month stats
            current_year = datetime.now().year
            current_month = datetime.now().month
            
            cursor.execute("""
                SELECT 
                    SUM(debit) as total_income,
                    SUM(credit) as total_expenses,
                    MAX(balance) as current_balance
                FROM transactions t
                JOIN monthly_records mr ON t.monthly_record_id = mr.id
                WHERE mr.user_id = %s AND mr.year = %s AND mr.month = %s
            """, (user_id, current_year, current_month))
            
            current_stats = cursor.fetchone()
            
            # Get year-to-date stats
            cursor.execute("""
                SELECT 
                    SUM(debit) as ytd_income,
                    SUM(credit) as ytd_expenses
                FROM transactions t
                JOIN monthly_records mr ON t.monthly_record_id = mr.id
                WHERE mr.user_id = %s AND mr.year = %s
            """, (user_id, current_year))
            
            ytd_stats = cursor.fetchone()
            
            # Get recent transactions
            cursor.execute("""
                SELECT 
                    t.description,
                    t.debit,
                    t.credit,
                    t.balance,
                    t.transaction_date,
                    c.name as category
                FROM transactions t
                JOIN monthly_records mr ON t.monthly_record_id = mr.id
                LEFT JOIN categories c ON t.category_id = c.id
                WHERE mr.user_id = %s
                ORDER BY t.created_at DESC
                LIMIT 10
            """, (user_id,))
            
            recent_transactions = cursor.fetchall()
            
            # Get monthly trend (last 12 months)
            cursor.execute("""
                SELECT 
                    mr.year,
                    mr.month,
                    mr.month_name,
                    SUM(t.debit) as income,
                    SUM(t.credit) as expenses
                FROM monthly_records mr
                LEFT JOIN transactions t ON mr.id = t.monthly_record_id
                WHERE mr.user_id = %s
                GROUP BY mr.year, mr.month, mr.month_name
                ORDER BY mr.year DESC, mr.month DESC
                LIMIT 12
            """, (user_id,))
            
            monthly_trend = cursor.fetchall()
            
            return jsonify({
                'current_stats': current_stats,
                'ytd_stats': ytd_stats,
                'recent_transactions': recent_transactions,
                'monthly_trend': monthly_trend
            })
            
        except Error as e:
            return jsonify({'error': str(e)}), 500
        finally:
            cursor.close()
            connection.close()
    
    return jsonify({'error': 'Database connection failed'}), 500

@app.route('/api/transactions', methods=['GET', 'POST'])
@login_required
def transactions():
    """Get or create transactions."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500
    
    cursor = connection.cursor(dictionary=True)
    user_id = session['user_id']
    
    try:
        if request.method == 'GET':
            # Get query parameters
            year = request.args.get('year', datetime.now().year, type=int)
            month = request.args.get('month', datetime.now().month, type=int)
            
            # Get monthly record
            cursor.execute("""
                SELECT id FROM monthly_records 
                WHERE user_id = %s AND year = %s AND month = %s
            """, (user_id, year, month))
            
            monthly_record = cursor.fetchone()
            
            if monthly_record:
                cursor.execute("""
                    SELECT
                        t.*,
                        c.name as category_name,
                        pm.name as payment_method_name,
                        pm.type as payment_method_type,
                        pm.color as payment_method_color,
                        COALESCE(t.is_paid, FALSE) as is_paid
                    FROM transactions t
                    LEFT JOIN categories c ON t.category_id = c.id
                    LEFT JOIN payment_methods pm ON t.payment_method_id = pm.id
                    WHERE t.monthly_record_id = %s
                    ORDER BY t.id
                """, (monthly_record['id'],))

                transactions = cursor.fetchall()
                return jsonify(transactions)
            else:
                return jsonify([])
        
        else:  # POST - Create new transaction
            data = request.get_json()
            print(f"[DEBUG] Received transaction data: {data}")

            # Get or create monthly record
            year = data.get('year', datetime.now().year)
            month = data.get('month', datetime.now().month)
            month_name = calendar.month_name[month]

            cursor.execute("""
                INSERT INTO monthly_records (user_id, year, month, month_name)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE updated_at = CURRENT_TIMESTAMP
            """, (user_id, year, month, month_name))

            cursor.execute("""
                SELECT id FROM monthly_records
                WHERE user_id = %s AND year = %s AND month = %s
            """, (user_id, year, month))

            monthly_record = cursor.fetchone()

            # Calculate balance: get previous balance and add/subtract current transaction
            cursor.execute("""
                SELECT balance FROM transactions
                WHERE monthly_record_id = %s
                ORDER BY id DESC LIMIT 1
            """, (monthly_record['id'],))

            last_balance_row = cursor.fetchone()
            previous_balance = last_balance_row['balance'] if last_balance_row and last_balance_row['balance'] is not None else Decimal('0')

            # Convert to Decimal to avoid float/Decimal arithmetic errors
            debit_value = data.get('debit')
            credit_value = data.get('credit')

            debit = Decimal(str(debit_value)) if debit_value else Decimal('0')
            credit = Decimal(str(credit_value)) if credit_value else Decimal('0')

            # Ensure previous_balance is also Decimal
            if not isinstance(previous_balance, Decimal):
                previous_balance = Decimal(str(previous_balance))

            print(f"[DEBUG] Debit: {debit}, Credit: {credit}, Previous balance: {previous_balance}")
            new_balance = previous_balance + debit - credit
            print(f"[DEBUG] New balance: {new_balance}")

            # Insert transaction
            insert_values = (
                monthly_record['id'],
                data.get('description'),
                data.get('category_id'),
                debit if debit > 0 else None,
                credit if credit > 0 else None,
                new_balance,
                data.get('transaction_date'),
                data.get('notes')
            )
            print(f"[DEBUG] Inserting transaction with values: {insert_values}")

            cursor.execute("""
                INSERT INTO transactions
                (monthly_record_id, description, category_id, debit, credit, balance, transaction_date, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, insert_values)

            transaction_id = cursor.lastrowid
            print(f"[DEBUG] Transaction inserted with ID: {transaction_id}")

            connection.commit()
            print(f"[DEBUG] Transaction committed successfully")

            return jsonify({'message': 'Transaction created successfully', 'id': transaction_id}), 201
            
    except Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()

@app.route('/api/transactions/<int:transaction_id>', methods=['PUT', 'DELETE'])
@login_required
def manage_transaction(transaction_id):
    """Update or delete a transaction."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500
    
    cursor = connection.cursor()
    
    try:
        if request.method == 'PUT':
            data = request.get_json()

            # Get the monthly_record_id for this transaction
            cursor.execute("""
                SELECT monthly_record_id FROM transactions
                WHERE id = %s AND monthly_record_id IN
                    (SELECT id FROM monthly_records WHERE user_id = %s)
            """, (transaction_id, session['user_id']))

            result = cursor.fetchone()
            if not result:
                return jsonify({'error': 'Transaction not found'}), 404

            monthly_record_id = result[0]

            # Get previous balance (from transaction before this one)
            cursor.execute("""
                SELECT balance FROM transactions
                WHERE monthly_record_id = %s AND id < %s
                ORDER BY id DESC LIMIT 1
            """, (monthly_record_id, transaction_id))

            prev_balance_row = cursor.fetchone()
            previous_balance = prev_balance_row[0] if prev_balance_row and prev_balance_row[0] is not None else Decimal('0')

            # Convert to Decimal to avoid float/Decimal arithmetic errors
            debit_value = data.get('debit')
            credit_value = data.get('credit')

            debit = Decimal(str(debit_value)) if debit_value else Decimal('0')
            credit = Decimal(str(credit_value)) if credit_value else Decimal('0')

            # Ensure previous_balance is also Decimal
            if not isinstance(previous_balance, Decimal):
                previous_balance = Decimal(str(previous_balance))

            new_balance = previous_balance + debit - credit

            # Update transaction
            cursor.execute("""
                UPDATE transactions
                SET description = %s, category_id = %s, debit = %s,
                    credit = %s, balance = %s, notes = %s
                WHERE id = %s
            """, (
                data.get('description'),
                data.get('category_id'),
                debit if debit > 0 else None,
                credit if credit > 0 else None,
                new_balance,
                data.get('notes'),
                transaction_id
            ))

            # Recalculate balances for all subsequent transactions
            cursor.execute("""
                SELECT id, debit, credit FROM transactions
                WHERE monthly_record_id = %s AND id > %s
                ORDER BY id
            """, (monthly_record_id, transaction_id))

            subsequent_transactions = cursor.fetchall()
            current_balance = new_balance

            for trans in subsequent_transactions:
                trans_id, trans_debit, trans_credit = trans
                # Convert to Decimal for arithmetic
                trans_debit = Decimal(str(trans_debit)) if trans_debit else Decimal('0')
                trans_credit = Decimal(str(trans_credit)) if trans_credit else Decimal('0')
                current_balance = current_balance + trans_debit - trans_credit
                cursor.execute("""
                    UPDATE transactions SET balance = %s WHERE id = %s
                """, (current_balance, trans_id))

            connection.commit()
            return jsonify({'message': 'Transaction updated successfully'})
        
        else:  # DELETE
            cursor.execute("""
                DELETE FROM transactions 
                WHERE id = %s AND monthly_record_id IN 
                    (SELECT id FROM monthly_records WHERE user_id = %s)
            """, (transaction_id, session['user_id']))
            
            connection.commit()
            return jsonify({'message': 'Transaction deleted successfully'})
            
    except Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()

@app.route('/api/categories')
@login_required
def get_categories():
    """Get all categories."""
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("SELECT * FROM categories ORDER BY type, name")
            categories = cursor.fetchall()
            return jsonify(categories)
        except Error as e:
            return jsonify({'error': str(e)}), 500
        finally:
            cursor.close()
            connection.close()
    
    return jsonify({'error': 'Database connection failed'}), 500

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

            # Calculate summary from transactions instead of relying on a view
            cursor.execute("""
                SELECT
                    mr.year,
                    mr.month,
                    mr.month_name,
                    COALESCE(SUM(t.debit), 0) as total_income,
                    COALESCE(SUM(t.credit), 0) as total_expenses,
                    COALESCE(SUM(t.debit), 0) - COALESCE(SUM(t.credit), 0) as net_savings
                FROM monthly_records mr
                LEFT JOIN transactions t ON mr.id = t.monthly_record_id
                WHERE mr.user_id = %s AND mr.year = %s
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
    """Get category breakdown report."""
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor(dictionary=True)
        try:
            user_id = session['user_id']
            year = request.args.get('year', datetime.now().year, type=int)
            month = request.args.get('month', type=int)
            
            if month:
                cursor.execute("""
                    SELECT 
                        c.name as category,
                        c.type,
                        SUM(CASE WHEN c.type = 'income' THEN t.debit ELSE t.credit END) as amount
                    FROM transactions t
                    JOIN monthly_records mr ON t.monthly_record_id = mr.id
                    LEFT JOIN categories c ON t.category_id = c.id
                    WHERE mr.user_id = %s AND mr.year = %s AND mr.month = %s
                    GROUP BY c.id, c.name, c.type
                    ORDER BY amount DESC
                """, (user_id, year, month))
            else:
                cursor.execute("""
                    SELECT 
                        c.name as category,
                        c.type,
                        SUM(CASE WHEN c.type = 'income' THEN t.debit ELSE t.credit END) as amount
                    FROM transactions t
                    JOIN monthly_records mr ON t.monthly_record_id = mr.id
                    LEFT JOIN categories c ON t.category_id = c.id
                    WHERE mr.user_id = %s AND mr.year = %s
                    GROUP BY c.id, c.name, c.type
                    ORDER BY amount DESC
                """, (user_id, year))
            
            breakdown = cursor.fetchall()
            return jsonify(breakdown)
            
        except Error as e:
            return jsonify({'error': str(e)}), 500
        finally:
            cursor.close()
            connection.close()
    
    return jsonify({'error': 'Database connection failed'}), 500

@app.route('/api/budget', methods=['GET', 'POST'])
@login_required
def budget():
    """Manage budget plans."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500
    
    cursor = connection.cursor(dictionary=True)
    user_id = session['user_id']
    
    try:
        if request.method == 'GET':
            year = request.args.get('year', datetime.now().year, type=int)
            month = request.args.get('month', datetime.now().month, type=int)
            
            cursor.execute("""
                SELECT 
                    bp.*,
                    c.name as category_name,
                    c.type as category_type,
                    COALESCE(
                        (SELECT SUM(CASE WHEN c.type = 'income' THEN t.debit ELSE t.credit END)
                         FROM transactions t
                         JOIN monthly_records mr ON t.monthly_record_id = mr.id
                         WHERE mr.user_id = %s AND mr.year = %s AND mr.month = %s
                         AND t.category_id = bp.category_id), 0
                    ) as actual_amount
                FROM budget_plans bp
                JOIN categories c ON bp.category_id = c.id
                WHERE bp.user_id = %s AND bp.year = %s AND bp.month = %s
            """, (user_id, year, month, user_id, year, month))
            
            budgets = cursor.fetchall()
            return jsonify(budgets)
        
        else:  # POST
            data = request.get_json()
            cursor.execute("""
                INSERT INTO budget_plans (user_id, category_id, year, month, planned_amount)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE planned_amount = %s
            """, (
                user_id,
                data.get('category_id'),
                data.get('year'),
                data.get('month'),
                data.get('planned_amount'),
                data.get('planned_amount')
            ))
            
            connection.commit()
            return jsonify({'message': 'Budget updated successfully'}), 201
            
    except Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()

@app.route('/api/payment-methods', methods=['GET', 'POST'])
@login_required
def payment_methods():
    """Get or create payment methods."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = connection.cursor(dictionary=True)
    user_id = session['user_id']

    try:
        if request.method == 'GET':
            cursor.execute("""
                SELECT * FROM payment_methods
                WHERE user_id = %s AND is_active = TRUE
                ORDER BY type, name
            """, (user_id,))

            methods = cursor.fetchall()
            return jsonify(methods)

        else:  # POST
            data = request.get_json()
            cursor.execute("""
                INSERT INTO payment_methods (user_id, name, type, color)
                VALUES (%s, %s, %s, %s)
            """, (
                user_id,
                data.get('name'),
                data.get('type', 'credit_card'),
                data.get('color', '#007bff')
            ))

            connection.commit()
            return jsonify({'message': 'Payment method added successfully', 'id': cursor.lastrowid}), 201

    except Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()

@app.route('/api/payment-methods/<int:method_id>', methods=['DELETE'])
@login_required
def delete_payment_method(method_id):
    """Delete a payment method."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = connection.cursor()

    try:
        cursor.execute("""
            UPDATE payment_methods
            SET is_active = FALSE
            WHERE id = %s AND user_id = %s
        """, (method_id, session['user_id']))

        connection.commit()
        return jsonify({'message': 'Payment method deleted successfully'})

    except Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()

@app.route('/api/transactions/<int:transaction_id>/mark-done', methods=['POST'])
@login_required
def mark_transaction_done(transaction_id):
    """Mark a transaction as done with payment method."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = connection.cursor()

    try:
        data = request.get_json()
        payment_method_id = data.get('payment_method_id')

        cursor.execute("""
            UPDATE transactions
            SET is_done = TRUE,
                payment_method_id = %s,
                marked_done_at = CURRENT_TIMESTAMP
            WHERE id = %s AND monthly_record_id IN
                (SELECT id FROM monthly_records WHERE user_id = %s)
        """, (payment_method_id, transaction_id, session['user_id']))

        connection.commit()
        return jsonify({'message': 'Transaction marked as done'})

    except Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()

@app.route('/api/transactions/<int:transaction_id>/mark-undone', methods=['POST'])
@login_required
def mark_transaction_undone(transaction_id):
    """Mark a transaction as not done."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = connection.cursor()

    try:
        cursor.execute("""
            UPDATE transactions
            SET is_done = FALSE,
                payment_method_id = NULL,
                marked_done_at = NULL
            WHERE id = %s AND monthly_record_id IN
                (SELECT id FROM monthly_records WHERE user_id = %s)
        """, (transaction_id, session['user_id']))

        connection.commit()
        return jsonify({'message': 'Transaction marked as not done'})

    except Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()

@app.route('/api/transactions/<int:transaction_id>/mark-paid', methods=['POST'])
@login_required
def mark_transaction_paid(transaction_id):
    """Mark a transaction as paid (when description cell is clicked)."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = connection.cursor()

    try:
        data = request.get_json()
        payment_method_id = data.get('payment_method_id')

        cursor.execute("""
            UPDATE transactions
            SET is_done = TRUE,
                is_paid = TRUE,
                payment_method_id = %s,
                marked_done_at = CURRENT_TIMESTAMP,
                paid_at = CURRENT_TIMESTAMP
            WHERE id = %s AND monthly_record_id IN
                (SELECT id FROM monthly_records WHERE user_id = %s)
        """, (payment_method_id, transaction_id, session['user_id']))

        connection.commit()
        return jsonify({'message': 'Transaction marked as paid'})

    except Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()

@app.route('/api/transactions/<int:transaction_id>/mark-unpaid', methods=['POST'])
@login_required
def mark_transaction_unpaid(transaction_id):
    """Unmark a transaction as paid (reverse the paid status)."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = connection.cursor()

    try:
        cursor.execute("""
            UPDATE transactions
            SET is_done = FALSE,
                is_paid = FALSE,
                payment_method_id = NULL,
                marked_done_at = NULL,
                paid_at = NULL
            WHERE id = %s AND monthly_record_id IN
                (SELECT id FROM monthly_records WHERE user_id = %s)
        """, (transaction_id, session['user_id']))

        connection.commit()
        return jsonify({'message': 'Transaction marked as unpaid'})

    except Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5003)
