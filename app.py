import os
import json
import logging
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
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

logger.info("Environment variables loaded")

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
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=365)  # Remember me for 1 year

# Session cookie configuration for mobile browser compatibility
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Allow cookies in same-site context
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevent JavaScript access for security
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True if using HTTPS in production
app.config['SESSION_COOKIE_NAME'] = 'session'  # Explicit session cookie name

CORS(app)

# Database configuration with proper type conversion and defaults
def get_db_config():
    """Get database configuration from environment variables."""
    host = os.environ.get('DB_HOST')
    port = os.environ.get('DB_PORT', '3306')  # Default MySQL port
    database = os.environ.get('DB_NAME')
    user = os.environ.get('DB_USER')
    password = os.environ.get('DB_PASSWORD')

    # Validate required fields
    if not all([host, database, user, password]):
        logger.error("Missing required database configuration in environment variables")
        logger.error(f"DB_HOST: {host}, DB_NAME: {database}, DB_USER: {user}, DB_PASSWORD: {'***' if password else None}")
        return None

    # Convert port to integer
    try:
        port_int = int(port)
    except (ValueError, TypeError):
        logger.error(f"Invalid DB_PORT value: {port}, using default 3306")
        port_int = 3306

    return {
        'host': host,
        'port': port_int,
        'database': database,
        'user': user,
        'password': password,
        'charset': 'utf8mb4',
        'use_unicode': True
    }

DB_CONFIG = get_db_config()

# Log database configuration status
if DB_CONFIG:
    logger.info(f"Database configuration loaded successfully")
    logger.info(f"DB Host: {DB_CONFIG['host']}, Port: {DB_CONFIG['port']}, Database: {DB_CONFIG['database']}")
else:
    logger.error("CRITICAL: Database configuration failed to load. Application may not function properly.")
    logger.error("Please check your .env file and ensure all required variables are set:")
    logger.error("Required: DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD")

def get_db_connection():
    """Create a database connection."""
    if DB_CONFIG is None:
        logger.error("Cannot connect to database: DB_CONFIG is not properly configured")
        return None

    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        logger.info("Database connection established successfully")
        return connection
    except Error as e:
        logger.error(f"Error connecting to MySQL: {e}")
        logger.error(f"DB_CONFIG: host={DB_CONFIG.get('host')}, port={DB_CONFIG.get('port')}, database={DB_CONFIG.get('database')}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error connecting to database: {e}", exc_info=True)
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

def admin_required(f):
    """Decorator to require admin privileges for routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first.', 'warning')
            return redirect(url_for('login'))

        # Check if user is admin
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            try:
                cursor.execute("SELECT is_admin FROM users WHERE id = %s", (session['user_id'],))
                user = cursor.fetchone()

                if not user or not user.get('is_admin'):
                    flash('Access denied. Admin privileges required.', 'danger')
                    return redirect(url_for('dashboard'))

            finally:
                cursor.close()
                connection.close()
        else:
            flash('Database connection failed.', 'danger')
            return redirect(url_for('dashboard'))

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
    """Landing page - redirect to login or dashboard/mobile based on device."""
    logger.info(f"Index route accessed - User logged in: {'user_id' in session}")
    if 'user_id' in session:
        # Detect if mobile device from user agent
        user_agent = request.headers.get('User-Agent', '').lower()
        is_mobile = any(device in user_agent for device in
                       ['android', 'webos', 'iphone', 'ipad', 'ipod', 'blackberry', 'windows phone'])

        if is_mobile:
            logger.info(f"Redirecting user {session.get('user_id')} to mobile view")
            return redirect(url_for('mobile'))
        logger.info(f"Redirecting user {session.get('user_id')} to dashboard")
        return redirect(url_for('dashboard'))
    logger.info("No user session found, redirecting to login")
    return redirect(url_for('login'))

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
        remember_me = data.get('remember_me', False)

        logger.info(f"Login attempt for username: {username}, remember_me: {remember_me}")

        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            try:
                # Check if username is an email or username
                cursor.execute("SELECT * FROM users WHERE username = %s OR email = %s",
                             (username, username))
                user = cursor.fetchone()

                if user and check_password_hash(user['password_hash'], password):
                    # Check if user account is active
                    if not user.get('is_active', True):
                        logger.warning(f"Login failed for username: {username} - Account is deactivated")
                        return jsonify({'error': 'Your account has been deactivated. Please contact an administrator.'}), 403

                    # Update last_login timestamp
                    cursor.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s", (user['id'],))
                    connection.commit()

                    # Set session as permanent if remember_me is checked
                    session.permanent = remember_me
                    session['user_id'] = user['id']
                    session['username'] = user['username']
                    session['is_admin'] = user.get('is_admin', False)
                    logger.info(f"Login successful for user: {username} (ID: {user['id']}), permanent: {remember_me}, is_admin: {user.get('is_admin', False)}")
                    return jsonify({'message': 'Login successful'}), 200
                else:
                    logger.warning(f"Login failed for username: {username} - Invalid credentials")
                    return jsonify({'error': 'Invalid credentials'}), 401
            except Error as e:
                logger.error(f"Database error during login: {str(e)}")
                return jsonify({'error': str(e)}), 500
            finally:
                cursor.close()
                connection.close()
        else:
            logger.error("Failed to establish database connection during login")
            return jsonify({'error': 'Database connection failed'}), 500

    return render_template('login.html')

@app.route('/logout')
def logout():
    """User logout."""
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/api/change-password', methods=['POST'])
@login_required
def change_password():
    """Change user password."""
    data = request.get_json()
    current_password = data.get('current_password')
    new_password = data.get('new_password')

    if not current_password or not new_password:
        return jsonify({'error': 'Current and new passwords are required'}), 400

    if len(new_password) < 6:
        return jsonify({'error': 'New password must be at least 6 characters long'}), 400

    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = connection.cursor(dictionary=True)
    user_id = session['user_id']

    try:
        # Get current user
        cursor.execute("SELECT password_hash FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()

        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Verify current password
        if not check_password_hash(user['password_hash'], current_password):
            return jsonify({'error': 'Current password is incorrect'}), 401

        # Update password
        new_password_hash = generate_password_hash(new_password)
        cursor.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s",
            (new_password_hash, user_id)
        )
        connection.commit()

        return jsonify({'message': 'Password changed successfully'}), 200

    except Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()

@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard."""
    return render_template('dashboard.html', username=session.get('username'))

@app.route('/mobile')
@login_required
def mobile():
    """Mobile view."""
    return render_template('mobile.html', username=session.get('username'))

@app.route('/admin')
@admin_required
def admin_dashboard():
    """Admin dashboard."""
    return render_template('admin.html', username=session.get('username'))

@app.route('/api/admin/users', methods=['GET'])
@admin_required
def get_all_users():
    """Get all users with their details."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                u.id,
                u.username,
                u.email,
                u.is_admin,
                u.is_active,
                u.last_login,
                u.created_at,
                COUNT(DISTINCT mr.id) as monthly_records_count,
                COUNT(DISTINCT t.id) as transactions_count
            FROM users u
            LEFT JOIN monthly_records mr ON u.id = mr.user_id
            LEFT JOIN transactions t ON mr.id = t.monthly_record_id
            GROUP BY u.id, u.username, u.email, u.is_admin, u.is_active, u.last_login, u.created_at
            ORDER BY u.created_at DESC
        """)

        users = cursor.fetchall()
        return jsonify(users)

    except Error as e:
        logger.error(f"Error fetching users: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()

def log_audit(admin_user_id, action, target_user_id=None, details=None):
    """Helper function to log admin actions."""
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor()
        try:
            cursor.execute("""
                INSERT INTO audit_logs (admin_user_id, action, target_user_id, details)
                VALUES (%s, %s, %s, %s)
            """, (admin_user_id, action, target_user_id, details))
            connection.commit()
        except Error as e:
            logger.error(f"Error logging audit: {str(e)}")
        finally:
            cursor.close()
            connection.close()

@app.route('/api/admin/users/<int:user_id>/toggle-active', methods=['POST'])
@admin_required
def toggle_user_active(user_id):
    """Activate or deactivate a user."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = connection.cursor(dictionary=True)
    admin_id = session['user_id']

    try:
        # Prevent admin from deactivating themselves
        if user_id == admin_id:
            return jsonify({'error': 'You cannot deactivate your own account'}), 400

        # Get current user status
        cursor.execute("SELECT username, is_active FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()

        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Toggle active status
        new_status = not user['is_active']
        cursor.execute("UPDATE users SET is_active = %s WHERE id = %s", (new_status, user_id))
        connection.commit()

        # Log the action
        action = f"{'Activated' if new_status else 'Deactivated'} user"
        log_audit(admin_id, action, user_id, f"User '{user['username']}' status changed to {'active' if new_status else 'inactive'}")

        logger.info(f"Admin {admin_id} {action.lower()} user {user_id} ({user['username']})")

        return jsonify({
            'message': f"User {'activated' if new_status else 'deactivated'} successfully",
            'is_active': new_status
        })

    except Error as e:
        logger.error(f"Error toggling user active status: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()

@app.route('/api/admin/users/<int:user_id>/toggle-admin', methods=['POST'])
@admin_required
def toggle_user_admin(user_id):
    """Grant or revoke admin privileges."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = connection.cursor(dictionary=True)
    admin_id = session['user_id']

    try:
        # Prevent admin from revoking their own admin status
        if user_id == admin_id:
            return jsonify({'error': 'You cannot modify your own admin status'}), 400

        # Get current user status
        cursor.execute("SELECT username, is_admin FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()

        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Toggle admin status
        new_status = not user['is_admin']
        cursor.execute("UPDATE users SET is_admin = %s WHERE id = %s", (new_status, user_id))
        connection.commit()

        # Log the action
        action = f"{'Granted' if new_status else 'Revoked'} admin privileges"
        log_audit(admin_id, action, user_id, f"User '{user['username']}' admin status changed to {new_status}")

        logger.info(f"Admin {admin_id} {action.lower()} for user {user_id} ({user['username']})")

        return jsonify({
            'message': f"Admin privileges {'granted' if new_status else 'revoked'} successfully",
            'is_admin': new_status
        })

    except Error as e:
        logger.error(f"Error toggling user admin status: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()

@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    """Delete a user and all their data."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = connection.cursor(dictionary=True)
    admin_id = session['user_id']

    try:
        # Prevent admin from deleting themselves
        if user_id == admin_id:
            return jsonify({'error': 'You cannot delete your own account'}), 400

        # Get user details before deletion
        cursor.execute("SELECT username, email FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()

        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Delete user (cascading will handle related records)
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        connection.commit()

        # Log the action
        log_audit(admin_id, 'Deleted user', None, f"User '{user['username']}' ({user['email']}) permanently deleted")

        logger.info(f"Admin {admin_id} deleted user {user_id} ({user['username']})")

        return jsonify({'message': 'User deleted successfully'})

    except Error as e:
        logger.error(f"Error deleting user: {str(e)}")
        connection.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()

@app.route('/api/admin/audit-logs', methods=['GET'])
@admin_required
def get_audit_logs():
    """Get audit logs of admin actions."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = connection.cursor(dictionary=True)

    try:
        limit = request.args.get('limit', 100, type=int)

        cursor.execute("""
            SELECT
                al.id,
                al.action,
                al.details,
                al.created_at,
                au.username as admin_username,
                tu.username as target_username
            FROM audit_logs al
            JOIN users au ON al.admin_user_id = au.id
            LEFT JOIN users tu ON al.target_user_id = tu.id
            ORDER BY al.created_at DESC
            LIMIT %s
        """, (limit,))

        logs = cursor.fetchall()
        return jsonify(logs)

    except Error as e:
        logger.error(f"Error fetching audit logs: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()

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
            
            # Get current month income and expenses
            cursor.execute("""
                SELECT
                    SUM(debit) as total_income,
                    SUM(credit) as total_expenses
                FROM transactions t
                JOIN monthly_records mr ON t.monthly_record_id = mr.id
                WHERE mr.user_id = %s AND mr.year = %s AND mr.month = %s
            """, (user_id, current_year, current_month))

            current_stats = cursor.fetchone() or {'total_income': 0, 'total_expenses': 0}

            # Balance will be calculated on frontend
            current_stats['current_balance'] = (current_stats.get('total_income', 0) or 0) - (current_stats.get('total_expenses', 0) or 0)
            
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
            
            # Get recent transactions (balance will be calculated on frontend)
            cursor.execute("""
                SELECT
                    t.description,
                    t.debit,
                    t.credit,
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
                    ORDER BY t.id DESC
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

            # Convert to Decimal to avoid float/Decimal arithmetic errors
            debit_value = data.get('debit')
            credit_value = data.get('credit')

            debit = Decimal(str(debit_value)) if debit_value else Decimal('0')
            credit = Decimal(str(credit_value)) if credit_value else Decimal('0')

            print(f"[DEBUG] Debit: {debit}, Credit: {credit}")

            # Use current date if no transaction_date provided
            transaction_date = data.get('transaction_date')
            if not transaction_date:
                transaction_date = datetime.now().date()

            # Insert transaction (balance will be calculated on frontend)
            insert_values = (
                monthly_record['id'],
                data.get('description'),
                data.get('category_id'),
                debit if debit > 0 else None,
                credit if credit > 0 else None,
                transaction_date,
                data.get('notes')
            )
            print(f"[DEBUG] Inserting transaction with values: {insert_values}")

            cursor.execute("""
                INSERT INTO transactions
                (monthly_record_id, description, category_id, debit, credit, transaction_date, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
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

            # Validate request data
            if not data:
                return jsonify({'error': 'No data provided'}), 400

            print(f"[DEBUG] Updating transaction {transaction_id} with data: {data}")

            # Get the monthly_record_id for this transaction
            cursor.execute("""
                SELECT monthly_record_id FROM transactions
                WHERE id = %s AND monthly_record_id IN
                    (SELECT id FROM monthly_records WHERE user_id = %s)
            """, (transaction_id, session['user_id']))

            result = cursor.fetchone()
            if not result:
                print(f"[DEBUG] Transaction {transaction_id} not found for user {session['user_id']}")
                return jsonify({'error': 'Transaction not found'}), 404

            monthly_record_id = result[0]
            print(f"[DEBUG] Found monthly_record_id: {monthly_record_id}")

            # Convert to Decimal to avoid float/Decimal arithmetic errors
            debit_value = data.get('debit')
            credit_value = data.get('credit')

            debit = Decimal(str(debit_value)) if debit_value else Decimal('0')
            credit = Decimal(str(credit_value)) if credit_value else Decimal('0')

            print(f"[DEBUG] Debit: {debit}, Credit: {credit}")

            # Handle transaction_date - use current date if not provided or empty
            transaction_date = data.get('transaction_date')
            if not transaction_date or transaction_date == '':
                transaction_date = datetime.now().date()

            # Update transaction (balance will be calculated on frontend)
            cursor.execute("""
                UPDATE transactions
                SET description = %s, category_id = %s, debit = %s,
                    credit = %s, transaction_date = %s, notes = %s
                WHERE id = %s
            """, (
                data.get('description'),
                data.get('category_id'),
                debit if debit > 0 else None,
                credit if credit > 0 else None,
                transaction_date,
                data.get('notes'),
                transaction_id
            ))

            print(f"[DEBUG] Transaction {transaction_id} updated successfully")

            connection.commit()
            print(f"[DEBUG] Transaction update committed successfully")
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
        print(f"[ERROR] Database error in manage_transaction: {str(e)}")
        connection.rollback()
        return jsonify({'error': f'Database error: {str(e)}'}), 500
    except Exception as e:
        print(f"[ERROR] Unexpected error in manage_transaction: {str(e)}")
        connection.rollback()
        return jsonify({'error': f'Server error: {str(e)}'}), 500
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

@app.route('/api/recalculate-balances', methods=['POST'])
@login_required
def recalculate_balances():
    """Deprecated: Balance calculation now happens on frontend."""
    return jsonify({
        'message': 'Balance calculation now happens on frontend',
        'transactions_updated': 0
    })

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

@app.route('/api/payment-method-totals', methods=['GET'])
@login_required
def get_payment_method_totals():
    """Get totals for each payment method for the current month."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = connection.cursor(dictionary=True)
    user_id = session['user_id']

    try:
        year = request.args.get('year', datetime.now().year, type=int)
        month = request.args.get('month', datetime.now().month, type=int)

        # Get monthly record
        cursor.execute("""
            SELECT id FROM monthly_records
            WHERE user_id = %s AND year = %s AND month = %s
        """, (user_id, year, month))

        monthly_record = cursor.fetchone()

        if not monthly_record:
            return jsonify([])

        # Get totals by payment method
        cursor.execute("""
            SELECT
                pm.id,
                pm.name,
                pm.type,
                pm.color,
                COUNT(t.id) as transaction_count,
                SUM(t.debit) as total_debit,
                SUM(t.credit) as total_credit,
                SUM(COALESCE(t.debit, 0) - COALESCE(t.credit, 0)) as net_amount
            FROM payment_methods pm
            LEFT JOIN transactions t ON pm.id = t.payment_method_id
                AND t.monthly_record_id = %s
                AND t.is_done = TRUE
            WHERE pm.user_id = %s AND pm.is_active = TRUE
            GROUP BY pm.id, pm.name, pm.type, pm.color
            ORDER BY pm.type, pm.name
        """, (monthly_record['id'], user_id))

        totals = cursor.fetchall()
        return jsonify(totals)

    except Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()

@app.route('/api/clone-month-transactions', methods=['POST'])
@login_required
def clone_month_transactions():
    """Clone all transactions from one month to another."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = connection.cursor(dictionary=True)
    user_id = session['user_id']

    try:
        data = request.get_json()
        from_year = data.get('from_year')
        from_month = data.get('from_month')
        to_year = data.get('to_year')
        to_month = data.get('to_month')
        include_payments = data.get('include_payments', False)

        # Validate inputs
        if not all([from_year, from_month, to_year, to_month]):
            return jsonify({'error': 'All date fields are required'}), 400

        if from_year == to_year and from_month == to_month:
            return jsonify({'error': 'Source and target months cannot be the same'}), 400

        # Get source monthly record
        cursor.execute("""
            SELECT id FROM monthly_records
            WHERE user_id = %s AND year = %s AND month = %s
        """, (user_id, from_year, from_month))

        source_record = cursor.fetchone()

        if not source_record:
            return jsonify({'error': 'Source month has no transactions'}), 404

        # Get or create target monthly record
        month_name = calendar.month_name[to_month]
        cursor.execute("""
            INSERT INTO monthly_records (user_id, year, month, month_name)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE updated_at = CURRENT_TIMESTAMP
        """, (user_id, to_year, to_month, month_name))

        cursor.execute("""
            SELECT id FROM monthly_records
            WHERE user_id = %s AND year = %s AND month = %s
        """, (user_id, to_year, to_month))

        target_record = cursor.fetchone()

        # Get all transactions from source month
        cursor.execute("""
            SELECT description, category_id, debit, credit, notes,
                   payment_method_id, is_done, is_paid
            FROM transactions
            WHERE monthly_record_id = %s
            ORDER BY id
        """, (source_record['id'],))

        source_transactions = cursor.fetchall()

        if not source_transactions:
            return jsonify({'error': 'No transactions found in source month'}), 404

        # Clone transactions (balance will be calculated on frontend)
        cloned_count = 0

        for trans in source_transactions:
            debit = Decimal(str(trans['debit'])) if trans['debit'] else Decimal('0')
            credit = Decimal(str(trans['credit'])) if trans['credit'] else Decimal('0')

            # Set payment fields based on checkbox
            payment_method_id = trans['payment_method_id'] if include_payments else None
            is_done = trans['is_done'] if include_payments else False
            is_paid = trans['is_paid'] if include_payments else False

            cursor.execute("""
                INSERT INTO transactions
                (monthly_record_id, description, category_id, debit, credit,
                 transaction_date, notes, payment_method_id, is_done, is_paid)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                target_record['id'],
                trans['description'],
                trans['category_id'],
                debit if debit > 0 else None,
                credit if credit > 0 else None,
                datetime.now().date(),  # Use current date for cloned transactions
                trans['notes'],
                payment_method_id,
                is_done,
                is_paid
            ))

            cloned_count += 1

        connection.commit()

        return jsonify({
            'message': f'Successfully cloned {cloned_count} transactions',
            'count': cloned_count
        }), 200

    except Error as e:
        connection.rollback()
        logger.error(f"Error cloning transactions: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()

# Global error handlers (must be outside if __name__ block)
@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {str(error)}")
    # For API requests, return JSON
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Internal server error'}), 500
    # For page requests, render error template or return HTML
    return render_template('error.html', error_code=500, error_message='Internal Server Error'), 500

@app.errorhandler(404)
def not_found(error):
    logger.warning(f"404 error: {request.path}")
    # For API requests, return JSON
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Not found'}), 404
    # For page requests, redirect to dashboard or login
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.errorhandler(Exception)
def handle_exception(error):
    logger.error(f"Unhandled exception: {str(error)}", exc_info=True)
    # For API requests, return JSON
    if request.path.startswith('/api/'):
        return jsonify({'error': 'An unexpected error occurred'}), 500
    # For page requests, render error template
    return render_template('error.html', error_code=500, error_message='An unexpected error occurred'), 500

if __name__ == '__main__':
    logger.info("Starting Personal Finance Budget application...")
    logger.info(f"Debug mode: False (Production)")
    logger.info(f"Host: 0.0.0.0, Port: 5003")

    # Use debug=False for production
    # Set to True for development (detailed error messages)
    app.run(debug=False, host='0.0.0.0', port=5003)
