import logging
import os
from datetime import datetime, timedelta
from decimal import Decimal
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, send_from_directory
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from mysql.connector import Error

from services.exchange_rate_routes import register_exchange_rate_routes
from services.tax_service import register_tax_routes
from services.transaction_service import register_transaction_routes
from services.markup_rule_service import register_markup_rule_routes
from services.admin_service import register_admin_routes
from services.user_service import register_user_routes
from services.report_service import register_report_routes
from services.category_service import register_category_routes
from services.payment_method_service import register_payment_method_routes

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
# Favicon route to suppress browser 404 warnings
# ---------------------------------------------------------------------------
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')


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


def log_audit(admin_user_id, action, target_user_id=None, details=None):
    """Helper function to log admin actions.

    This is kept in app.py for compatibility with existing token-related routes.
    Main admin audit logging is now handled by admin_service.py.
    """
    from services.admin_service import log_audit as admin_log_audit
    admin_log_audit(admin_user_id, action, target_user_id, details)


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


@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard."""
    return render_template('dashboard.html', username=session.get('username'))


@app.route('/api/settings/upload-mode', methods=['GET'])
def get_upload_mode():
    """Public endpoint to get bill upload mode (sequential vs batch).
    No authentication required - used by client-side to determine upload strategy."""
    mode = get_setting('bill_upload_mode', 'sequential')
    logger.info(f"Upload mode requested: returning '{mode}'")
    return jsonify({'upload_mode': mode}), 200


@app.route('/mobile')
@login_required
def mobile():
    """Mobile view."""
    return render_template('mobile.html', username=session.get('username'))


register_user_routes(app, limiter, RATE_LIMIT_LOGIN, RATE_LIMIT_REGISTER, RATE_LIMIT_CHANGE_PASSWORD, RATE_LIMIT_API,
                     token_required)
register_admin_routes(app, admin_required, limiter, RATE_LIMIT_ADMIN)
register_exchange_rate_routes(app, login_required, admin_required, token_required, log_audit)
register_tax_routes(app, login_required)
register_transaction_routes(app, login_required, limiter, RATE_LIMIT_API, token_required)
register_markup_rule_routes(app, admin_required, limiter, RATE_LIMIT_ADMIN)
register_report_routes(app, login_required)
register_category_routes(app, login_required)
register_payment_method_routes(app, login_required, admin_required, limiter, RATE_LIMIT_ADMIN)


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


@app.route('/api/recalculate-balances', methods=['POST'])
@login_required
def recalculate_balances():
    """Deprecated: Balance calculation now happens on frontend."""
    return jsonify({
        'message': 'Balance calculation now happens on frontend',
        'transactions_updated': 0
    })


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
