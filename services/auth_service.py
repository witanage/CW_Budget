"""
Authentication Service

Provides authentication and authorization decorators for routes:
- login_required: Requires user to be logged in
- admin_required: Requires user to be logged in and have admin privileges
- token_required: Requires valid API token in Authorization header
- make_session_permanent: Flask before_request hook to make sessions persistent
"""

import logging
from functools import wraps

import jwt
from flask import session, flash, redirect, url_for, request, jsonify, current_app

from db import get_db_connection

logger = logging.getLogger(__name__)


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
            payload = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
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


def make_session_permanent():
    """Ensure authenticated sessions always use a persistent cookie.

    Without this, non-'Remember Me' sessions use browser-session cookies
    that are deleted when the tab or browser is closed. By always marking
    authenticated sessions as permanent, the cookie is sent with a Max-Age
    equal to PERMANENT_SESSION_LIFETIME (365 days) so the user stays
    logged in across tab/browser restarts.

    Use as Flask before_request hook:
        @app.before_request
        def setup_session():
            make_session_permanent()
    """
    if 'user_id' in session:
        session.permanent = True
