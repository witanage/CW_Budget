import logging
import os
from datetime import datetime, timedelta
from decimal import Decimal

from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, send_from_directory
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from mysql.connector import Error

from services.exchange_rate_routes import register_exchange_rate_routes, get_best_rate_today
from services.tax_service import register_tax_routes
from services.transaction_service import register_transaction_routes, get_month_summary
from services.markup_rule_service import register_markup_rule_routes
from services.admin_service import register_admin_routes
from services.user_service import register_user_routes
from services.report_service import register_report_routes
from services.category_service import register_category_routes
from services.payment_method_service import register_payment_method_routes
from services.auth_service import login_required, admin_required, token_required, make_session_permanent
from services.user_tab_service import get_enabled_tabs
from services.dashboard_service import get_dashboard_stats, get_sidebar_summary
from services.settings_service import get_upload_mode, get_global_template_vars

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
from db import get_db_connection, DB_CONFIG, get_setting  # noqa: E402

if DB_CONFIG is None:
    logger.warning(
        "Database is NOT configured. The application will start but all "
        "database operations will fail. Copy .env.example to .env and fill "
        "in your database credentials, then restart the application.")


def log_audit(admin_user_id, action, target_user_id=None, details=None):
    """Helper function to log admin actions.

    This is kept in app.py for compatibility with existing token-related routes.
    Main admin audit logging is now handled by admin_service.py.
    """
    from services.admin_service import log_audit as admin_log_audit
    admin_log_audit(admin_user_id, action, target_user_id, details)


# Authentication decorators are now imported from services.auth_service
# - login_required: Requires user to be logged in
# - admin_required: Requires admin privileges
# - token_required: Requires valid API token in Authorization header


@app.context_processor
def inject_global_template_vars():
    """Make admin-tunable UI settings available to all templates.

    Currently exposes:
      - modal_opacity: float string ('0.10'-'1.00') used by base.html to set
        the --modal-bg-opacity CSS custom property consumed by modal styles.
    """
    return get_global_template_vars()


@app.before_request
def setup_session():
    """Ensure authenticated sessions always use a persistent cookie."""
    make_session_permanent()


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
    user_id = session.get('user_id')
    enabled_tabs = get_enabled_tabs(user_id, device_type='desktop')
    
    return render_template('dashboard.html', 
                          username=session.get('username'),
                          enabled_tabs=enabled_tabs)


# Lazy-loaded page fragment endpoints (return HTML partials for on-demand loading)
@app.route('/api/page/reports')
@login_required
def page_reports():
    """Return reports page HTML fragment."""
    return render_template('partials/dashboard_reports.html')


@app.route('/api/page/tax')
@login_required
def page_tax():
    """Return tax calculator page HTML fragment."""
    return render_template('partials/dashboard_tax.html')


@app.route('/api/page/rateTrends')
@login_required
def page_rate_trends():
    """Return rate trends page HTML fragment."""
    return render_template('partials/dashboard_rate_trends.html')


@app.route('/api/settings/upload-mode', methods=['GET'])
def get_upload_mode_endpoint():
    """Public endpoint to get bill upload mode (sequential vs batch).
    No authentication required - used by client-side to determine upload strategy."""
    mode = get_upload_mode()
    return jsonify({'upload_mode': mode}), 200


@app.route('/mobile')
@login_required
def mobile():
    """Mobile view."""
    user_id = session.get('user_id')
    enabled_tabs = get_enabled_tabs(user_id, device_type='mobile')
    
    return render_template('mobile.html', 
                          username=session.get('username'),
                          enabled_tabs=enabled_tabs)


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
    user_id = session['user_id']
    result = get_dashboard_stats(user_id)
    
    if 'error' in result:
        return jsonify(result), 500
    
    return jsonify(result)


@app.route('/api/sidebar-summary')
@login_required
@limiter.limit(RATE_LIMIT_API)
def sidebar_summary():
    """Get summary data for sidebar widgets."""
    try:
        user_id = session['user_id']
        current_year = datetime.now().year
        current_month = datetime.now().month
        
        result = get_sidebar_summary(user_id, current_year, current_month)
        return jsonify(result)
    
    except Exception as e:
        logger.error(f"Error in sidebar_summary: {str(e)}")
        return jsonify({'error': 'Failed to fetch sidebar summary'}), 500


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
