import calendar
import csv
import io
import json
import logging
import os
import re
import requests
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from decimal import Decimal
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, make_response
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from mysql.connector import Error
from werkzeug.security import generate_password_hash, check_password_hash

from services.hnb_exchange_rate_service import get_hnb_exchange_rate_service
from services.pb_exchange_rate_service import get_pb_exchange_rate_service
from services.sampath_exchange_rate_service import get_sampath_exchange_rate_service
from services.backup_service import get_backup_service
from services.appwrite_file_service import get_appwrite_file_service
from services.exchange_rate_routes import register_exchange_rate_routes
from services.tax_service import register_tax_routes
from services.transaction_service import register_transaction_routes

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
    from appwrite.client import Client
    from appwrite.services.storage import Storage
    from appwrite.input_file import InputFile
    from appwrite.id import ID

    APPWRITE_AVAILABLE = True
except ImportError:
    APPWRITE_AVAILABLE = False
    logger.warning("appwrite not installed. Bill image upload will be disabled.")

# PyPDF2 removed - PDFs are converted to images on frontend before upload

logger.info("Environment variables loaded")

# Initialize Appwrite client (will be set up after helper functions are defined)
appwrite_client = None
appwrite_storage = None
APPWRITE_BUCKET_ID = None

# Initialize Appwrite file service
appwrite_file_service = get_appwrite_file_service()


# Custom JSON provider to handle Decimal objects
class DecimalJSONProvider(DefaultJSONProvider):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


# Flask app configuration
app = Flask(__name__)
app.json = DecimalJSONProvider(app)

# Require SECRET_KEY from environment (no fallback for security)
if not os.environ.get('SECRET_KEY'):
    raise ValueError("SECRET_KEY environment variable is required. Please set it in your .env file.")
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=365)  # Remember me for 1 year

# Session cookie configuration for mobile browser compatibility
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Allow cookies in same-site context
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevent JavaScript access for security
# Enable secure cookies only when HTTPS is available (production)
IS_HTTPS = os.environ.get('HTTPS_ENABLED', 'False').lower() == 'true'
app.config['SESSION_COOKIE_SECURE'] = IS_HTTPS
app.config['SESSION_COOKIE_NAME'] = 'session'  # Explicit session cookie name
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max upload size

# Configure CORS with restricted origins for security
allowed_origins = []
cors_origins_env = os.environ.get('CORS_ALLOWED_ORIGINS', '')

if cors_origins_env:
    # Use explicitly configured origins from environment variable
    allowed_origins = [origin.strip() for origin in cors_origins_env.split(',') if origin.strip()]
else:
    # Fallback: Allow localhost for development, or require explicit configuration for production
    if IS_HTTPS:
        logger.warning("HTTPS enabled but CORS_ALLOWED_ORIGINS not set. CORS will be restrictive.")
        allowed_origins = []  # No origins allowed - must be explicitly configured
    else:
        # Development mode - allow localhost
        allowed_origins = [
            'http://localhost:5000',
            'http://127.0.0.1:5000'
        ]

if allowed_origins:
    CORS(app, origins=allowed_origins, supports_credentials=True)
    logger.info(f"CORS configured with allowed origins: {allowed_origins}")
else:
    logger.warning("CORS not configured - no origins allowed. Set CORS_ALLOWED_ORIGINS in environment.")

# ---------------------------------------------------------------------------
# Rate Limiting Configuration
# ---------------------------------------------------------------------------
# Initialize Flask-Limiter for rate limiting (brute force protection)
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=[],  # No global limits, we'll set per-endpoint
    storage_uri="memory://",  # Use in-memory storage (switch to Redis for production scaling)
    strategy="fixed-window",  # Fixed window strategy
)

# Load rate limit thresholds from environment variables with fallback defaults
RATE_LIMIT_LOGIN = os.environ.get('RATE_LIMIT_LOGIN', '5 per 15 minutes')
RATE_LIMIT_REGISTER = os.environ.get('RATE_LIMIT_REGISTER', '3 per hour')
RATE_LIMIT_CHANGE_PASSWORD = os.environ.get('RATE_LIMIT_CHANGE_PASSWORD', '3 per hour')
RATE_LIMIT_ADMIN = os.environ.get('RATE_LIMIT_ADMIN', '30 per minute')
RATE_LIMIT_API = os.environ.get('RATE_LIMIT_API', '100 per minute')

logger.info(
    f"Rate limiting configured - Login: {RATE_LIMIT_LOGIN}, Register: {RATE_LIMIT_REGISTER}, Admin: {RATE_LIMIT_ADMIN}")


# ---------------------------------------------------------------------------
# Rate Limit Error Handler
# ---------------------------------------------------------------------------
@app.errorhandler(429)
def ratelimit_handler(e):
    """Handle rate limit exceeded errors."""
    logger.warning(f"Rate limit exceeded for IP: {get_remote_address()} - {request.path}")
    return jsonify({
        'error': 'Rate limit exceeded',
        'message': 'Too many requests. Please try again later.',
        'retry_after': e.description
    }), 429


# ---------------------------------------------------------------------------
# Cache Control - Disable caching during development
# ---------------------------------------------------------------------------
@app.after_request
def add_header(response):
    """
    Add headers to disable caching for HTML, CSS, and JS files.
    This ensures changes are immediately visible during development.

    Remove or modify this in production for better performance.
    """
    # Don't cache HTML, CSS, JS, or JSON responses
    if response.content_type and any(ct in response.content_type for ct in
                                     ['text/html', 'text/css', 'application/javascript',
                                      'application/json', 'text/javascript']):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response


# ---------------------------------------------------------------------------
# Database connection pool (centralised in db.py)
# ---------------------------------------------------------------------------
from db import get_db_connection, DB_CONFIG  # noqa: E402

if DB_CONFIG is None:
    logger.warning(
        "Database is NOT configured. The application will start but all "
        "database operations will fail. Copy .env.example to .env and fill "
        "in your database credentials, then restart the application.")



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


# Initialize Appwrite client
if APPWRITE_AVAILABLE:
    try:
        # Load from environment variables
        appwrite_endpoint = os.environ.get('APPWRITE_ENDPOINT')
        appwrite_project_id = os.environ.get('APPWRITE_PROJECT_ID')
        appwrite_api_key = os.environ.get('APPWRITE_API_KEY')
        APPWRITE_BUCKET_ID = os.environ.get('APPWRITE_BUCKET_ID')

        if all([appwrite_endpoint, appwrite_project_id, appwrite_api_key, APPWRITE_BUCKET_ID]):
            appwrite_client = Client()
            appwrite_client.set_endpoint(appwrite_endpoint)
            appwrite_client.set_project(appwrite_project_id)
            appwrite_client.set_key(appwrite_api_key)

            appwrite_storage = Storage(appwrite_client)
            logger.info(f"✅ Appwrite storage initialized (endpoint: {appwrite_endpoint})")
        else:
            logger.warning("Appwrite credentials incomplete. Set them in .env file.")
            appwrite_storage = None
    except Exception as e:
        logger.error(f"Failed to initialize Appwrite client: {e}")
        appwrite_storage = None


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
    """Decorator to require admin privileges for routes.

    Uses the ``is_admin`` flag cached in the session at login time so that
    no extra database round-trip is needed on every admin request.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first.', 'warning')
            return redirect(url_for('login'))

        if not session.get('is_admin'):
            flash('Access denied. Admin privileges required.', 'danger')
            return redirect(url_for('dashboard'))

        return f(*args, **kwargs)

    return decorated_function


def token_required(f):
    """Decorator to require token authentication for routes.
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


# Routes


@app.before_request
def make_session_permanent():
    """Ensure authenticated sessions always use a persistent cookie.

    Without this, non-'Remember Me' sessions use browser-session cookies
    that are deleted when the tab or browser is closed. By always marking
    authenticated sessions as permanent, the cookie is sent with a Max-Age
    equal to PERMANENT_SESSION_LIFETIME (365 days) so the user stays
    logged in across tab/browser restarts.
    """
    if 'user_id' in session:
        session.permanent = True


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
@limiter.limit(RATE_LIMIT_REGISTER)
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


@app.route('/login', methods=['GET', 'POST'])
@limiter.limit(RATE_LIMIT_LOGIN)
def login():
    """User login."""
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        username = data.get('username')
        password = data.get('password')
        remember_me = bool(data.get('remember_me', False))

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

                    # Always set session as permanent so the cookie is sent
                    # with Max-Age (persists across tab/browser restarts).
                    session.permanent = True
                    session['user_id'] = user['id']
                    session['username'] = user['username']
                    session['is_admin'] = user.get('is_admin', False)
                    session.modified = True
                    logger.info(
                        f"Login successful for user: {username} (ID: {user['id']}), is_admin: {user.get('is_admin', False)}")

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

    # If user is already authenticated, redirect to dashboard/mobile
    if 'user_id' in session:
        user_agent = request.headers.get('User-Agent', '').lower()
        is_mobile = any(device in user_agent for device in
                        ['android', 'webos', 'iphone', 'ipad', 'ipod', 'blackberry', 'windows phone'])
        if is_mobile:
            return redirect(url_for('mobile'))
        return redirect(url_for('dashboard'))

    return render_template('login.html')


@app.route('/logout')
def logout():
    """User logout."""
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


@app.route('/api/change-password', methods=['POST'])
@login_required
@limiter.limit(RATE_LIMIT_CHANGE_PASSWORD)
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


@app.route('/api/user-preferences', methods=['GET'])
@login_required
@limiter.limit(RATE_LIMIT_API)
def get_user_preferences():
    """Get current user's preferences."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = connection.cursor(dictionary=True)
    user_id = session['user_id']

    try:
        cursor.execute("SELECT default_page FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()

        if not user:
            return jsonify({'error': 'User not found'}), 404

        return jsonify({
            'default_page': user.get('default_page', 'transactions')
        }), 200

    except Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


@app.route('/api/user-preferences', methods=['PUT'])
@login_required
@limiter.limit(RATE_LIMIT_API)
def update_user_preferences():
    """Update current user's preferences."""
    data = request.get_json()
    default_page = data.get('default_page')

    # Validate default_page value
    valid_pages = ['transactions', 'tax', 'reports', 'rateTrends']
    if default_page not in valid_pages:
        return jsonify({
            'error': f'Invalid default_page. Must be one of: {", ".join(valid_pages)}'
        }), 400

    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = connection.cursor(dictionary=True)
    user_id = session['user_id']

    try:
        cursor.execute(
            "UPDATE users SET default_page = %s WHERE id = %s",
            (default_page, user_id)
        )
        connection.commit()

        logger.info(f"User {session.get('username')} updated default_page to {default_page}")
        return jsonify({
            'message': 'Preferences updated successfully',
            'default_page': default_page
        }), 200

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
                                  u.default_page,
                                  u.created_at,
                                  COUNT(DISTINCT mr.id) as monthly_records_count,
                                  COUNT(DISTINCT t.id)  as transactions_count
                           FROM users u
                                    LEFT JOIN monthly_records mr ON u.id = mr.user_id
                                    LEFT JOIN transactions t ON mr.id = t.monthly_record_id
                           GROUP BY u.id, u.username, u.email, u.is_admin, u.is_active, u.last_login, u.default_page, u.created_at
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
@limiter.limit(RATE_LIMIT_ADMIN)
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


# ==================================================
# REGISTER SERVICE ROUTES
# ==================================================
# Register all service routes from the dedicated service modules
# This must be called after all decorators and helper functions are defined
register_exchange_rate_routes(app, login_required, admin_required, token_required, log_audit)
register_tax_routes(app, login_required)
register_transaction_routes(app, login_required, limiter, RATE_LIMIT_API, token_required)


@app.route('/api/admin/users/<int:user_id>/toggle-active', methods=['POST'])
@admin_required
@limiter.limit(RATE_LIMIT_ADMIN)
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
@limiter.limit(RATE_LIMIT_ADMIN)
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
@limiter.limit(RATE_LIMIT_ADMIN)
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

        # Get all attachments from user's transactions before deletion
        cursor.execute("""
            SELECT t.attachments 
            FROM transactions t
            INNER JOIN monthly_records mr ON t.monthly_record_id = mr.id
            WHERE mr.user_id = %s AND t.attachments IS NOT NULL
        """, (user_id,))
        transactions_with_attachments = cursor.fetchall()

        # Delete all attachments from Appwrite before deleting user
        if appwrite_file_service.is_available() and transactions_with_attachments:
            deleted_count = 0
            for txn in transactions_with_attachments:
                attachments_value = txn['attachments']
                # Split comma-separated GUIDs
                attachment_guids = [guid.strip() for guid in attachments_value.split(',') if guid.strip()]

                for attachment_guid in attachment_guids:
                    success, error = appwrite_file_service.delete_file(attachment_guid)
                    if success:
                        deleted_count += 1
                    else:
                        logger.warning(f"Failed to delete attachment {attachment_guid}: {error}")

            if deleted_count > 0:
                logger.info(f"Deleted {deleted_count} attachment(s) from Appwrite for user {user_id}")

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


@app.route('/api/admin/users/<int:user_id>/default-page', methods=['PUT'])
@admin_required
@limiter.limit(RATE_LIMIT_ADMIN)
def admin_update_user_default_page(user_id):
    """Update a user's default landing page (admin only)."""
    data = request.get_json()
    default_page = data.get('default_page')

    # Validate default_page value
    valid_pages = ['transactions', 'tax', 'reports', 'rateTrends']
    if default_page not in valid_pages:
        return jsonify({
            'error': f'Invalid default_page. Must be one of: {", ".join(valid_pages)}'
        }), 400

    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = connection.cursor(dictionary=True)
    admin_id = session['user_id']

    try:
        # Get user details
        cursor.execute("SELECT username FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()

        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Update default page
        cursor.execute(
            "UPDATE users SET default_page = %s WHERE id = %s",
            (default_page, user_id)
        )
        connection.commit()

        # Log the action
        log_audit(admin_id, 'Updated user preferences', user_id,
                  f"User '{user['username']}' default page changed to '{default_page}'")

        logger.info(f"Admin {admin_id} updated default_page for user {user_id} ({user['username']}) to {default_page}")

        return jsonify({
            'message': 'Default page updated successfully',
            'default_page': default_page
        }), 200

    except Error as e:
        logger.error(f"Error updating user default page: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


@app.route('/api/admin/audit-logs', methods=['GET'])
@admin_required
@limiter.limit(RATE_LIMIT_ADMIN)
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
@limiter.limit(RATE_LIMIT_ADMIN)
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


@app.route('/api/settings/upload-mode', methods=['GET'])
def get_upload_mode():
    """Public endpoint to get bill upload mode (sequential vs batch).
    No authentication required - used by client-side to determine upload strategy."""
    mode = get_setting('bill_upload_mode', 'sequential')
    logger.info(f"Upload mode requested: returning '{mode}'")
    return jsonify({'upload_mode': mode}), 200


@app.route('/api/admin/settings/<string:key>', methods=['PUT'])
@admin_required
@limiter.limit(RATE_LIMIT_ADMIN)
def update_admin_setting(key):
    """Update a single application setting.  Only keys that already exist in
    app_settings may be written — arbitrary keys are rejected."""
    data = request.get_json()
    if not data or 'value' not in data:
        return jsonify({'error': "'value' field is required"}), 400

    new_value = str(data['value'])

    # Key-specific validation
    if key == 'bill_upload_mode':
        if new_value not in ('sequential', 'batch'):
            return jsonify({'error': "Value must be 'sequential' or 'batch'"}), 400

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


# NOTE: The old /api/admin/db-backup route (manual SQL download) was removed.
# Use /api/admin/trigger-backup instead, which creates, compresses, encrypts
# and uploads backups to Appwrite via BackupService.


# ---------------------------------------------------------------------------
# Async DB backup → Appwrite upload (triggered by external cron)
# ---------------------------------------------------------------------------

def _run_backup_and_upload():
    """Generate a MySQL database backup and upload it to Appwrite.

    Uses the BackupService to create, compress, encrypt and upload backups.
    """
    backup_service = get_backup_service()
    return backup_service.create_and_upload_backup()


@app.route('/api/admin/trigger-backup', methods=['GET'])
def trigger_db_backup():
    """Trigger a database backup that uploads to Appwrite.

    Can run synchronously (for Vercel) or asynchronously (for local dev).
    Set BACKUP_MODE=sync in environment for Vercel/serverless platforms.
    """
    # Get allowed origins from environment variable
    backup_origins_env = os.environ.get('BACKUP_ALLOWED_ORIGINS', '')
    allowed_origins = [origin.strip() for origin in backup_origins_env.split(',') if origin.strip()]

    # Get local patterns from environment variable
    local_patterns_env = os.environ.get('BACKUP_LOCAL_PATTERNS', 'localhost,127.0.0.1')
    local_patterns = [pattern.strip() for pattern in local_patterns_env.split(',') if pattern.strip()]

    origin = request.headers.get('Origin', '')
    referer = request.headers.get('Referer', '')
    user_agent = request.headers.get('User-Agent', '')
    remote_addr = request.remote_addr or ''

    origin_ok = any(origin.startswith(a) for a in allowed_origins)
    referer_ok = any(referer.startswith(a) for a in allowed_origins)
    ua_ok = 'cron-job.org' in user_agent.lower()
    local_origin = any(p in origin for p in local_patterns) or origin.startswith(
        'http://localhost') or origin.startswith('http://127.0.0.1')
    local_referer = any(p in referer for p in local_patterns) or referer.startswith(
        'http://localhost') or referer.startswith('http://127.0.0.1')
    local_addr = any(remote_addr.startswith(p) for p in local_patterns)

    if not (origin_ok or referer_ok or ua_ok or local_origin or local_referer or local_addr):
        logger.warning("Unauthorized backup trigger — Origin: %s, Referer: %s, UA: %s, Remote: %s",
                       origin, referer, user_agent, remote_addr)
        return jsonify({'error': 'Access denied',
                        'message': 'This endpoint is only accessible from authorized sources'}), 403

    # Determine if we should run synchronously (for Vercel) or async (for local)
    backup_mode = os.environ.get('BACKUP_MODE', 'async').lower()

    if backup_mode == 'sync':
        # Run synchronously (Vercel-friendly)
        logger.info("Starting synchronous database backup")
        try:
            success, message = _run_backup_and_upload()
            if success:
                return jsonify({
                    'status': 'completed',
                    'message': message
                }), 200
            else:
                return jsonify({
                    'status': 'failed',
                    'error': message
                }), 500
        except Exception as e:
            logger.error("Backup failed with exception: %s", e, exc_info=True)
            return jsonify({
                'status': 'failed',
                'error': str(e)
            }), 500
    else:
        # Run asynchronously (local dev)
        def _async_backup_wrapper():
            try:
                success, message = _run_backup_and_upload()
                if success:
                    logger.info("Background backup completed: %s", message)
                else:
                    logger.error("Background backup failed: %s", message)
            except Exception as e:
                logger.error("Background backup exception: %s", e, exc_info=True)

        thread = threading.Thread(target=_async_backup_wrapper, daemon=True)
        thread.start()
        logger.info("Database backup triggered (background thread started)")

        return jsonify({
            'status': 'triggered',
            'message': 'Database backup started in background. It will be uploaded to Appwrite upon completion.',
        }), 202


@app.route('/api/admin/users/<int:user_id>/payment-methods', methods=['GET'])
@admin_required
@limiter.limit(RATE_LIMIT_ADMIN)
def admin_get_user_payment_methods(user_id):
    """Return active payment methods for a given user (admin only)."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("""
                       SELECT id, name, type, color
                       FROM payment_methods
                       WHERE user_id = %s AND is_active = TRUE
                       ORDER BY name
                       """, (user_id,))
        return jsonify(cursor.fetchall())
    except Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


@app.route('/api/admin/import-csv', methods=['POST'])
@admin_required
@limiter.limit(RATE_LIMIT_ADMIN)
def admin_import_csv():
    """Import transactions from a CSV file for a specific user/month/year.

    CSV format: Description, Credit, Debit, Note, Method
    Amounts may have a currency prefix (e.g. "Rs") and thousand-separators.

    Accepts an optional ``method_mapping`` JSON field (form-data string):
        { "CsvMethodName": <payment_method_id | "__create__"  | "__skip__"> , ... }

    - An integer id means "map to this existing payment method".
    - ``"__create__"`` means "create a new payment method with that name".
    - ``"__skip__"`` means "leave payment_method_id NULL for those rows".
    - If a CSV method name is not in the mapping it falls back to
      auto-matching by name (case-insensitive) or creating a new method.
    """
    # ── Validate inputs ──────────────────────────────────────────
    if 'file' not in request.files:
        return jsonify({'error': 'No CSV file provided'}), 400

    csv_file = request.files['file']
    if not csv_file.filename or not csv_file.filename.lower().endswith('.csv'):
        return jsonify({'error': 'File must be a .csv file'}), 400

    target_user_id = request.form.get('user_id', type=int)
    year = request.form.get('year', type=int)
    month = request.form.get('month', type=int)

    if not target_user_id or not year or not month:
        return jsonify({'error': 'user_id, year and month are required'}), 400

    if month < 1 or month > 12:
        return jsonify({'error': 'month must be between 1 and 12'}), 400

    # Optional method mapping from the frontend
    method_mapping_raw = request.form.get('method_mapping')
    method_mapping = {}
    if method_mapping_raw:
        try:
            method_mapping = json.loads(method_mapping_raw)
        except (json.JSONDecodeError, TypeError):
            return jsonify({'error': 'Invalid method_mapping JSON'}), 400

    # ── Parse CSV ────────────────────────────────────────────────
    import re

    def parse_amount(raw):
        """Strip currency prefix/symbols and thousand-separators, return Decimal or None."""
        if raw is None:
            return None
        raw = str(raw).strip()
        if not raw:
            return None
        # Remove common currency prefixes (Rs, Rs., LKR, $, etc.) and spaces
        raw = re.sub(r'^[A-Za-z$.\s]+', '', raw)
        # Remove thousand-separators
        raw = raw.replace(',', '')
        if not raw:
            return None
        try:
            val = Decimal(raw)
            return val if val > 0 else None
        except Exception:
            return None

    try:
        stream = io.StringIO(csv_file.read().decode('utf-8-sig'))
        reader = csv.DictReader(stream)

        # Normalise header names (strip whitespace, lowercase)
        if reader.fieldnames:
            reader.fieldnames = [f.strip() for f in reader.fieldnames]

        rows = []
        for line_no, row in enumerate(reader, start=2):
            # Normalise keys
            row = {k.strip().lower(): v for k, v in row.items() if k}
            description = (row.get('description') or '').strip()
            if not description:
                continue  # skip blank rows

            debit = parse_amount(row.get('debit'))
            credit = parse_amount(row.get('credit'))
            note = (row.get('note') or row.get('notes') or '').strip()
            method = (row.get('method') or row.get('payment method') or '').strip()

            rows.append({
                'description': description,
                'debit': debit,
                'credit': credit,
                'note': note,
                'method': method,
            })

        if not rows:
            return jsonify({'error': 'CSV file contains no valid rows'}), 400

    except UnicodeDecodeError:
        return jsonify({'error': 'File encoding not supported. Please use UTF-8.'}), 400
    except Exception as e:
        logger.error(f"CSV parse error: {e}")
        return jsonify({'error': f'Failed to parse CSV: {str(e)}'}), 400

    # ── Database operations ──────────────────────────────────────
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = connection.cursor(dictionary=True)
    admin_id = session['user_id']

    try:
        # Verify target user exists
        cursor.execute("SELECT id, username FROM users WHERE id = %s", (target_user_id,))
        target_user = cursor.fetchone()
        if not target_user:
            return jsonify({'error': 'Target user not found'}), 404

        # Get or create monthly record
        month_name = calendar.month_name[month]
        cursor.execute("""
                       INSERT INTO monthly_records (user_id, year, month, month_name)
                       VALUES (%s, %s, %s, %s) ON DUPLICATE KEY
                       UPDATE id = LAST_INSERT_ID(id), updated_at = CURRENT_TIMESTAMP
                       """, (target_user_id, year, month, month_name))
        monthly_record = {'id': cursor.lastrowid}

        # Pre-load existing payment methods for the target user
        cursor.execute("""
                       SELECT id, name FROM payment_methods
                       WHERE user_id = %s AND is_active = TRUE
                       """, (target_user_id,))
        existing_methods = {pm['name'].lower(): pm['id'] for pm in cursor.fetchall()}

        # Get current max display_order for appending at the end
        cursor.execute("""
                       SELECT COALESCE(MAX(display_order), 0) AS max_order
                       FROM transactions WHERE monthly_record_id = %s
                       """, (monthly_record['id'],))
        current_max_order = cursor.fetchone()['max_order']

        transaction_date = datetime(year, month, 1).date()

        imported_count = 0
        skipped_count = 0
        methods_created = []

        # ── Phase 1: resolve payment methods for ALL rows first ──
        # This avoids interleaving method-creation queries with
        # transaction inserts and reduces round-trips.
        resolved_pm_ids = []  # parallel list — one entry per row
        for row in rows:
            payment_method_id = None
            if row['method']:
                mapping_value = method_mapping.get(row['method'])

                if mapping_value == '__skip__':
                    payment_method_id = None
                elif mapping_value == '__create__':
                    method_key = row['method'].lower()
                    if method_key in existing_methods:
                        payment_method_id = existing_methods[method_key]
                    else:
                        cursor.execute("""
                                       INSERT INTO payment_methods (user_id, name, type, color)
                                       VALUES (%s, %s, %s, %s)
                                       """, (target_user_id, row['method'], 'other', '#6c757d'))
                        payment_method_id = cursor.lastrowid
                        existing_methods[method_key] = payment_method_id
                        methods_created.append(row['method'])
                elif mapping_value is not None:
                    try:
                        payment_method_id = int(mapping_value)
                    except (ValueError, TypeError):
                        payment_method_id = None
                else:
                    method_key = row['method'].lower()
                    if method_key in existing_methods:
                        payment_method_id = existing_methods[method_key]
                    else:
                        cursor.execute("""
                                       INSERT INTO payment_methods (user_id, name, type, color)
                                       VALUES (%s, %s, %s, %s)
                                       """, (target_user_id, row['method'], 'other', '#6c757d'))
                        payment_method_id = cursor.lastrowid
                        existing_methods[method_key] = payment_method_id
                        methods_created.append(row['method'])
            resolved_pm_ids.append(payment_method_id)

        # ── Phase 2: batch-insert all transactions in one query ──
        txn_values = []
        txn_params = []
        for idx, row in enumerate(rows):
            current_max_order += 1
            txn_values.append("(%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)")
            txn_params.extend([
                monthly_record['id'],
                row['description'],
                None,
                row['debit'],
                row['credit'],
                transaction_date,
                row['note'] if row['note'] else None,
                resolved_pm_ids[idx],
                current_max_order,
            ])

        if txn_values:
            cursor.execute(
                "INSERT INTO transactions "
                "(monthly_record_id, description, category_id, debit, credit, "
                "transaction_date, notes, payment_method_id, display_order, "
                "is_done, is_paid, marked_done_at, paid_at) VALUES "
                + ", ".join(txn_values),
                txn_params,
            )
            first_txn_id = cursor.lastrowid
            imported_count = len(txn_values)

            # ── Phase 3: batch-insert audit logs in one query ──
            ip_address = request.remote_addr if request else None
            user_agent = request.headers.get('User-Agent') if request else None
            audit_note = f"Imported for user {target_user['username']}"

            audit_values = []
            audit_params = []
            for i in range(imported_count):
                audit_values.append("(%s, %s, %s, %s, %s, %s, %s)")
                audit_params.extend([
                    first_txn_id + i,
                    admin_id,
                    'CREATE',
                    'csv_import',
                    audit_note,
                    ip_address,
                    user_agent,
                ])

            try:
                cursor.execute(
                    "INSERT INTO transaction_audit_logs "
                    "(transaction_id, user_id, action, field_name, new_value, ip_address, user_agent) VALUES "
                    + ", ".join(audit_values),
                    audit_params,
                )
            except Exception as e:
                logger.error(f"Failed to create batch audit logs: {e}")

        connection.commit()

        # Audit log
        details = (f"Imported {imported_count} transactions from CSV "
                   f"for {month_name} {year} (user: {target_user['username']})")
        if methods_created:
            details += f". Created payment methods: {', '.join(methods_created)}"
        log_audit(admin_id, 'CSV_IMPORT', target_user_id=target_user_id, details=details)

        return jsonify({
            'message': f'Successfully imported {imported_count} transactions for {month_name} {year}',
            'imported': imported_count,
            'skipped': skipped_count,
            'methods_created': methods_created,
        }), 201

    except Error as e:
        connection.rollback()
        logger.error(f"CSV import DB error: {e}")
        return jsonify({'error': f'Database error: {str(e)}'}), 500
    finally:
        cursor.close()
        connection.close()


@app.route('/api/admin/users/<int:user_id>/monthly-records', methods=['GET'])
@admin_required
@limiter.limit(RATE_LIMIT_ADMIN)
def admin_get_user_monthly_records(user_id):
    """Return monthly records for a given user with transaction counts (admin only)."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("""
                       SELECT mr.id, mr.year, mr.month, mr.month_name,
                              COUNT(t.id) AS transaction_count,
                              COALESCE(SUM(t.debit), 0) AS total_debit,
                              COALESCE(SUM(t.credit), 0) AS total_credit
                       FROM monthly_records mr
                       LEFT JOIN transactions t ON mr.id = t.monthly_record_id
                       WHERE mr.user_id = %s
                       GROUP BY mr.id, mr.year, mr.month, mr.month_name
                       ORDER BY mr.year DESC, mr.month DESC
                       """, (user_id,))
        return jsonify(cursor.fetchall())
    except Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


@app.route('/api/admin/users/<int:user_id>/monthly-records/<int:record_id>', methods=['DELETE'])
@admin_required
@limiter.limit(RATE_LIMIT_ADMIN)
def admin_delete_monthly_record(user_id, record_id):
    """Delete a monthly record and all its transactions for a given user (admin only)."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = connection.cursor(dictionary=True)
    admin_id = session['user_id']

    try:
        # Verify the record belongs to the specified user
        cursor.execute("""
                       SELECT mr.id, mr.year, mr.month, mr.month_name, u.username
                       FROM monthly_records mr
                       JOIN users u ON mr.user_id = u.id
                       WHERE mr.id = %s AND mr.user_id = %s
                       """, (record_id, user_id))
        record = cursor.fetchone()
        if not record:
            return jsonify({'error': 'Monthly record not found for this user'}), 404

        # Count transactions that will be deleted
        cursor.execute("SELECT COUNT(*) AS cnt FROM transactions WHERE monthly_record_id = %s", (record_id,))
        txn_count = cursor.fetchone()['cnt']

        # Get all attachments from transactions in this monthly record before deletion
        cursor.execute("""
            SELECT attachments 
            FROM transactions 
            WHERE monthly_record_id = %s AND attachments IS NOT NULL
        """, (record_id,))
        transactions_with_attachments = cursor.fetchall()

        # Delete all attachments from Appwrite before deleting transactions
        if appwrite_file_service.is_available() and transactions_with_attachments:
            for txn in transactions_with_attachments:
                attachments_value = txn['attachments']
                # Split comma-separated GUIDs
                attachment_guids = [guid.strip() for guid in attachments_value.split(',') if guid.strip()]

                for attachment_guid in attachment_guids:
                    success, error = appwrite_file_service.delete_file(attachment_guid)
                    if success:
                        logger.info(f"Deleted attachment {attachment_guid} from Appwrite (monthly record cleanup)")
                    else:
                        logger.warning(f"Failed to delete attachment {attachment_guid}: {error}")

        # Delete the monthly record (CASCADE will remove transactions)
        cursor.execute("DELETE FROM monthly_records WHERE id = %s", (record_id,))
        connection.commit()

        details = (f"Deleted {record['month_name']} {record['year']} "
                   f"({txn_count} transactions) for user {record['username']}")
        log_audit(admin_id, 'DELETE_MONTHLY_RECORD', target_user_id=user_id, details=details)

        return jsonify({
            'message': f"Deleted {record['month_name']} {record['year']} ({txn_count} transactions)",
            'deleted_transactions': txn_count,
        }), 200

    except Error as e:
        connection.rollback()
        logger.error(f"Delete monthly record error: {e}")
        return jsonify({'error': f'Database error: {str(e)}'}), 500
    finally:
        cursor.close()
        connection.close()


@app.route('/api/dashboard-stats')
@login_required
@limiter.limit(RATE_LIMIT_API)
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

# ==================================================
# TRANSACTION ROUTES - Registered from services/transaction_service.py
# ==================================================
# All transaction routes are now handled by the transaction_service
# This reduces the size of app.py and improves code organization
# Routes include: /api/transactions, /api/transactions/filter,
# /api/transactions/<id>, /api/transactions/<id>/audit-logs,
# /api/transactions/<id>/move, /api/transactions/<id>/copy,
# /api/transactions/<id>/attachment, /api/transactions/<id>/attachment/view,
# /api/transactions/export, /api/transactions/reorder,
# /api/transactions/<id>/mark-done, /api/transactions/<id>/mark-undone,
# /api/transactions/<id>/mark-paid, /api/transactions/<id>/mark-unpaid,
# /api/payment-method-totals, /api/clone-month-transactions


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
    percentage_markup = data.get('percentage_markup', 0.00)

    if not name:
        return jsonify({'error': 'Category name cannot be empty'}), 400

    if category_type not in ['income', 'expense']:
        return jsonify({'error': 'Category type must be either "income" or "expense"'}), 400

    # Validate percentage_markup
    try:
        percentage_markup = float(percentage_markup)
        if percentage_markup < 0 or percentage_markup > 100:
            return jsonify({'error': 'Percentage markup must be between 0 and 100'}), 400
    except (ValueError, TypeError):
        percentage_markup = 0.00

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
                "INSERT INTO categories (name, type, percentage_markup) VALUES (%s, %s, %s)",
                (name, category_type, percentage_markup)
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
    percentage_markup = data.get('percentage_markup', 0.00)

    if not name:
        return jsonify({'error': 'Category name cannot be empty'}), 400

    if category_type not in ['income', 'expense']:
        return jsonify({'error': 'Category type must be either "income" or "expense"'}), 400

    # Validate percentage_markup
    try:
        percentage_markup = float(percentage_markup)
        if percentage_markup < 0 or percentage_markup > 100:
            return jsonify({'error': 'Percentage markup must be between 0 and 100'}), 400
    except (ValueError, TypeError):
        percentage_markup = 0.00

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
                "UPDATE categories SET name = %s, type = %s, percentage_markup = %s WHERE id = %s",
                (name, category_type, percentage_markup, category_id)
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


# ==================================================
# TAX CALCULATION ROUTES - Registered from services/tax_service.py
# ==================================================
# All tax calculation routes are now handled by the tax_service
# This reduces the size of app.py and improves code organization
# Routes include: POST /api/tax-calculations, GET /api/tax-calculations,
# GET /api/tax-calculations/<id>, DELETE /api/tax-calculations/<id>,
# PUT /api/tax-calculations/<id>/set-active


# ==================================================
# EXCHANGE RATE ROUTES - Registered from services/exchange_rate_routes.py
# ==================================================
# All exchange rate routes are now handled by the exchange_rate_routes service
# This reduces the size of app.py and improves code organization
# Routes include: /api/exchange-rate, /api/exchange-rate/month, /api/exchange-rate/import-csv,
# /api/exchange-rate/bulk-cache, /api/exchange-rate/hnb/current, /api/exchange-rate/pb/current,
# /api/exchange-rate/sampath/current, /api/exchange-rate/refresh-all, /api/exchange-rate/banks,
# /api/exchange-rate/bank/<bank_code>, /api/exchange-rate/pb, /api/exchange-rate/trends/all,
# /api/exchange-rate/ai-insights, /api/exchange-rate/intraday-logs


# ==================================================
# TOKEN GENERATION ENDPOINT
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
    app.run(debug=False, host='0.0.0.0', port=5003)
