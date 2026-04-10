"""
User Service - Handles user authentication, profile, and preference management.

This service manages:
- User registration and login
- Password management
- User preferences
- Token-based authentication (JWT)
"""

import logging
from datetime import datetime, timedelta

from flask import request, jsonify, redirect, url_for, session, flash, render_template
from werkzeug.security import generate_password_hash, check_password_hash

from db import get_db_connection
from mysql.connector import Error

logger = logging.getLogger(__name__)


def register_user_routes(app, limiter, RATE_LIMIT_LOGIN, RATE_LIMIT_REGISTER, RATE_LIMIT_CHANGE_PASSWORD,
                         RATE_LIMIT_API, token_required):
    """Register all user-related routes with the Flask app.

    Args:
        app: Flask application instance
        limiter: Flask-Limiter instance for rate limiting
        RATE_LIMIT_LOGIN: Rate limit for login endpoint
        RATE_LIMIT_REGISTER: Rate limit for register endpoint
        RATE_LIMIT_CHANGE_PASSWORD: Rate limit for password change endpoint
        RATE_LIMIT_API: Rate limit for API endpoints
        token_required: Decorator for token authentication
    """

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
    @limiter.limit(RATE_LIMIT_CHANGE_PASSWORD)
    def change_password():
        """Change user password."""
        # Require login - check session
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401

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
    @limiter.limit(RATE_LIMIT_API)
    def get_user_preferences():
        """Get current user's preferences."""
        # Require login - check session
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401

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
    @limiter.limit(RATE_LIMIT_API)
    def update_user_preferences():
        """Update current user's preferences."""
        # Require login - check session
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401

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
            # Get token from Authorization header
            auth_header = request.headers.get('Authorization')
            if not auth_header or ' ' not in auth_header:
                return jsonify({'error': 'Token is required'}), 401

            token = auth_header.split(' ')[1]

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

    logger.info("User service routes registered successfully")
