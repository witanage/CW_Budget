import calendar
import csv
import io
import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from decimal import Decimal
from functools import wraps

import mysql.connector
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, make_response
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS
from mysql.connector import Error
from werkzeug.security import generate_password_hash, check_password_hash

from apscheduler.schedulers.background import BackgroundScheduler
from services.hnb_exchange_rate_service import get_hnb_exchange_rate_service
from services.pb_exchange_rate_service import get_pb_exchange_rate_service

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Try importing optional dependencies
try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill

    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False
    logger.warning("openpyxl not installed. Excel export will use CSV format.")

try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet

    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    logger.warning("reportlab not installed. PDF export will use text format.")

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
        logger.error(
            f"DB_HOST: {host}, DB_NAME: {database}, DB_USER: {user}, DB_PASSWORD: {'***' if password else None}")
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

# Scheduler instance — assigned in the __main__ block; referenced by the hourly job
# so it can reschedule itself when the interval setting changes.
scheduler = None

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
        logger.error(
            f"DB_CONFIG: host={DB_CONFIG.get('host')}, port={DB_CONFIG.get('port')}, database={DB_CONFIG.get('database')}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error connecting to database: {e}", exc_info=True)
        return None


def get_setting(key, default=None):
    """Read a single value from the app_settings table. Returns *default* when
    the table does not exist yet, the key is missing, or the DB is unreachable."""
    connection = get_db_connection()
    if not connection:
        return default
    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT value FROM app_settings WHERE setting_key = %s", (key,))
        row = cursor.fetchone()
        return row['value'] if row else default
    except Exception as e:
        logger.warning(f"get_setting('{key}'): {e} — using default {default}")
        return default
    finally:
        if cursor:
            cursor.close()
        connection.close()


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


def log_transaction_audit(cursor, transaction_id, user_id, action, field_name=None, old_value=None, new_value=None):
    """
    Log transaction changes to audit trail.

    Args:
        cursor: Database cursor
        transaction_id: ID of the transaction (None for DELETE after completion)
        user_id: ID of the user making the change
        action: Type of action (CREATE, UPDATE, DELETE)
        field_name: Name of the field changed (None for CREATE/DELETE)
        old_value: Previous value (None for CREATE)
        new_value: New value (None for DELETE)
    """
    try:
        # Get request metadata
        ip_address = request.remote_addr if request else None
        user_agent = request.headers.get('User-Agent') if request else None

        # Convert values to strings for storage
        old_value_str = str(old_value) if old_value is not None else None
        new_value_str = str(new_value) if new_value is not None else None

        cursor.execute("""
                       INSERT INTO transaction_audit_logs
                       (transaction_id, user_id, action, field_name, old_value, new_value, ip_address, user_agent)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                       """, (transaction_id, user_id, action, field_name, old_value_str, new_value_str, ip_address,
                             user_agent))

        logger.info(f"Audit log created: {action} on transaction {transaction_id} by user {user_id}")
    except Exception as e:
        logger.error(f"Failed to create audit log: {e}")
        # Don't fail the main transaction if audit logging fails


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

                # Create new user (deactivated by default, requires admin activation)
                password_hash = generate_password_hash(password)
                cursor.execute(
                    "INSERT INTO users (username, email, password_hash, is_active) VALUES (%s, %s, %s, %s)",
                    (username, email, password_hash, False)
                )
                connection.commit()

                logger.info(f"New user registered: {username} ({email}) - Account created in deactivated state")

                return jsonify({'message': 'Registration successful. Your account is pending admin approval.'}), 201
            except Error as e:
                return jsonify({'error': str(e)}), 500
            finally:
                cursor.close()
                connection.close()

        return jsonify({'error': 'Database connection failed'}), 500

    return render_template('register.html')


def refresh_all_exchange_rates(force=False):
    """Fetch today's exchange rates from all banks and cache in the database.

    Called by the background scheduler every *interval* minutes.  When the
    admin switches the mode to ``manual`` the scheduler still fires but the
    function returns immediately — unless *force* is ``True`` (used by the
    admin "Refresh All" endpoint).
    """
    if not force:
        mode = get_setting('exchange_rate_refresh_mode', 'background')
        if mode != 'background':
            logger.info("Scheduler: refresh mode is '%s' — skipping automatic refresh.", mode)
            return

    logger.info("Scheduler: Starting exchange rate refresh (force=%s)...", force)

    results = {}

    # HNB
    hnb_start = time.time()
    try:
        hnb_service = get_hnb_exchange_rate_service()
        hnb_rate = hnb_service.fetch_and_store_current_rate()
        hnb_ms = int((time.time() - hnb_start) * 1000)
        if hnb_rate:
            logger.info(f"Scheduler: HNB rate updated: Buy={hnb_rate['buy_rate']}, Sell={hnb_rate['sell_rate']}")
            log_exchange_rate_refresh('HNB', 'success',
                                     buy_rate=hnb_rate['buy_rate'],
                                     sell_rate=hnb_rate['sell_rate'],
                                     duration_ms=hnb_ms)
            results['HNB'] = {'status': 'success', 'buy_rate': hnb_rate['buy_rate'], 'sell_rate': hnb_rate['sell_rate']}
        else:
            logger.warning("Scheduler: Failed to fetch HNB rate")
            log_exchange_rate_refresh('HNB', 'failure',
                                     error_message='No rate returned by HNB API',
                                     duration_ms=hnb_ms)
            results['HNB'] = {'status': 'failure', 'error': 'No rate returned by HNB API'}
    except Exception as e:
        logger.error(f"Scheduler: Error fetching HNB rate: {str(e)}")
        log_exchange_rate_refresh('HNB', 'failure',
                                 error_message=str(e),
                                 duration_ms=int((time.time() - hnb_start) * 1000))
        results['HNB'] = {'status': 'failure', 'error': str(e)}

    # People's Bank
    pb_start = time.time()
    try:
        pb_service = get_pb_exchange_rate_service()
        pb_rate = pb_service.fetch_and_store_current_rate()
        pb_ms = int((time.time() - pb_start) * 1000)
        if pb_rate:
            logger.info(f"Scheduler: PB rate updated: Buy={pb_rate['buy_rate']}, Sell={pb_rate['sell_rate']}")
            log_exchange_rate_refresh('PB', 'success',
                                     buy_rate=pb_rate['buy_rate'],
                                     sell_rate=pb_rate['sell_rate'],
                                     duration_ms=pb_ms)
            results['PB'] = {'status': 'success', 'buy_rate': pb_rate['buy_rate'], 'sell_rate': pb_rate['sell_rate']}
        else:
            logger.warning("Scheduler: Failed to fetch PB rate")
            log_exchange_rate_refresh('PB', 'failure',
                                     error_message='No rate returned by PB scraper',
                                     duration_ms=pb_ms)
            results['PB'] = {'status': 'failure', 'error': 'No rate returned by PB scraper'}
    except Exception as e:
        logger.error(f"Scheduler: Error fetching PB rate: {str(e)}")
        log_exchange_rate_refresh('PB', 'failure',
                                 error_message=str(e),
                                 duration_ms=int((time.time() - pb_start) * 1000))
        results['PB'] = {'status': 'failure', 'error': str(e)}

    # CBSL (for today)
    cbsl_start = time.time()
    try:
        from services.exchange_rate_service import get_exchange_rate_service
        cbsl_service = get_exchange_rate_service()
        cbsl_rate = cbsl_service.get_exchange_rate(datetime.now())
        cbsl_ms = int((time.time() - cbsl_start) * 1000)
        if cbsl_rate:
            logger.info(f"Scheduler: CBSL rate for today: Buy={cbsl_rate['buy_rate']}, Sell={cbsl_rate['sell_rate']}")
            log_exchange_rate_refresh('CBSL', 'success',
                                     buy_rate=cbsl_rate['buy_rate'],
                                     sell_rate=cbsl_rate['sell_rate'],
                                     duration_ms=cbsl_ms)
            results['CBSL'] = {'status': 'success', 'buy_rate': cbsl_rate['buy_rate'], 'sell_rate': cbsl_rate['sell_rate']}
        else:
            logger.warning("Scheduler: No CBSL rate available for today")
            log_exchange_rate_refresh('CBSL', 'failure',
                                     error_message='No CBSL rate available for today',
                                     duration_ms=cbsl_ms)
            results['CBSL'] = {'status': 'failure', 'error': 'No CBSL rate available for today'}
    except Exception as e:
        logger.error(f"Scheduler: Error fetching CBSL rate: {str(e)}")
        log_exchange_rate_refresh('CBSL', 'failure',
                                 error_message=str(e),
                                 duration_ms=int((time.time() - cbsl_start) * 1000))
        results['CBSL'] = {'status': 'failure', 'error': str(e)}

    # Check whether the admin changed the interval since the last run.
    # reschedule_job() is a no-op-equivalent when the value hasn't changed.
    if scheduler:
        try:
            new_minutes = int(get_setting('exchange_rate_refresh_interval_minutes', '60'))
            job = scheduler.get_job('refresh_exchange_rates')
            if job:
                current_minutes = int(job.trigger.interval.total_seconds() // 60)
                if new_minutes != current_minutes:
                    scheduler.reschedule_job('refresh_exchange_rates', trigger='interval', minutes=new_minutes)
                    logger.info(f"Scheduler: Interval changed {current_minutes} -> {new_minutes} min")
        except Exception as e:
            logger.error(f"Scheduler: Error checking interval setting: {str(e)}")

    logger.info("Scheduler: Exchange rate refresh completed — results: %s", results)
    return results


def _resolve_rate(service, date):
    """Return today's rate from *service*, using the live-fetch-on-miss path
    when the refresh mode is ``manual``.

    In *background* mode the scheduler keeps the cache warm so a plain
    DB read is sufficient.  In *manual* mode nothing populates the cache
    automatically, so we delegate to ``get_or_fetch_rate`` which hits the
    cache first and falls back to the 3rd-party source only for today's
    date.  CBSL's ``get_exchange_rate`` already does live-fetch internally,
    so no special branch is needed for that source.
    """
    mode = get_setting('exchange_rate_refresh_mode', 'background')
    if mode == 'manual' and hasattr(service, 'get_or_fetch_rate'):
        return service.get_or_fetch_rate(date)
    return service.get_exchange_rate(date)


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
                        return jsonify(
                            {'error': 'Your account has been deactivated. Please contact an administrator.'}), 403

                    # Update last_login timestamp
                    cursor.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s", (user['id'],))
                    connection.commit()

                    # Set session as permanent if remember_me is checked
                    session.permanent = remember_me
                    session['user_id'] = user['id']
                    session['username'] = user['username']
                    session['is_admin'] = user.get('is_admin', False)
                    logger.info(
                        f"Login successful for user: {username} (ID: {user['id']}), permanent: {remember_me}, is_admin: {user.get('is_admin', False)}")

                    # Start background task to populate exchange rates (CBSL + HNB)
                    background_thread = threading.Thread(target=populate_all_exchange_rates_background, daemon=True)
                    background_thread.start()
                    logger.info("Background task started to populate CBSL and HNB exchange rates")

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


# ==================================================
# LOGIN BACKGROUND TASK - CBSL HISTORICAL RATES
# ==================================================

def populate_all_exchange_rates_background():
    """
    Background task to populate missing CBSL historical exchange rates.
    Runs in a separate thread after user login.

    HNB and People's Bank rates are handled by the hourly scheduler.
    """
    try:
        logger.info("Background task: Starting CBSL exchange rate population...")

        # ===== PART 1: CBSL RATES (existing logic) =====
        from services.exchange_rate_service import get_exchange_rate_service

        cbsl_service = get_exchange_rate_service()

        # Check if database is empty
        if cbsl_service._is_database_empty():
            logger.info("Background task: Database is empty, triggering CBSL bulk import...")
            success = cbsl_service._fetch_and_import_bulk_csv()
            if success:
                logger.info("Background task: CBSL bulk import completed successfully")
            else:
                logger.warning("Background task: CBSL bulk import failed")
        else:
            # Database has data, check last 10 days for missing CBSL dates
            logger.info("Background task: Checking last 10 days for missing CBSL exchange rates...")

            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=10)

            # Get existing dates in the last 10 days
            connection = mysql.connector.connect(
                host=os.environ.get('DB_HOST', 'localhost'),
                port=int(os.environ.get('DB_PORT', 3306)),
                user=os.environ.get('DB_USER', 'root'),
                password=os.environ.get('DB_PASSWORD', ''),
                database=os.environ.get('DB_NAME', 'budget_app')
            )
            cursor = connection.cursor()
            cursor.execute("""
                           SELECT date
                           FROM exchange_rates
                           WHERE date BETWEEN %s
                             AND %s
                             AND source IN ('CBSL', 'CBSL_BULK')
                           """, (start_date, end_date))

            existing_dates = {row[0] for row in cursor.fetchall()}
            cursor.close()
            connection.close()

            # Find missing dates in the last 10 days
            current_date = start_date
            missing_dates = []
            while current_date <= end_date:
                if current_date not in existing_dates:
                    missing_dates.append(current_date)
                current_date += timedelta(days=1)

            if missing_dates:
                logger.info(f"Background task: Found {len(missing_dates)} missing CBSL dates in last 10 days")

                # Fetch each missing date
                fetched = 0
                failed = 0
                for date in missing_dates:
                    try:
                        rate = cbsl_service.get_exchange_rate(datetime.combine(date, datetime.min.time()))
                        if rate:
                            fetched += 1
                        else:
                            failed += 1
                    except Exception as e:
                        logger.error(f"Background task: Error fetching CBSL rate for {date}: {str(e)}")
                        failed += 1

                logger.info(f"Background task: CBSL completed - {fetched} fetched, {failed} failed")
            else:
                logger.info("Background task: No missing CBSL dates in last 10 days")

        logger.info("Background task: CBSL exchange rate population completed")

    except Exception as e:
        logger.error(f"Background task: Error populating exchange rates: {str(e)}", exc_info=True)


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
    """Admin dashboard with server-side data."""
    connection = get_db_connection()
    users = []
    audit_logs = []
    settings = {}
    error_message = None

    if connection:
        cursor = connection.cursor(dictionary=True)
        try:
            # Fetch users
            cursor.execute("""
                           SELECT u.id,
                                  u.username,
                                  u.email,
                                  u.is_admin,
                                  u.is_active,
                                  u.last_login,
                                  u.created_at,
                                  COUNT(DISTINCT mr.id) as monthly_records_count,
                                  COUNT(DISTINCT t.id)  as transactions_count
                           FROM users u
                                    LEFT JOIN monthly_records mr ON u.id = mr.user_id
                                    LEFT JOIN transactions t ON mr.id = t.monthly_record_id
                           GROUP BY u.id, u.username, u.email, u.is_admin, u.is_active, u.last_login, u.created_at
                           ORDER BY u.created_at DESC
                           """)
            users = cursor.fetchall()

            # Fetch audit logs
            cursor.execute("""
                           SELECT al.id,
                                  al.action,
                                  al.details,
                                  al.created_at,
                                  au.username as admin_username,
                                  tu.username as target_username
                           FROM audit_logs al
                                    JOIN users au ON al.admin_user_id = au.id
                                    LEFT JOIN users tu ON al.target_user_id = tu.id
                           ORDER BY al.created_at DESC LIMIT 50
                           """)
            audit_logs = cursor.fetchall()

            # Fetch app settings
            cursor.execute("SELECT setting_key, value, description FROM app_settings ORDER BY setting_key")
            settings = {row['setting_key']: row for row in cursor.fetchall()}

        except Error as e:
            logger.error(f"Error fetching admin data: {str(e)}")
            error_message = str(e)
        finally:
            cursor.close()
            connection.close()
    else:
        error_message = "Database connection failed"

    return render_template('admin.html',
                           username=session.get('username'),
                           users=users,
                           audit_logs=audit_logs,
                           settings=settings,
                           error_message=error_message,
                           current_user_id=session.get('user_id'))


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
                       SELECT u.id,
                              u.username,
                              u.email,
                              u.is_admin,
                              u.is_active,
                              u.last_login,
                              u.created_at,
                              COUNT(DISTINCT mr.id) as monthly_records_count,
                              COUNT(DISTINCT t.id)  as transactions_count
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


def log_exchange_rate_refresh(source, status, buy_rate=None, sell_rate=None, error_message=None, duration_ms=None):
    """Write one row to exchange_rate_refresh_logs for a single source attempt."""
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor()
        try:
            cursor.execute("""
                INSERT INTO exchange_rate_refresh_logs
                    (source, status, buy_rate, sell_rate, error_message, duration_ms)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (source, status, buy_rate, sell_rate, error_message, duration_ms))
            connection.commit()
        except Error as e:
            logger.error(f"Error writing exchange_rate_refresh_logs: {str(e)}")
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
        log_audit(admin_id, action, user_id,
                  f"User '{user['username']}' status changed to {'active' if new_status else 'inactive'}")

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
                       SELECT al.id,
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


@app.route('/api/admin/settings', methods=['GET'])
@admin_required
def get_admin_settings():
    """Get all application settings."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT setting_key, value, description, updated_at FROM app_settings ORDER BY setting_key")
        settings = cursor.fetchall()
        for row in settings:
            if row.get('updated_at'):
                row['updated_at'] = str(row['updated_at'])
        return jsonify(settings), 200
    except Error as e:
        logger.error(f"Error fetching settings: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


@app.route('/api/admin/settings/<string:key>', methods=['PUT'])
@admin_required
def update_admin_setting(key):
    """Update a single application setting.  Only keys that already exist in
    app_settings may be written — arbitrary keys are rejected."""
    data = request.get_json()
    if not data or 'value' not in data:
        return jsonify({'error': "'value' field is required"}), 400

    new_value = str(data['value'])

    # Key-specific validation
    if key == 'exchange_rate_refresh_interval_minutes':
        try:
            interval = int(new_value)
            if interval < 1:
                return jsonify({'error': 'Interval must be at least 1 minute'}), 400
            new_value = str(interval)
        except (ValueError, TypeError):
            return jsonify({'error': 'Interval must be a positive integer'}), 400

    if key == 'exchange_rate_refresh_mode':
        if new_value not in ('background', 'manual'):
            return jsonify({'error': "Value must be 'background' or 'manual'"}), 400

    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = connection.cursor(dictionary=True)
    try:
        # Guard: only allow updating pre-existing keys
        cursor.execute("SELECT setting_key FROM app_settings WHERE setting_key = %s", (key,))
        if not cursor.fetchone():
            return jsonify({'error': f'Unknown setting: {key}'}), 404

        cursor.execute("UPDATE app_settings SET value = %s WHERE setting_key = %s", (new_value, key))
        connection.commit()

        username = session.get('username')
        logger.info(f"Admin setting updated: {key} = {new_value} (by {username})")
        log_audit(session['user_id'], 'UPDATE_SETTING', details=f'{key} = {new_value}')

        return jsonify({'message': 'Setting updated', 'key': key, 'value': new_value}), 200
    except Error as e:
        logger.error(f"Error updating setting '{key}': {str(e)}")
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
                           SELECT SUM(debit)  as total_income,
                                  SUM(credit) as total_expenses
                           FROM transactions t
                                    JOIN monthly_records mr ON t.monthly_record_id = mr.id
                           WHERE mr.user_id = %s
                             AND mr.year = %s
                             AND mr.month = %s
                           """, (user_id, current_year, current_month))

            current_stats = cursor.fetchone() or {'total_income': 0, 'total_expenses': 0}

            # Balance will be calculated on frontend
            current_stats['current_balance'] = (current_stats.get('total_income', 0) or 0) - (
                        current_stats.get('total_expenses', 0) or 0)

            # Get year-to-date stats
            cursor.execute("""
                           SELECT SUM(debit)  as ytd_income,
                                  SUM(credit) as ytd_expenses
                           FROM transactions t
                                    JOIN monthly_records mr ON t.monthly_record_id = mr.id
                           WHERE mr.user_id = %s
                             AND mr.year = %s
                           """, (user_id, current_year))

            ytd_stats = cursor.fetchone()

            # Get recent transactions (balance will be calculated on frontend)
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

            # Get monthly trend (last 12 months)
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

            # Get current month income by category
            cursor.execute("""
                           SELECT c.name       as category,
                                  SUM(t.debit) as amount
                           FROM transactions t
                                    JOIN monthly_records mr ON t.monthly_record_id = mr.id
                                    LEFT JOIN categories c ON t.category_id = c.id
                           WHERE mr.user_id = %s
                             AND mr.year = %s
                             AND mr.month = %s
                             AND t.debit > 0
                           GROUP BY c.name
                           ORDER BY amount DESC LIMIT 5
                           """, (user_id, current_year, current_month))

            income_categories = cursor.fetchall()

            # Get current month expenses by category
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

            return jsonify({
                'current_stats': current_stats,
                'ytd_stats': ytd_stats,
                'recent_transactions': recent_transactions,
                'monthly_trend': monthly_trend,
                'income_categories': income_categories,
                'expense_categories': expense_categories
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
            search_all = request.args.get('searchAll', 'false').lower() == 'true'

            # Get filter parameters
            description = request.args.get('description', '')
            notes_filter = request.args.get('notes', '')
            categories = request.args.get('categories', '')  # comma-separated IDs
            payment_methods = request.args.get('paymentMethods', '')  # comma-separated IDs
            types = request.args.get('types', '')  # comma-separated: income,expense
            statuses = request.args.get('statuses', '')  # comma-separated: done,not_done,paid,unpaid
            min_amount = request.args.get('minAmount', type=float)
            max_amount = request.args.get('maxAmount', type=float)
            start_date = request.args.get('startDate', '')
            end_date = request.args.get('endDate', '')

            # Check if any filters are active
            has_filters = any([
                description, notes_filter, categories, payment_methods,
                types, statuses, min_amount is not None, max_amount is not None,
                start_date, end_date
            ])

            # Build dynamic WHERE clause
            where_clauses = []
            params = []

            # If searching all or filters are active, search across all user's transactions
            # Otherwise, limit to specific month
            if search_all or has_filters:
                # Parse date range to extract year and month if provided
                start_year, start_month = None, None
                end_year, end_month = None, None

                if start_date:
                    try:
                        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                        start_year = start_dt.year
                        start_month = start_dt.month
                    except ValueError:
                        pass

                if end_date:
                    try:
                        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
                        end_year = end_dt.year
                        end_month = end_dt.month
                    except ValueError:
                        pass

                # Get all monthly records for this user, filtered by date range if provided
                monthly_records_query = "SELECT id FROM monthly_records WHERE user_id = %s"
                monthly_records_params = [user_id]

                # Add date range filter on monthly_records year/month
                if start_year and start_month:
                    monthly_records_query += " AND (year > %s OR (year = %s AND month >= %s))"
                    monthly_records_params.extend([start_year, start_year, start_month])

                if end_year and end_month:
                    monthly_records_query += " AND (year < %s OR (year = %s AND month <= %s))"
                    monthly_records_params.extend([end_year, end_year, end_month])

                cursor.execute(monthly_records_query, monthly_records_params)
                monthly_records = cursor.fetchall()

                if monthly_records:
                    monthly_record_ids = [record['id'] for record in monthly_records]
                    placeholders = ','.join(['%s'] * len(monthly_record_ids))
                    where_clauses.append(f"t.monthly_record_id IN ({placeholders})")
                    params.extend(monthly_record_ids)
                else:
                    # No records found, return empty
                    return jsonify([])
            else:
                # Normal behavior - get specific monthly record
                cursor.execute("""
                               SELECT id
                               FROM monthly_records
                               WHERE user_id = %s AND year = %s AND month = %s
                               """, (user_id, year, month))

                monthly_record = cursor.fetchone()

                if not monthly_record:
                    return jsonify([])

                where_clauses.append("t.monthly_record_id = %s")
                params.append(monthly_record['id'])

            # Continue with filter building only if we have WHERE clauses
            if where_clauses:

                # Description filter
                if description:
                    where_clauses.append("LOWER(t.description) LIKE %s")
                    params.append(f"%{description.lower()}%")

                # Notes filter
                if notes_filter:
                    where_clauses.append("LOWER(t.notes) LIKE %s")
                    params.append(f"%{notes_filter.lower()}%")

                # Category filter
                if categories:
                    cat_ids = [int(cid) for cid in categories.split(',') if cid.strip()]
                    if cat_ids:
                        placeholders = ','.join(['%s'] * len(cat_ids))
                        where_clauses.append(f"t.category_id IN ({placeholders})")
                        params.extend(cat_ids)

                # Payment method filter
                if payment_methods:
                    pm_ids = [int(pmid) for pmid in payment_methods.split(',') if pmid.strip()]
                    if pm_ids:
                        placeholders = ','.join(['%s'] * len(pm_ids))
                        where_clauses.append(f"t.payment_method_id IN ({placeholders})")
                        params.extend(pm_ids)

                # Transaction type filter
                if types:
                    type_list = [t.strip() for t in types.split(',') if t.strip()]
                    type_conditions = []
                    if 'income' in type_list:
                        type_conditions.append("t.debit > 0")
                    if 'expense' in type_list:
                        type_conditions.append("t.credit > 0")
                    if type_conditions:
                        where_clauses.append(f"({' OR '.join(type_conditions)})")

                # Status filter
                if statuses:
                    status_list = [s.strip() for s in statuses.split(',') if s.strip()]
                    status_conditions = []
                    if 'done' in status_list:
                        status_conditions.append("t.is_done = TRUE")
                    if 'not_done' in status_list:
                        status_conditions.append("t.is_done = FALSE OR t.is_done IS NULL")
                    if 'paid' in status_list:
                        status_conditions.append("t.is_paid = TRUE")
                    if 'unpaid' in status_list:
                        status_conditions.append("t.is_paid = FALSE OR t.is_paid IS NULL")
                    if status_conditions:
                        where_clauses.append(f"({' OR '.join(status_conditions)})")

                # Amount range filter
                if min_amount is not None:
                    where_clauses.append("(COALESCE(t.debit, 0) >= %s OR COALESCE(t.credit, 0) >= %s)")
                    params.extend([min_amount, min_amount])

                if max_amount is not None:
                    where_clauses.append("(COALESCE(t.debit, 0) <= %s OR COALESCE(t.credit, 0) <= %s)")
                    params.extend([max_amount, max_amount])

                # Date range filter is now handled via monthly_records filtering above
                # No need to filter on transaction dates here

                # Combine WHERE clauses
                where_sql = " AND ".join(where_clauses)

                query = f"""
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
                    WHERE {where_sql}
                    ORDER BY t.display_order ASC, t.id ASC
                """

                cursor.execute(query, params)
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
                           VALUES (%s, %s, %s, %s) ON DUPLICATE KEY
                           UPDATE updated_at = CURRENT_TIMESTAMP
                           """, (user_id, year, month, month_name))

            cursor.execute("""
                           SELECT id
                           FROM monthly_records
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

            # Push all existing transactions down by incrementing their display_order
            # This makes room for the new transaction at position 1 (top)
            cursor.execute("""
                           UPDATE transactions
                           SET display_order = display_order + 1
                           WHERE monthly_record_id = %s
                           """, (monthly_record['id'],))

            # New transaction gets display_order = 1 (appears at top)
            next_display_order = 1

            # Insert transaction (balance will be calculated on frontend)
            insert_values = (
                monthly_record['id'],
                data.get('description'),
                data.get('category_id'),
                debit if debit > 0 else None,
                credit if credit > 0 else None,
                transaction_date,
                data.get('notes'),
                next_display_order
            )
            print(f"[DEBUG] Inserting transaction with values: {insert_values}")

            cursor.execute("""
                           INSERT INTO transactions
                           (monthly_record_id, description, category_id, debit, credit, transaction_date, notes,
                            display_order)
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


@app.route('/api/transactions/filter', methods=['GET'])
@login_required
def filter_transactions():
    """Filter transactions across all data with advanced criteria."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    try:
        cursor = connection.cursor(dictionary=True)
        user_id = session.get('user_id')

        # Get filter parameters
        date_from = request.args.get('dateFrom')
        date_to = request.args.get('dateTo')
        category_id = request.args.get('category')
        payment_method_id = request.args.get('paymentMethod')
        amount_min = request.args.get('amountMin')
        amount_max = request.args.get('amountMax')
        transaction_type = request.args.get('transactionType')  # 'debit' or 'credit'
        search_text = request.args.get('searchText')
        done_status = request.args.get('doneStatus')  # 'done', 'not_done', or empty
        paid_status = request.args.get('paidStatus')  # 'paid', 'not_paid', or empty

        # Build SQL query with filters
        query = """
                SELECT t.*,
                       c.name   as category_name,
                       pm.name  as payment_method_name,
                       pm.type  as payment_method_type,
                       pm.color as payment_method_color,
                       mr.year,
                       mr.month,
                       mr.month_name
                FROM transactions t
                         LEFT JOIN categories c ON t.category_id = c.id
                         LEFT JOIN payment_methods pm ON t.payment_method_id = pm.id
                         INNER JOIN monthly_records mr ON t.monthly_record_id = mr.id
                WHERE mr.user_id = %s \
                """

        params = [user_id]

        # Add date range filter (based on monthly_records year/month)
        if date_from:
            try:
                start_dt = datetime.strptime(date_from, '%Y-%m-%d')
                start_year = start_dt.year
                start_month = start_dt.month
                query += " AND (mr.year > %s OR (mr.year = %s AND mr.month >= %s))"
                params.extend([start_year, start_year, start_month])
            except ValueError:
                pass

        if date_to:
            try:
                end_dt = datetime.strptime(date_to, '%Y-%m-%d')
                end_year = end_dt.year
                end_month = end_dt.month
                query += " AND (mr.year < %s OR (mr.year = %s AND mr.month <= %s))"
                params.extend([end_year, end_year, end_month])
            except ValueError:
                pass

        # Add category filter
        if category_id:
            query += " AND t.category_id = %s"
            params.append(int(category_id))

        # Add payment method filter
        if payment_method_id:
            query += " AND t.payment_method_id = %s"
            params.append(int(payment_method_id))

        # Add amount filter based on transaction type
        if transaction_type == 'debit':
            # Income transactions (debit > 0)
            query += " AND t.debit > 0"
            if amount_min:
                query += " AND t.debit >= %s"
                params.append(float(amount_min))
            if amount_max:
                query += " AND t.debit <= %s"
                params.append(float(amount_max))
        elif transaction_type == 'credit':
            # Expense transactions (credit > 0)
            query += " AND t.credit > 0"
            if amount_min:
                query += " AND t.credit >= %s"
                params.append(float(amount_min))
            if amount_max:
                query += " AND t.credit <= %s"
                params.append(float(amount_max))
        else:
            # Both types - check either debit or credit
            if amount_min or amount_max:
                amount_conditions = []
                if amount_min:
                    amount_conditions.append("(t.debit >= %s OR t.credit >= %s)")
                    params.extend([float(amount_min), float(amount_min)])
                if amount_max:
                    amount_conditions.append("(t.debit <= %s OR t.credit <= %s)")
                    params.extend([float(amount_max), float(amount_max)])
                if amount_conditions:
                    query += " AND " + " AND ".join(amount_conditions)

        # Add text search filter (search in description and notes)
        if search_text:
            query += " AND (t.description LIKE %s OR t.notes LIKE %s)"
            search_pattern = f"%{search_text}%"
            params.extend([search_pattern, search_pattern])

        # Add done status filter
        if done_status == 'done':
            query += " AND t.is_done = 1"
        elif done_status == 'not_done':
            query += " AND t.is_done = 0"

        # Add paid status filter
        if paid_status == 'paid':
            query += " AND t.is_paid = 1"
        elif paid_status == 'not_paid':
            query += " AND t.is_paid = 0"

        # Order by date descending (most recent first)
        query += " ORDER BY t.transaction_date DESC, t.id DESC"

        # Limit results to prevent overload (max 500 transactions)
        query += " LIMIT 500"

        cursor.execute(query, params)
        transactions = cursor.fetchall()

        # Calculate running balance for filtered transactions
        running_balance = 0
        for trans in reversed(transactions):
            running_balance += (trans['debit'] or 0) - (trans['credit'] or 0)
            trans['balance'] = running_balance

        # Reverse back to show most recent first
        transactions.reverse()

        return jsonify(transactions)

    except Exception as e:
        print(f"Error filtering transactions: {e}")
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

            # Get the current transaction data for audit trail
            dict_cursor = connection.cursor(dictionary=True)
            dict_cursor.execute("""
                                SELECT t.*
                                FROM transactions t
                                WHERE t.id = %s
                                  AND t.monthly_record_id IN
                                      (SELECT id FROM monthly_records WHERE user_id = %s)
                                """, (transaction_id, session['user_id']))

            old_transaction = dict_cursor.fetchone()
            dict_cursor.close()

            if not old_transaction:
                print(f"[DEBUG] Transaction {transaction_id} not found for user {session['user_id']}")
                return jsonify({'error': 'Transaction not found'}), 404

            monthly_record_id = old_transaction['monthly_record_id']
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
                           SET description      = %s,
                               category_id      = %s,
                               debit            = %s,
                               credit           = %s,
                               transaction_date = %s,
                               notes            = %s
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

            # Log audit trail for each changed field
            user_id = session['user_id']

            # Track field changes
            new_debit = debit if debit > 0 else None
            new_credit = credit if credit > 0 else None

            # Normalize values for comparison to avoid false positives
            # Convert category_id to int for comparison (handle None)
            old_category = old_transaction['category_id']
            new_category = int(data.get('category_id')) if data.get('category_id') else None

            # Compare description
            if old_transaction['description'] != data.get('description'):
                log_transaction_audit(cursor, transaction_id, user_id, 'UPDATE', 'description',
                                      old_transaction['description'], data.get('description'))

            # Compare category_id (normalized)
            if old_category != new_category:
                log_transaction_audit(cursor, transaction_id, user_id, 'UPDATE', 'category_id',
                                      old_category, new_category)

            # Compare debit (Decimal comparison)
            old_debit_normalized = old_transaction['debit'] if old_transaction['debit'] else None
            if old_debit_normalized != new_debit:
                log_transaction_audit(cursor, transaction_id, user_id, 'UPDATE', 'debit',
                                      old_transaction['debit'], new_debit)

            # Compare credit (Decimal comparison)
            old_credit_normalized = old_transaction['credit'] if old_transaction['credit'] else None
            if old_credit_normalized != new_credit:
                log_transaction_audit(cursor, transaction_id, user_id, 'UPDATE', 'credit',
                                      old_transaction['credit'], new_credit)

            # Compare transaction_date
            if str(old_transaction['transaction_date']) != str(transaction_date):
                log_transaction_audit(cursor, transaction_id, user_id, 'UPDATE', 'transaction_date',
                                      old_transaction['transaction_date'], transaction_date)

            # Compare notes (handle None/empty string)
            old_notes = old_transaction['notes'] if old_transaction['notes'] else None
            new_notes = data.get('notes') if data.get('notes') else None
            if old_notes != new_notes:
                log_transaction_audit(cursor, transaction_id, user_id, 'UPDATE', 'notes',
                                      old_transaction['notes'], data.get('notes'))

            connection.commit()
            print(f"[DEBUG] Transaction update committed successfully")
            return jsonify({'message': 'Transaction updated successfully'})

        else:  # DELETE
            # Log audit trail before deleting
            user_id = session['user_id']
            log_transaction_audit(cursor, transaction_id, user_id, 'DELETE')

            cursor.execute("""
                           DELETE
                           FROM transactions
                           WHERE id = %s
                             AND monthly_record_id IN
                                 (SELECT id FROM monthly_records WHERE user_id = %s)
                           """, (transaction_id, user_id))

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


@app.route('/api/transactions/<int:transaction_id>/audit-logs', methods=['GET'])
@login_required
def get_transaction_audit_logs(transaction_id):
    """Get audit logs for a specific transaction."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    try:
        cursor = connection.cursor(dictionary=True)
        user_id = session['user_id']

        # Verify the transaction belongs to the user
        cursor.execute("""
                       SELECT t.id
                       FROM transactions t
                                INNER JOIN monthly_records mr ON t.monthly_record_id = mr.id
                       WHERE t.id = %s
                         AND mr.user_id = %s
                       """, (transaction_id, user_id))

        transaction = cursor.fetchone()
        if not transaction:
            return jsonify({'error': 'Transaction not found'}), 404

        # Fetch audit logs for this transaction
        cursor.execute("""
                       SELECT tal.id,
                              tal.action,
                              tal.field_name,
                              tal.old_value,
                              tal.new_value,
                              tal.created_at,
                              u.username
                       FROM transaction_audit_logs tal
                                INNER JOIN users u ON tal.user_id = u.id
                       WHERE tal.transaction_id = %s
                       ORDER BY tal.created_at DESC
                       """, (transaction_id,))

        audit_logs = cursor.fetchall()
        return jsonify(audit_logs)

    except Error as e:
        logger.error(f"Error fetching audit logs: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


@app.route('/api/transactions/<int:transaction_id>/move', methods=['POST'])
@login_required
def move_transaction(transaction_id):
    """Move a transaction to a different month."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    try:
        cursor = connection.cursor(dictionary=True)
        user_id = session['user_id']
        data = request.get_json()

        target_year = data.get('target_year')
        target_month = data.get('target_month')

        if not target_year or not target_month:
            return jsonify({'error': 'Target year and month are required'}), 400

        # Verify the transaction belongs to the user
        cursor.execute("""
                       SELECT t.*, mr.year, mr.month
                       FROM transactions t
                                INNER JOIN monthly_records mr ON t.monthly_record_id = mr.id
                       WHERE t.id = %s
                         AND mr.user_id = %s
                       """, (transaction_id, user_id))

        transaction = cursor.fetchone()
        if not transaction:
            return jsonify({'error': 'Transaction not found'}), 404

        # Check if moving to the same month
        if transaction['year'] == target_year and transaction['month'] == target_month:
            return jsonify({'error': 'Transaction is already in this month'}), 400

        # Get or create target monthly record
        month_name = calendar.month_name[target_month]
        cursor.execute("""
                       INSERT INTO monthly_records (user_id, year, month, month_name)
                       VALUES (%s, %s, %s, %s) ON DUPLICATE KEY
                       UPDATE updated_at = CURRENT_TIMESTAMP
                       """, (user_id, target_year, target_month, month_name))

        cursor.execute("""
                       SELECT id
                       FROM monthly_records
                       WHERE user_id = %s AND year = %s AND month = %s
                       """, (user_id, target_year, target_month))

        target_record = cursor.fetchone()

        # Update transaction's monthly_record_id and date
        new_date = datetime(target_year, target_month, 1).date()
        cursor.execute("""
                       UPDATE transactions
                       SET monthly_record_id = %s,
                           transaction_date  = %s
                       WHERE id = %s
                       """, (target_record['id'], new_date, transaction_id))

        # Log audit trail
        log_transaction_audit(cursor, transaction_id, user_id, 'UPDATE', 'moved_to_month',
                              f"{transaction['year']}-{transaction['month']:02d}",
                              f"{target_year}-{target_month:02d}")

        connection.commit()

        return jsonify({
            'message': f'Transaction moved to {month_name} {target_year} successfully',
            'target_year': target_year,
            'target_month': target_month
        })

    except Error as e:
        logger.error(f"Error moving transaction: {e}")
        connection.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


@app.route('/api/transactions/<int:transaction_id>/copy', methods=['POST'])
@login_required
def copy_transaction(transaction_id):
    """Copy a transaction to a different month."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    try:
        cursor = connection.cursor(dictionary=True)
        user_id = session['user_id']
        data = request.get_json()

        target_year = data.get('target_year')
        target_month = data.get('target_month')

        if not target_year or not target_month:
            return jsonify({'error': 'Target year and month are required'}), 400

        # Verify the transaction belongs to the user and get its data
        cursor.execute("""
                       SELECT t.*
                       FROM transactions t
                                INNER JOIN monthly_records mr ON t.monthly_record_id = mr.id
                       WHERE t.id = %s
                         AND mr.user_id = %s
                       """, (transaction_id, user_id))

        transaction = cursor.fetchone()
        if not transaction:
            return jsonify({'error': 'Transaction not found'}), 404

        # Get or create target monthly record
        month_name = calendar.month_name[target_month]
        cursor.execute("""
                       INSERT INTO monthly_records (user_id, year, month, month_name)
                       VALUES (%s, %s, %s, %s) ON DUPLICATE KEY
                       UPDATE updated_at = CURRENT_TIMESTAMP
                       """, (user_id, target_year, target_month, month_name))

        cursor.execute("""
                       SELECT id
                       FROM monthly_records
                       WHERE user_id = %s AND year = %s AND month = %s
                       """, (user_id, target_year, target_month))

        target_record = cursor.fetchone()

        # Push all existing transactions down in the target month
        cursor.execute("""
                       UPDATE transactions
                       SET display_order = display_order + 1
                       WHERE monthly_record_id = %s
                       """, (target_record['id'],))

        # Create a copy of the transaction in the target month at position 1 (top)
        new_date = datetime(target_year, target_month, 1).date()
        debit = Decimal(str(transaction['debit'])) if transaction['debit'] else None
        credit = Decimal(str(transaction['credit'])) if transaction['credit'] else None

        cursor.execute("""
                       INSERT INTO transactions
                       (monthly_record_id, description, category_id, debit, credit,
                        transaction_date, notes, payment_method_id, display_order)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                       """, (
                           target_record['id'],
                           transaction['description'],
                           transaction['category_id'],
                           debit,
                           credit,
                           new_date,
                           transaction['notes'],
                           transaction['payment_method_id'],
                           1  # Display at top
                       ))

        new_transaction_id = cursor.lastrowid

        # Log audit trail for the new transaction
        log_transaction_audit(cursor, new_transaction_id, user_id, 'CREATE')
        log_transaction_audit(cursor, new_transaction_id, user_id, 'UPDATE', 'copied_from_transaction',
                              None, str(transaction_id))

        connection.commit()

        return jsonify({
            'message': f'Transaction copied to {month_name} {target_year} successfully',
            'new_transaction_id': new_transaction_id,
            'target_year': target_year,
            'target_month': target_month
        })

    except Error as e:
        logger.error(f"Error copying transaction: {e}")
        connection.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


@app.route('/api/transactions/export', methods=['GET'])
@login_required
def export_transactions():
    """Export transactions to CSV, PDF, or Excel format."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    try:
        cursor = connection.cursor(dictionary=True)
        user_id = session['user_id']

        # Get parameters
        year = request.args.get('year', datetime.now().year, type=int)
        month = request.args.get('month', datetime.now().month, type=int)
        export_format = request.args.get('format', 'csv')

        # Get monthly record
        cursor.execute("""
                       SELECT id
                       FROM monthly_records
                       WHERE user_id = %s AND year = %s AND month = %s
                       """, (user_id, year, month))

        monthly_record = cursor.fetchone()

        if not monthly_record:
            # Return empty file if no transactions
            transactions = []
        else:
            # Fetch transactions (DESC order for downloads - oldest first)
            cursor.execute("""
                           SELECT t.id,
                                  t.transaction_date,
                                  t.description,
                                  c.name  as category,
                                  t.debit,
                                  t.credit,
                                  t.notes,
                                  pm.name as payment_method,
                                  t.is_done,
                                  t.is_paid,
                                  t.paid_at
                           FROM transactions t
                                    LEFT JOIN categories c ON t.category_id = c.id
                                    LEFT JOIN payment_methods pm ON t.payment_method_id = pm.id
                           WHERE t.monthly_record_id = %s
                           ORDER BY t.display_order DESC, t.id DESC
                           """, (monthly_record['id'],))

            transactions = cursor.fetchall()

        # Generate file based on format
        if export_format == 'csv':
            return generate_csv(transactions, year, month)
        elif export_format == 'excel':
            return generate_excel(transactions, year, month)
        elif export_format == 'pdf':
            return generate_pdf(transactions, year, month)
        else:
            return jsonify({'error': 'Invalid format'}), 400

    except Error as e:
        logger.error(f"Error exporting transactions: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


def generate_csv(transactions, year, month):
    """Generate CSV file from transactions."""
    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow(
        ['Date', 'Description', 'Category', 'Debit', 'Credit', 'Balance', 'Notes', 'Payment Method', 'Done', 'Paid',
         'Paid At'])

    # Transactions come in DESC order (oldest first in downloads)
    # Calculate running balance sequentially from oldest to newest
    balance = 0
    for t in transactions:
        debit = float(t['debit']) if t['debit'] else 0
        credit = float(t['credit']) if t['credit'] else 0
        balance += debit - credit

        writer.writerow([
            t['transaction_date'],
            t['description'],
            t['category'] or '',
            f"{debit:.2f}" if debit > 0 else '',
            f"{credit:.2f}" if credit > 0 else '',
            f"{balance:.2f}",
            t['notes'] or '',
            t['payment_method'] or '',
            'Yes' if t['is_done'] else 'No',
            'Yes' if t['is_paid'] else 'No',
            t['paid_at'] if t['paid_at'] else ''
        ])

    # Create response
    output.seek(0)
    month_name = calendar.month_name[month]
    filename = f'transactions_{month_name}_{year}.csv'

    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'

    return response


def generate_excel(transactions, year, month):
    """Generate Excel file from transactions."""
    if not EXCEL_AVAILABLE:
        # Fallback to CSV
        return generate_csv(transactions, year, month)

    # Create workbook and worksheet
    wb = Workbook()
    ws = wb.active
    month_name = calendar.month_name[month]
    ws.title = f"{month_name} {year}"

    # Define styles
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center")

    # Write header row
    headers = ['Date', 'Description', 'Category', 'Debit', 'Credit', 'Balance', 'Notes', 'Payment Method', 'Done',
               'Paid', 'Paid At']
    ws.append(headers)

    # Style header row
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment

    # Transactions come in DESC order (oldest first in downloads)
    # Calculate running balance sequentially from oldest to newest
    balance = 0
    for t in transactions:
        debit = float(t['debit']) if t['debit'] else 0
        credit = float(t['credit']) if t['credit'] else 0
        balance += debit - credit

        ws.append([
            str(t['transaction_date']),
            t['description'],
            t['category'] or '',
            debit if debit > 0 else '',
            credit if credit > 0 else '',
            balance,
            t['notes'] or '',
            t['payment_method'] or '',
            'Yes' if t['is_done'] else 'No',
            'Yes' if t['is_paid'] else 'No',
            str(t['paid_at']) if t['paid_at'] else ''
        ])

    # Adjust column widths
    ws.column_dimensions['A'].width = 12
    ws.column_dimensions['B'].width = 30
    ws.column_dimensions['C'].width = 20
    ws.column_dimensions['D'].width = 12
    ws.column_dimensions['E'].width = 12
    ws.column_dimensions['F'].width = 12
    ws.column_dimensions['G'].width = 30
    ws.column_dimensions['H'].width = 20

    # Save to BytesIO
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f'transactions_{month_name}_{year}.xlsx'

    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'

    return response


def generate_pdf(transactions, year, month):
    """Generate PDF file from transactions."""
    if not PDF_AVAILABLE:
        # Fallback to CSV
        return generate_csv(transactions, year, month)

    month_name = calendar.month_name[month]
    output = io.BytesIO()

    # Create the PDF document
    doc = SimpleDocTemplate(output, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()

    # Add title
    title = Paragraph(f"<b>Transaction Report - {month_name} {year}</b>", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 0.2 * inch))

    # Create table data
    table_data = [['Date', 'Description', 'Category', 'Debit', 'Credit', 'Balance']]

    # Transactions come in DESC order (oldest first in downloads)
    # Calculate running balance sequentially from oldest to newest
    balance = 0
    for t in transactions:
        debit = float(t['debit']) if t['debit'] else 0
        credit = float(t['credit']) if t['credit'] else 0
        balance += debit - credit

        table_data.append([
            str(t['transaction_date']),
            t['description'][:30],  # Truncate long descriptions
            (t['category'] or '')[:15],
            f"{debit:.2f}" if debit > 0 else '',
            f"{credit:.2f}" if credit > 0 else '',
            f"{balance:.2f}"
        ])

    # Create table
    table = Table(table_data, colWidths=[1.0 * inch, 2.5 * inch, 1.2 * inch, 0.9 * inch, 0.9 * inch, 1.0 * inch])

    # Style the table
    table.setStyle(TableStyle([
        # Header styling
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#366092')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),

        # Body styling
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),  # Date
        ('ALIGN', (1, 1), (2, -1), 'LEFT'),  # Description, Category
        ('ALIGN', (3, 1), (-1, -1), 'RIGHT'),  # Amounts
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f0f0')]),
    ]))

    elements.append(table)

    # Build PDF
    doc.build(elements)
    output.seek(0)

    filename = f'transactions_{month_name}_{year}.pdf'

    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'

    return response


@app.route('/api/transactions/reorder', methods=['POST'])
@login_required
def reorder_transactions():
    """Reorder transactions based on new order array of transaction IDs."""
    data = request.get_json()
    transaction_ids = data.get('transaction_ids', [])

    if not transaction_ids or not isinstance(transaction_ids, list):
        return jsonify({'error': 'Invalid transaction_ids. Must be a non-empty array'}), 400

    connection = get_db_connection()
    if connection:
        cursor = connection.cursor(dictionary=True)
        try:
            user_id = session.get('user_id')

            # Update display_order for each transaction in the new order
            for index, transaction_id in enumerate(transaction_ids):
                new_order = index + 1  # Start from 1

                # Get old display_order for audit log
                cursor.execute("""
                               SELECT display_order
                               FROM transactions
                               WHERE id = %s
                               """, (transaction_id,))

                result = cursor.fetchone()
                if result:
                    old_order = result['display_order']

                    # Only update if order changed
                    if old_order != new_order:
                        cursor.execute("""
                                       UPDATE transactions
                                       SET display_order = %s
                                       WHERE id = %s
                                       """, (new_order, transaction_id))

            connection.commit()
            return jsonify({
                'success': True,
                'message': 'Transaction order updated successfully'
            })

        except Error as e:
            connection.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cursor.close()
            connection.close()

    return jsonify({'error': 'Database connection failed'}), 500


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


@app.route('/api/categories', methods=['POST'])
@login_required
def add_category():
    """Add a new category."""
    data = request.get_json()

    # Validate input
    if not data or 'name' not in data or 'type' not in data:
        return jsonify({'error': 'Missing required fields: name and type'}), 400

    name = data['name'].strip()
    category_type = data['type'].strip().lower()

    if not name:
        return jsonify({'error': 'Category name cannot be empty'}), 400

    if category_type not in ['income', 'expense']:
        return jsonify({'error': 'Category type must be either "income" or "expense"'}), 400

    connection = get_db_connection()
    if connection:
        cursor = connection.cursor(dictionary=True)
        try:
            # Check if category with same name and type already exists
            cursor.execute(
                "SELECT id FROM categories WHERE name = %s AND type = %s",
                (name, category_type)
            )
            existing = cursor.fetchone()

            if existing:
                return jsonify({'error': 'Category with this name and type already exists', 'id': existing['id']}), 409

            # Insert new category
            cursor.execute(
                "INSERT INTO categories (name, type) VALUES (%s, %s)",
                (name, category_type)
            )
            connection.commit()

            # Get the newly created category
            category_id = cursor.lastrowid
            cursor.execute("SELECT * FROM categories WHERE id = %s", (category_id,))
            new_category = cursor.fetchone()

            return jsonify(new_category), 201
        except Error as e:
            connection.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cursor.close()
            connection.close()

    return jsonify({'error': 'Database connection failed'}), 500


@app.route('/api/categories/<int:category_id>', methods=['PUT'])
@login_required
def update_category(category_id):
    """Update a category."""
    data = request.get_json()

    # Validate input
    if not data or 'name' not in data or 'type' not in data:
        return jsonify({'error': 'Missing required fields: name and type'}), 400

    name = data['name'].strip()
    category_type = data['type'].strip().lower()

    if not name:
        return jsonify({'error': 'Category name cannot be empty'}), 400

    if category_type not in ['income', 'expense']:
        return jsonify({'error': 'Category type must be either "income" or "expense"'}), 400

    connection = get_db_connection()
    if connection:
        cursor = connection.cursor(dictionary=True)
        try:
            # Check if category exists
            cursor.execute("SELECT * FROM categories WHERE id = %s", (category_id,))
            category = cursor.fetchone()

            if not category:
                return jsonify({'error': 'Category not found'}), 404

            # Check if another category with same name and type already exists (excluding current category)
            cursor.execute(
                "SELECT id FROM categories WHERE name = %s AND type = %s AND id != %s",
                (name, category_type, category_id)
            )
            existing = cursor.fetchone()

            if existing:
                return jsonify({'error': 'Another category with this name and type already exists'}), 409

            # Update the category
            cursor.execute(
                "UPDATE categories SET name = %s, type = %s WHERE id = %s",
                (name, category_type, category_id)
            )
            connection.commit()

            # Get the updated category
            cursor.execute("SELECT * FROM categories WHERE id = %s", (category_id,))
            updated_category = cursor.fetchone()

            return jsonify(updated_category), 200
        except Error as e:
            connection.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cursor.close()
            connection.close()

    return jsonify({'error': 'Database connection failed'}), 500


@app.route('/api/categories/<int:category_id>', methods=['DELETE'])
@login_required
def delete_category(category_id):
    """Delete a category."""
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor(dictionary=True)
        try:
            # Check if category exists
            cursor.execute("SELECT * FROM categories WHERE id = %s", (category_id,))
            category = cursor.fetchone()

            if not category:
                return jsonify({'error': 'Category not found'}), 404

            # Check if category is being used in transactions
            cursor.execute(
                "SELECT COUNT(*) as count FROM transactions WHERE category_id = %s",
                (category_id,)
            )
            result = cursor.fetchone()

            if result and result['count'] > 0:
                return jsonify({
                    'error': f'Cannot delete category. It is being used by {result["count"]} transaction(s).',
                    'transaction_count': result['count']
                }), 409

            # Delete the category
            cursor.execute("DELETE FROM categories WHERE id = %s", (category_id,))
            connection.commit()

            return jsonify({'message': 'Category deleted successfully'}), 200
        except Error as e:
            connection.rollback()
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
                           SELECT *
                           FROM payment_methods
                           WHERE user_id = %s
                             AND is_active = TRUE
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
                       WHERE id = %s
                         AND user_id = %s
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
                       SET is_done           = TRUE,
                           payment_method_id = %s,
                           marked_done_at    = CURRENT_TIMESTAMP
                       WHERE id = %s
                         AND monthly_record_id IN
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
                       SET is_done           = FALSE,
                           payment_method_id = NULL,
                           marked_done_at    = NULL
                       WHERE id = %s
                         AND monthly_record_id IN
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
                       SET is_done           = TRUE,
                           is_paid           = TRUE,
                           payment_method_id = %s,
                           marked_done_at    = CURRENT_TIMESTAMP,
                           paid_at           = CURRENT_TIMESTAMP
                       WHERE id = %s
                         AND monthly_record_id IN
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
                       SET is_done           = FALSE,
                           is_paid           = FALSE,
                           payment_method_id = NULL,
                           marked_done_at    = NULL,
                           paid_at           = NULL
                       WHERE id = %s
                         AND monthly_record_id IN
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
                       SELECT id
                       FROM monthly_records
                       WHERE user_id = %s AND year = %s AND month = %s
                       """, (user_id, year, month))

        monthly_record = cursor.fetchone()

        if not monthly_record:
            return jsonify([])

        # Get totals by payment method
        cursor.execute("""
                       SELECT pm.id,
                              pm.name,
                              pm.type,
                              pm.color,
                              COUNT(t.id)                                       as transaction_count,
                              SUM(t.debit)                                      as total_debit,
                              SUM(t.credit)                                     as total_credit,
                              SUM(COALESCE(t.debit, 0) - COALESCE(t.credit, 0)) as net_amount
                       FROM payment_methods pm
                                LEFT JOIN transactions t ON pm.id = t.payment_method_id
                           AND t.monthly_record_id = %s
                           AND t.is_done = TRUE
                       WHERE pm.user_id = %s
                         AND pm.is_active = TRUE
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
                       SELECT id
                       FROM monthly_records
                       WHERE user_id = %s AND year = %s AND month = %s
                       """, (user_id, from_year, from_month))

        source_record = cursor.fetchone()

        if not source_record:
            return jsonify({'error': 'Source month has no transactions'}), 404

        # Get or create target monthly record
        month_name = calendar.month_name[to_month]
        cursor.execute("""
                       INSERT INTO monthly_records (user_id, year, month, month_name)
                       VALUES (%s, %s, %s, %s) ON DUPLICATE KEY
                       UPDATE updated_at = CURRENT_TIMESTAMP
                       """, (user_id, to_year, to_month, month_name))

        cursor.execute("""
                       SELECT id
                       FROM monthly_records
                       WHERE user_id = %s AND year = %s AND month = %s
                       """, (user_id, to_year, to_month))

        target_record = cursor.fetchone()

        # Get all transactions from source month (preserve order)
        cursor.execute("""
                       SELECT description,
                              category_id,
                              debit,
                              credit,
                              notes,
                              payment_method_id,
                              is_done,
                              is_paid,
                              display_order
                       FROM transactions
                       WHERE monthly_record_id = %s
                       ORDER BY display_order ASC, id ASC
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
                            transaction_date, notes, payment_method_id, is_done, is_paid, display_order)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                               is_paid,
                               trans['display_order']  # Preserve order from source
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


# ==================================================
# TAX CALCULATOR API ENDPOINTS
# ==================================================

@app.route('/api/tax-calculations', methods=['POST'])
@login_required
def save_tax_calculation():
    """Save income data only (tax calculations are computed on-the-fly)."""
    connection = None
    cursor = None
    try:
        data = request.get_json()
        user_id = session['user_id']

        # Extract income data (input fields only)
        calculation_name = data.get('calculation_name')
        assessment_year = data.get('assessment_year')
        tax_rate = data.get('tax_rate', 0)
        tax_free_threshold = data.get('tax_free_threshold', 0)
        start_month = int(data.get('start_month', 0))
        monthly_data = data.get('monthly_data', [])
        is_active = data.get('is_active', False)

        # Validate required fields
        if not all([calculation_name, assessment_year]):
            return jsonify({'error': 'Calculation name and assessment year are required'}), 400

        logger.info(f"Saving tax calculation: name='{calculation_name}', year={assessment_year}, active={is_active}")
        logger.info(f"Monthly data entries: {len(monthly_data)}")

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # If marking as active, deactivate other calculations for this year
        if is_active:
            cursor.execute("""
                           UPDATE tax_calculations
                           SET is_active = FALSE
                           WHERE user_id = %s
                             AND assessment_year = %s
                           """, (user_id, assessment_year))
            logger.info(f"Deactivated other calculations for year {assessment_year}")

        # Insert income data only (tax calculations computed on load)
        cursor.execute("""
                       INSERT INTO tax_calculations
                       (user_id, calculation_name, assessment_year,
                        tax_rate, tax_free_threshold, start_month, monthly_data, is_active)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                       """, (
                           user_id, calculation_name, assessment_year,
                           tax_rate, tax_free_threshold, start_month,
                           json.dumps(monthly_data), is_active
                       ))

        tax_calculation_id = cursor.lastrowid
        connection.commit()

        logger.info(f"Tax calculation saved successfully: ID={tax_calculation_id}")

        return jsonify({
            'message': 'Tax calculation saved successfully',
            'id': tax_calculation_id
        }), 201

    except Error as e:
        if connection:
            connection.rollback()
        logger.error(f"Error saving tax calculation: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@app.route('/api/tax-calculations', methods=['GET'])
@login_required
def get_tax_calculations():
    """Get all tax calculations for the current user, optionally filtered by year."""
    connection = None
    cursor = None
    try:
        user_id = session['user_id']
        year = request.args.get('year')  # Optional year filter

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Build query based on whether year filter is provided
        if year:
            cursor.execute("""
                           SELECT id,
                                  calculation_name,
                                  assessment_year,
                                  tax_rate,
                                  tax_free_threshold,
                                  start_month,
                                  is_active,
                                  created_at,
                                  updated_at
                           FROM tax_calculations
                           WHERE user_id = %s
                             AND assessment_year = %s
                           ORDER BY is_active DESC, created_at DESC
                           """, (user_id, year))
        else:
            cursor.execute("""
                           SELECT id,
                                  calculation_name,
                                  assessment_year,
                                  tax_rate,
                                  tax_free_threshold,
                                  start_month,
                                  is_active,
                                  created_at,
                                  updated_at
                           FROM tax_calculations
                           WHERE user_id = %s
                           ORDER BY assessment_year DESC, is_active DESC, created_at DESC
                           """, (user_id,))

        calculations = cursor.fetchall()

        # Convert Decimal types to float for proper JSON serialization
        for calc in calculations:
            if calc.get('tax_rate') is not None:
                calc['tax_rate'] = float(calc['tax_rate'])
            if calc.get('tax_free_threshold') is not None:
                calc['tax_free_threshold'] = float(calc['tax_free_threshold'])

        logger.info(f"Returning {len(calculations)} tax calculation(s)")
        return jsonify(calculations), 200

    except Error as e:
        logger.error(f"Error fetching tax calculations: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@app.route('/api/tax-calculations/<int:calculation_id>', methods=['GET'])
@login_required
def get_tax_calculation(calculation_id):
    """Get a specific tax calculation with all income data."""
    connection = None
    cursor = None
    try:
        user_id = session['user_id']

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Get main calculation with all income data
        cursor.execute("""
                       SELECT id,
                              calculation_name,
                              assessment_year,
                              tax_rate,
                              tax_free_threshold,
                              start_month,
                              monthly_data,
                              is_active,
                              created_at,
                              updated_at
                       FROM tax_calculations
                       WHERE id = %s
                         AND user_id = %s
                       """, (calculation_id, user_id))

        calculation = cursor.fetchone()

        if not calculation:
            return jsonify({'error': 'Tax calculation not found'}), 404

        # Convert Decimal types to float for proper JSON serialization
        if calculation.get('tax_rate') is not None:
            calculation['tax_rate'] = float(calculation['tax_rate'])
        if calculation.get('tax_free_threshold') is not None:
            calculation['tax_free_threshold'] = float(calculation['tax_free_threshold'])

        # Parse JSON monthly_data (contains all income details)
        if calculation.get('monthly_data'):
            if isinstance(calculation['monthly_data'], str):
                calculation['monthly_data'] = json.loads(calculation['monthly_data'])
            # else it's already parsed by MySQL JSON type

        logger.info(
            f"Loaded calculation ID={calculation['id']}, has {len(calculation.get('monthly_data', []))} monthly entries")
        return jsonify(calculation), 200

    except Error as e:
        logger.error(f"Error fetching tax calculation {calculation_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@app.route('/api/tax-calculations/<int:calculation_id>', methods=['DELETE'])
@login_required
def delete_tax_calculation(calculation_id):
    """Delete a tax calculation."""
    connection = None
    cursor = None
    try:
        user_id = session['user_id']

        connection = get_db_connection()
        cursor = connection.cursor()

        # Verify ownership before deleting
        cursor.execute("""
                       SELECT id
                       FROM tax_calculations
                       WHERE id = %s
                         AND user_id = %s
                       """, (calculation_id, user_id))

        if not cursor.fetchone():
            return jsonify({'error': 'Tax calculation not found'}), 404

        # Delete the calculation
        cursor.execute("""
                       DELETE
                       FROM tax_calculations
                       WHERE id = %s
                         AND user_id = %s
                       """, (calculation_id, user_id))

        connection.commit()
        logger.info(f"Tax calculation ID={calculation_id} deleted successfully")

        return jsonify({'message': 'Tax calculation deleted successfully'}), 200

    except Error as e:
        if connection:
            connection.rollback()
        logger.error(f"Error deleting tax calculation {calculation_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@app.route('/api/tax-calculations/<int:calculation_id>/set-active', methods=['PUT'])
@login_required
def set_active_tax_calculation(calculation_id):
    """Set a tax calculation as active for its assessment year."""
    connection = None
    cursor = None
    try:
        user_id = session['user_id']

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Verify ownership and get assessment year
        cursor.execute("""
                       SELECT assessment_year
                       FROM tax_calculations
                       WHERE id = %s
                         AND user_id = %s
                       """, (calculation_id, user_id))

        calculation = cursor.fetchone()

        if not calculation:
            return jsonify({'error': 'Tax calculation not found'}), 404

        assessment_year = calculation['assessment_year']

        # Deactivate all calculations for this year
        cursor.execute("""
                       UPDATE tax_calculations
                       SET is_active = FALSE
                       WHERE user_id = %s
                         AND assessment_year = %s
                       """, (user_id, assessment_year))

        # Activate the specified calculation
        cursor.execute("""
                       UPDATE tax_calculations
                       SET is_active  = TRUE,
                           updated_at = CURRENT_TIMESTAMP
                       WHERE id = %s
                         AND user_id = %s
                       """, (calculation_id, user_id))

        connection.commit()
        logger.info(f"Tax calculation ID={calculation_id} set as active for year {assessment_year}")

        return jsonify({
            'message': 'Tax calculation set as active successfully',
            'id': calculation_id,
            'assessment_year': assessment_year
        }), 200

    except Error as e:
        if connection:
            connection.rollback()
        logger.error(f"Error setting tax calculation {calculation_id} as active: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@app.route('/api/exchange-rate', methods=['GET'])
@login_required
def get_exchange_rate_api():
    """
    Get USD to LKR exchange rate for a specific date

    This endpoint:
    1. First checks the exchange_rates table in the database (cache)
    2. If not found, fetches from CBSL and stores in DB for future use
    3. If CBSL fails, returns nearest previous date from DB

    Query Parameters:
        date: Date in YYYY-MM-DD format (required)

    Returns:
        JSON with buy_rate, sell_rate, source, and date
    """
    try:
        from services.exchange_rate_service import get_exchange_rate_service

        date_str = request.args.get('date')
        if not date_str:
            return jsonify({'error': 'Date parameter is required (format: YYYY-MM-DD)'}), 400

        try:
            date = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

        # Check if date is not in the future
        if date > datetime.now():
            return jsonify({'error': 'Cannot fetch exchange rates for future dates'}), 400

        # Fetch exchange rate
        service = get_exchange_rate_service()
        rate = service.get_exchange_rate(date)

        if rate:
            logger.info(f"Exchange rate fetched for {date_str}: {rate}")
            return jsonify(rate), 200
        else:
            return jsonify({'error': 'Exchange rate not available for this date'}), 404

    except Exception as e:
        logger.error(f"Error fetching exchange rate: {str(e)}")
        return jsonify({'error': 'Failed to fetch exchange rate', 'details': str(e)}), 500


@app.route('/api/exchange-rate/month', methods=['GET'])
@login_required
def get_month_exchange_rates():
    """
    Fetch USD to LKR exchange rates for an entire month

    Query Parameters:
        year: Year (required)
        month: Month 1-12 (required)

    Returns:
        JSON with rates for each day in the month
    """
    try:
        from services.exchange_rate_service import get_exchange_rate_service

        year_str = request.args.get('year')
        month_str = request.args.get('month')

        if not year_str or not month_str:
            return jsonify({'error': 'Year and month parameters are required'}), 400

        try:
            year = int(year_str)
            month = int(month_str)

            if month < 1 or month > 12:
                return jsonify({'error': 'Month must be between 1 and 12'}), 400

            if year < 2000 or year > datetime.now().year:
                return jsonify({'error': f'Year must be between 2000 and {datetime.now().year}'}), 400

        except ValueError:
            return jsonify({'error': 'Invalid year or month format'}), 400

        # Fetch exchange rates for the month
        service = get_exchange_rate_service()
        rates = service.get_rates_for_month(year, month)

        if rates:
            logger.info(f"Exchange rates fetched for {year}-{month:02d}: {len(rates)} days")
            return jsonify(rates), 200
        else:
            return jsonify({'error': 'No exchange rates available for this month'}), 404

    except Exception as e:
        logger.error(f"Error fetching monthly exchange rates: {str(e)}")
        return jsonify({'error': 'Failed to fetch exchange rates', 'details': str(e)}), 500


@app.route('/api/exchange-rate/import-csv', methods=['POST'])
@login_required
def import_exchange_rates_csv():
    """
    Import exchange rates from CSV file

    Expects:
        csv_content: CSV content as string in request body

    Returns:
        JSON with import results
    """
    try:
        from services.exchange_rate_service import get_exchange_rate_service
        from exchange_rate_parser import ExchangeRateParser

        data = request.get_json()
        if not data or 'csv_content' not in data:
            return jsonify({'error': 'CSV content is required in request body'}), 400

        csv_content = data['csv_content']

        # Parse CSV
        parser = ExchangeRateParser()
        rates_dict = parser.parse_csv_content(csv_content)

        if not rates_dict:
            return jsonify({'error': 'No valid exchange rates found in CSV'}), 400

        # Save to database
        service = get_exchange_rate_service()
        success_count = 0
        error_count = 0

        for date_str, rate_data in rates_dict.items():
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                if service.save_exchange_rate(
                        date_obj,
                        rate_data['buy_rate'],
                        rate_data['sell_rate'],
                        source='CSV'
                ):
                    success_count += 1
                else:
                    error_count += 1
            except Exception as e:
                logger.error(f"Error saving rate for {date_str}: {str(e)}")
                error_count += 1

        logger.info(f"CSV import completed: {success_count} successful, {error_count} errors")

        return jsonify({
            'message': f'Successfully imported {success_count} exchange rates',
            'success_count': success_count,
            'error_count': error_count,
            'total_parsed': len(rates_dict)
        }), 200

    except Exception as e:
        logger.error(f"Error importing CSV exchange rates: {str(e)}")
        return jsonify({'error': 'Failed to import exchange rates', 'details': str(e)}), 500


@app.route('/api/exchange-rate/bulk-cache', methods=['POST'])
@login_required
def bulk_cache_exchange_rates():
    """
    Pre-populate exchange rates cache in database for a date range.

    This endpoint efficiently:
    1. Checks which dates in the range are missing from the database
    2. Fetches only missing dates from CBSL and stores them in the DB
    3. Returns summary of caching operation

    Request Body (JSON):
        start_date: Start date (YYYY-MM-DD). Required.
        end_date: End date (YYYY-MM-DD). Required.

    Returns:
        JSON with:
        - already_cached: Number of dates already in DB
        - newly_cached: Number of dates fetched and stored
        - failed: Number of dates that couldn't be fetched
        - message: Summary message
    """
    try:
        from services.exchange_rate_service import get_exchange_rate_service
        from datetime import datetime, timedelta

        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body is required'}), 400

        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')

        if not start_date_str or not end_date_str:
            return jsonify({'error': 'Both start_date and end_date are required'}), 400

        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError as e:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

        if start_date > end_date:
            return jsonify({'error': 'start_date must be before or equal to end_date'}), 400

        # Don't fetch dates too far in the future
        today = datetime.now().date()
        if start_date > today:
            return jsonify({'error': 'start_date cannot be in the future'}), 400
        if end_date > today:
            end_date = today

        service = get_exchange_rate_service()

        # Step 1: Get all dates that are already in the database (single query)
        import mysql.connector
        connection = mysql.connector.connect(
            host=os.environ.get('DB_HOST', 'localhost'),
            port=int(os.environ.get('DB_PORT', 3306)),
            user=os.environ.get('DB_USER', 'root'),
            password=os.environ.get('DB_PASSWORD', ''),
            database=os.environ.get('DB_NAME', 'budget_app')
        )
        cursor = connection.cursor()
        cursor.execute("""
                       SELECT date
                       FROM exchange_rates
                       WHERE date BETWEEN %s
                         AND %s
                       """, (start_date, end_date))

        existing_dates = {row[0] for row in cursor.fetchall()}
        cursor.close()
        connection.close()

        # Step 2: Determine which dates need to be fetched
        current_date = start_date
        dates_to_fetch = []
        while current_date <= end_date:
            if current_date not in existing_dates:
                dates_to_fetch.append(current_date)
            current_date += timedelta(days=1)

        already_cached = len(existing_dates)
        newly_cached = 0
        failed = 0

        logger.info(f"Bulk cache: {already_cached} already in DB, {len(dates_to_fetch)} dates to fetch")

        # Step 3: Fetch and store missing dates
        for date in dates_to_fetch:
            try:
                # This will fetch from CBSL and automatically save to DB
                rate_data = service.get_exchange_rate(date)
                if rate_data and rate_data.get('buy_rate'):
                    newly_cached += 1
                    logger.debug(f"Cached rate for {date}: {rate_data['buy_rate']} LKR")
                else:
                    failed += 1
                    logger.debug(f"Failed to fetch rate for {date}")
            except Exception as e:
                logger.error(f"Error fetching rate for {date}: {str(e)}")
                failed += 1

        total_dates = (end_date - start_date).days + 1
        logger.info(f"Bulk cache completed: {already_cached} existing, {newly_cached} new, {failed} failed")

        return jsonify({
            'already_cached': already_cached,
            'newly_cached': newly_cached,
            'failed': failed,
            'total_dates': total_dates,
            'message': f'Successfully cached {newly_cached} new exchange rates. {already_cached} were already cached.'
        }), 200

    except Exception as e:
        logger.error(f"Error in bulk cache exchange rates: {str(e)}")
        return jsonify({'error': 'Failed to cache exchange rates', 'details': str(e)}), 500


@app.route('/api/exchange-rate/hnb/current', methods=['GET'])
@login_required
def get_hnb_current_rate():
    """
    Get the latest cached USD to LKR exchange rate from HNB bank.

    Rates are refreshed automatically every hour by the background scheduler.
    Use POST /api/exchange-rate/hnb/refresh to force an immediate update.

    Returns:
        JSON with buy_rate, sell_rate, date, source, and updated_at
    """
    try:
        service = get_hnb_exchange_rate_service()
        rate_data = _resolve_rate(service, datetime.now().date())

        if rate_data:
            logger.info(f"HNB current rate: {rate_data}")
            return jsonify(rate_data), 200
        else:
            return jsonify({'error': 'HNB rate not yet available.'}), 404

    except Exception as e:
        logger.error(f"Error fetching HNB current rate: {str(e)}")
        return jsonify({'error': 'Failed to fetch exchange rate', 'details': str(e)}), 500


@app.route('/api/exchange-rate/hnb/refresh', methods=['POST'])
@login_required
def refresh_hnb_rate():
    """
    Manually refresh today's exchange rate from HNB.

    This forces a fresh fetch from the HNB API and updates the database.

    Returns:
        JSON with updated rate data
    """
    try:
        from services.hnb_exchange_rate_service import get_hnb_exchange_rate_service

        service = get_hnb_exchange_rate_service()
        rate_data = service.fetch_and_store_current_rate()

        if rate_data:
            logger.info(f"HNB rate refreshed: {rate_data}")
            return jsonify({
                'message': 'Exchange rate refreshed successfully',
                'rate': rate_data
            }), 200
        else:
            return jsonify({'error': 'Failed to refresh rate from HNB'}), 500

    except Exception as e:
        logger.error(f"Error refreshing HNB rate: {str(e)}")
        return jsonify({'error': 'Failed to refresh exchange rate', 'details': str(e)}), 500


@app.route('/api/exchange-rate/pb/current', methods=['GET'])
@login_required
def get_pb_current_rate():
    """
    Get the latest cached USD to LKR exchange rate from People's Bank.

    Rates are refreshed automatically every hour by the background scheduler.
    Use POST /api/exchange-rate/pb/refresh to force an immediate update.

    Returns:
        JSON with buy_rate, sell_rate, date, source, and updated_at
    """
    try:
        service = get_pb_exchange_rate_service()
        rate_data = _resolve_rate(service, datetime.now().date())

        if rate_data:
            logger.info(f"PB current rate: {rate_data}")
            return jsonify(rate_data), 200
        else:
            return jsonify({'error': "People's Bank rate not yet available."}), 404

    except Exception as e:
        logger.error(f"Error fetching PB current rate: {str(e)}")
        return jsonify({'error': 'Failed to fetch exchange rate', 'details': str(e)}), 500


@app.route('/api/exchange-rate/pb/refresh', methods=['POST'])
@login_required
def refresh_pb_rate():
    """
    Manually refresh today's exchange rate from People's Bank.

    This forces a fresh scrape from the People's Bank website and
    updates the database.

    Returns:
        JSON with updated rate data
    """
    try:
        service = get_pb_exchange_rate_service()
        rate_data = service.fetch_and_store_current_rate()

        if rate_data:
            logger.info(f"PB rate refreshed: {rate_data}")
            return jsonify({
                'message': 'Exchange rate refreshed successfully',
                'rate': rate_data
            }), 200
        else:
            return jsonify({'error': 'Failed to refresh rate from People\'s Bank'}), 500

    except Exception as e:
        logger.error(f"Error refreshing PB rate: {str(e)}")
        return jsonify({'error': 'Failed to refresh exchange rate', 'details': str(e)}), 500


@app.route('/api/exchange-rate/refresh-all', methods=['GET'])
@admin_required
def refresh_all_rates_manually():
    """Admin-only: trigger an immediate refresh of all exchange-rate sources
    regardless of the current refresh-mode setting.  Returns per-source
    results so the caller can see exactly which banks succeeded or failed."""
    try:
        results = refresh_all_exchange_rates(force=True)
        log_audit(session['user_id'], 'MANUAL_EXCHANGE_RATE_REFRESH')

        succeeded = [k for k, v in results.items() if v.get('status') == 'success']
        failed    = [k for k, v in results.items() if v.get('status') != 'success']

        status_code = 200 if succeeded else 500
        return jsonify({
            'message': f"{len(succeeded)} of {len(results)} source(s) refreshed successfully",
            'sources': results,
            'succeeded': succeeded,
            'failed': failed
        }), status_code
    except Exception as e:
        logger.error(f"Error in manual refresh-all: {str(e)}")
        return jsonify({'error': 'Refresh failed', 'details': str(e)}), 500


def token_required(f):
    """
    Decorator to require token authentication for routes.
    Extracts token from Authorization header: Bearer <token>

    IMPORTANT: This must be defined BEFORE any endpoints that use it.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        import jwt

        token = None

        # Get token from Authorization header
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                # Expected format: "Bearer <token>"
                token = auth_header.split(' ')[1]
            except IndexError:
                return jsonify({'error': 'Invalid authorization header format. Use: Bearer <token>'}), 401

        if not token:
            return jsonify({'error': 'Token is missing. Please provide token in Authorization header.'}), 401

        try:
            # Decode token (also verifies signature and expiry)
            payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired. Please generate a new token.'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token. Please provide a valid token.'}), 401
        except Exception as e:
            logger.error(f"Error validating token: {str(e)}")
            return jsonify({'error': 'Token validation failed'}), 401

        # Validate token against the tokens table
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Token validation failed'}), 401
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT id, is_revoked, expires_at < UTC_TIMESTAMP() AS is_expired FROM tokens WHERE token = %s AND user_id = %s",
                (token, payload['user_id'])
            )
            token_record = cursor.fetchone()

            if not token_record:
                return jsonify({'error': 'Token not recognized. Please generate a new token.'}), 401
            if token_record['is_revoked']:
                return jsonify({'error': 'Token has been revoked. Please generate a new token.'}), 401
            if token_record['is_expired']:
                return jsonify({'error': 'Token has expired. Please generate a new token.'}), 401

            cursor.execute(
                "UPDATE tokens SET last_used_at = CURRENT_TIMESTAMP WHERE id = %s",
                (token_record['id'],)
            )
            connection.commit()
        except Exception as e:
            logger.error(f"Error validating token in database: {str(e)}")
            return jsonify({'error': 'Token validation failed'}), 401
        finally:
            cursor.close()
            connection.close()

        # Store user info in request context
        request.current_user = {
            'user_id': payload['user_id'],
            'username': payload['username'],
            'is_admin': payload.get('is_admin', False)
        }

        return f(*args, **kwargs)

    return decorated_function


# ==================================================
# TOKEN GENERATION ENDPOINT (ADD THIS SECOND)
# ==================================================

@app.route('/api/auth/token', methods=['POST'])
def generate_token():
    """
    Generate authentication token using username and password.

    Request Body (JSON):
        {
            "username": "user@example.com",
            "password": "password123"
        }

    Returns:
        JSON with token and expiry or error message
    """
    try:
        import jwt
        from datetime import datetime, timedelta

        data = request.get_json()

        if not data:
            return jsonify({'error': 'Request body is required'}), 400

        username = data.get('username')
        password = data.get('password')

        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400

        logger.info(f"Token generation attempt for username: {username}")

        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = connection.cursor(dictionary=True)

        try:
            # Check if username is an email or username
            cursor.execute("SELECT * FROM users WHERE username = %s OR email = %s",
                           (username, username))
            user = cursor.fetchone()

            if user and check_password_hash(user['password_hash'], password):
                # Check if user account is active
                if not user.get('is_active', True):
                    logger.warning(f"Token generation failed for username: {username} - Account is deactivated")
                    return jsonify(
                        {'error': 'Your account has been deactivated. Please contact an administrator.'}), 403

                # Generate JWT token
                # Token expires in 24 hours
                expiry = datetime.utcnow() + timedelta(hours=24)

                payload = {
                    'user_id': user['id'],
                    'username': user['username'],
                    'is_admin': user.get('is_admin', False),
                    'exp': expiry,
                    'iat': datetime.utcnow()
                }

                # Use app secret key for JWT encoding
                token = jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')

                # Upsert: one active token row per user
                cursor.execute("""
                    INSERT INTO tokens (user_id, token, expires_at)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        token = VALUES(token),
                        expires_at = VALUES(expires_at),
                        is_revoked = FALSE,
                        created_at = CURRENT_TIMESTAMP,
                        last_used_at = NULL
                """, (user['id'], token, expiry))
                connection.commit()

                logger.info(f"Token generated successfully for user: {username} (ID: {user['id']})")

                return jsonify({
                    'token': token,
                    'expires_at': expiry.isoformat(),
                    'user': {
                        'id': user['id'],
                        'username': user['username'],
                        'email': user['email'],
                        'is_admin': user.get('is_admin', False)
                    }
                }), 200
            else:
                logger.warning(f"Token generation failed for username: {username} - Invalid credentials")
                return jsonify({'error': 'Invalid credentials'}), 401

        except Error as e:
            logger.error(f"Database error during token generation: {str(e)}")
            return jsonify({'error': str(e)}), 500
        finally:
            cursor.close()
            connection.close()

    except ImportError:
        logger.error("PyJWT library not installed")
        return jsonify({'error': 'Token authentication not available. Install PyJWT library.'}), 500
    except Exception as e:
        logger.error(f"Error generating token: {str(e)}")
        return jsonify({'error': 'Failed to generate token', 'details': str(e)}), 500


# ==================================================
# TOKEN REVOCATION ENDPOINT
# ==================================================

@app.route('/api/auth/token/revoke', methods=['POST'])
@token_required
def revoke_token():
    """
    Revoke the token that was used to make this request.
    The token is marked as revoked in the database and will be
    rejected on all subsequent requests.

    Returns:
        JSON with confirmation message
    """
    try:
        token = request.headers['Authorization'].split(' ')[1]

        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = connection.cursor()
        try:
            cursor.execute(
                "UPDATE tokens SET is_revoked = TRUE WHERE token = %s",
                (token,)
            )
            connection.commit()
            return jsonify({'message': 'Token revoked successfully'}), 200
        except Error as e:
            logger.error(f"Database error revoking token: {str(e)}")
            return jsonify({'error': 'Failed to revoke token'}), 500
        finally:
            cursor.close()
            connection.close()
    except Exception as e:
        logger.error(f"Error revoking token: {str(e)}")
        return jsonify({'error': 'Failed to revoke token', 'details': str(e)}), 500


# ==================================================
# BANK EXCHANGE RATE API ENDPOINTS
# ==================================================

@app.route('/api/exchange-rate/banks', methods=['GET'])
@token_required
def get_all_bank_rates_for_date():
    """
    Get all bank exchange rates for a specific date.
    Query Parameters:
        date: Date in YYYY-MM-DD format (required)
    Returns:
        JSON list of rates for all banks on that date
    """
    try:
        from services.exchange_rate_service import get_exchange_rate_service

        date_str = request.args.get('date')
        if not date_str:
            return jsonify({'error': 'Date is required (YYYY-MM-DD)'}), 400
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD.'}), 400

        rates = []

        # Get HNB rate (live-fetch in manual mode when today is missing)
        try:
            hnb_service = get_hnb_exchange_rate_service()
            hnb_rate = _resolve_rate(hnb_service, date)
            if hnb_rate:
                hnb_rate['bank'] = 'HNB'
                rates.append(hnb_rate)
        except Exception as e:
            logger.warning(f"Failed to get HNB rate for {date_str}: {str(e)}")

        # Get People's Bank rate (live-fetch in manual mode when today is missing)
        try:
            pb_service = get_pb_exchange_rate_service()
            pb_rate = _resolve_rate(pb_service, date)
            if pb_rate:
                pb_rate['bank'] = 'PB'
                rates.append(pb_rate)
        except Exception as e:
            logger.warning(f"Failed to get PB rate for {date_str}: {str(e)}")

        # Get CBSL rate
        try:
            cbsl_service = get_exchange_rate_service()
            cbsl_rate = cbsl_service.get_exchange_rate(date)
            if cbsl_rate and isinstance(cbsl_rate, dict):
                # Guard: only label as CBSL if source is actually CBSL (or absent = live scrape)
                source = cbsl_rate.get('source')
                if source is None or source in ('CBSL', 'CBSL_BULK'):
                    cbsl_rate['bank'] = 'CBSL'
                    rates.append(cbsl_rate)
        except Exception as e:
            logger.warning(f"Failed to get CBSL rate for {date_str}: {str(e)}")

        if rates:
            return jsonify(rates), 200
        else:
            return jsonify({'error': 'No rates found for this date'}), 404
    except Exception as e:
        logger.error(f"Error fetching all bank rates: {str(e)}")
        return jsonify({'error': 'Failed to fetch bank rates', 'details': str(e)}), 500


@app.route('/api/exchange-rate/bank/<bank_code>', methods=['GET'])
@token_required
def get_bank_rate_for_date(bank_code):
    """
    Get exchange rate for a specific bank and date.
    Query Parameters:
        date: Date in YYYY-MM-DD format (required)
    Returns:
        JSON with buy_rate, sell_rate, date, source, bank
    """
    try:
        from services.exchange_rate_service import get_exchange_rate_service

        date_str = request.args.get('date')
        if not date_str:
            return jsonify({'error': 'Date is required (YYYY-MM-DD)'}), 400
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD.'}), 400

        bank_code_lower = bank_code.lower()
        rate = None
        
        if bank_code_lower == 'hnb':
            try:
                service = get_hnb_exchange_rate_service()
                rate = _resolve_rate(service, date)
            except Exception as e:
                logger.error(f"Error fetching HNB rate for {date_str}: {str(e)}")
                return jsonify({'error': f'Failed to fetch HNB rate', 'details': str(e)}), 500
        elif bank_code_lower == 'pb':
            try:
                service = get_pb_exchange_rate_service()
                rate = _resolve_rate(service, date)
            except Exception as e:
                logger.error(f"Error fetching PB rate for {date_str}: {str(e)}")
                return jsonify({'error': f'Failed to fetch PB rate', 'details': str(e)}), 500
        elif bank_code_lower == 'cbsl':
            try:
                service = get_exchange_rate_service()
                rate = service.get_exchange_rate(date)
                # Guard: reject if the service returned another bank's row
                if rate and rate.get('source') in ('HNB', 'PB'):
                    rate = None
            except Exception as e:
                logger.error(f"Error fetching CBSL rate for {date_str}: {str(e)}")
                return jsonify({'error': f'Failed to fetch CBSL rate', 'details': str(e)}), 500
        else:
            return jsonify({'error': f'Unknown bank code: {bank_code}. Supported: hnb, pb, cbsl'}), 400

        if rate and isinstance(rate, dict):
            rate['bank'] = bank_code_lower.upper()
            return jsonify(rate), 200
        else:
            return jsonify({'error': f'Exchange rate not available for {bank_code_lower.upper()} on {date_str}'}), 404
    except Exception as e:
        logger.error(f"Error fetching {bank_code} rate: {str(e)}")
        return jsonify({'error': 'Failed to fetch bank rate', 'details': str(e)}), 500


@app.route('/api/exchange-rate/hnb', methods=['GET'])
@token_required
def get_hnb_rate_for_date():
    """
    Get HNB exchange rate for a specific date from cache.

    Rates are refreshed automatically every hour by the background scheduler.

    Query Parameters:
        date: Date in ddmmyyyy format (optional, defaults to today)
              Example: 01022026 for February 1, 2026

    Returns:
        JSON with buy_rate, sell_rate, date, and source

    Example Usage:
        GET /api/exchange-rate/hnb?date=01022026
        GET /api/exchange-rate/hnb  (returns today's rate)
    """
    try:
        date_str = request.args.get('date')

        if date_str:
            try:
                if len(date_str) != 8:
                    return jsonify({
                        'error': 'Invalid date format. Use ddmmyyyy (e.g., 01022026 for Feb 1, 2026)'
                    }), 400

                date = datetime.strptime(date_str, '%d%m%Y').date()

            except ValueError:
                return jsonify({
                    'error': 'Invalid date format. Use ddmmyyyy (e.g., 01022026 for Feb 1, 2026)'
                }), 400
        else:
            date = datetime.now().date()

        service = get_hnb_exchange_rate_service()
        rate = _resolve_rate(service, date)

        if rate:
            logger.info(f"HNB rate retrieved for {date_str or 'today'}: {rate}")
            return jsonify(rate), 200
        else:
            return jsonify({
                'error': 'Exchange rate not available for this date'
            }), 404

    except Exception as e:
        logger.error(f"Error getting HNB rate: {str(e)}")
        return jsonify({
            'error': 'Failed to get exchange rate',
            'details': str(e)
        }), 500


@app.route('/api/exchange-rate/pb', methods=['GET'])
@token_required
def get_pb_rate_for_date():
    """
    Get People's Bank exchange rate for a specific date from cache.

    Rates are refreshed automatically every hour by the background scheduler.

    Query Parameters:
        date: Date in ddmmyyyy format (optional, defaults to today)
              Example: 01022026 for February 1, 2026

    Returns:
        JSON with buy_rate, sell_rate, date, and source

    Example Usage:
        GET /api/exchange-rate/pb?date=01022026
        GET /api/exchange-rate/pb  (returns today's rate)
    """
    try:
        date_str = request.args.get('date')

        if date_str:
            try:
                if len(date_str) != 8:
                    return jsonify({
                        'error': 'Invalid date format. Use ddmmyyyy (e.g., 01022026 for Feb 1, 2026)'
                    }), 400

                date = datetime.strptime(date_str, '%d%m%Y').date()

            except ValueError:
                return jsonify({
                    'error': 'Invalid date format. Use ddmmyyyy (e.g., 01022026 for Feb 1, 2026)'
                }), 400
        else:
            date = datetime.now().date()

        service = get_pb_exchange_rate_service()
        rate = _resolve_rate(service, date)

        if rate:
            logger.info(f"PB rate retrieved for {date_str or 'today'}: {rate}")
            return jsonify(rate), 200
        else:
            return jsonify({
                'error': 'Exchange rate not available for this date'
            }), 404

    except Exception as e:
        logger.error(f"Error getting PB rate: {str(e)}")
        return jsonify({
            'error': 'Failed to get exchange rate',
            'details': str(e)
        }), 500


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

    # Start exchange-rate refresh scheduler.
    # Interval is read from app_settings; falls back to 60 min when the table
    # does not exist yet or the DB is unreachable.
    # next_run_time=datetime.now() warms the cache before the first request.
    interval_minutes = int(get_setting('exchange_rate_refresh_interval_minutes', '60'))
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=refresh_all_exchange_rates,
        trigger='interval',
        minutes=interval_minutes,
        next_run_time=datetime.now(),
        id='refresh_exchange_rates'
    )
    scheduler.start()
    logger.info(f"Exchange rate refresh scheduler started (interval: {interval_minutes} min)")

    # Use debug=False for production
    # Set to True for development (detailed error messages)
    app.run(debug=False, host='0.0.0.0', port=5003)
