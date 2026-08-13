"""
MFA Service - Handles Multi-Factor Authentication (2FA).

This service manages:
- MFA setup (TOTP) with QR code generation
- MFA verification during login
- Backup codes generation and verification
- MFA disable/enable management
"""

import io
import json
import logging
import secrets
from base64 import b64encode

import pyotp
import qrcode
from flask import request, jsonify, session, render_template, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from mysql.connector import Error

from db import get_db_connection

logger = logging.getLogger(__name__)


def generate_backup_codes(count=10):
    """Generate backup codes for MFA recovery.

    Args:
        count: Number of backup codes to generate (default: 10)

    Returns:
        List of backup codes (8-digit strings)
    """
    codes = []
    for _ in range(count):
        # Generate 8-digit code
        code = f"{secrets.randbelow(100000000):08d}"
        codes.append(code)
    return codes


def register_mfa_routes(app, limiter, RATE_LIMIT_API):
    """Register all MFA-related routes with the Flask app.

    Args:
        app: Flask application instance
        limiter: Flask-Limiter instance for rate limiting
        RATE_LIMIT_API: Rate limit for API endpoints
    """

    @app.route('/mfa/setup', methods=['GET'])
    def mfa_setup_page():
        """Display MFA setup page."""
        if 'user_id' not in session:
            flash('Please login first.', 'warning')
            return redirect(url_for('login'))

        return render_template('mfa_setup.html')

    @app.route('/api/mfa/setup', methods=['POST'])
    @limiter.limit(RATE_LIMIT_API)
    def mfa_setup():
        """Initialize MFA setup - generate secret and QR code.

        Returns:
            JSON with QR code (base64 image) and secret for manual entry
        """
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401

        user_id = session['user_id']
        username = session.get('username', '')

        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = connection.cursor(dictionary=True)

        try:
            # Check if MFA is already enabled
            cursor.execute(
                "SELECT mfa_enabled FROM users WHERE id = %s",
                (user_id,)
            )
            user = cursor.fetchone()

            if not user:
                return jsonify({'error': 'User not found'}), 404

            if user['mfa_enabled']:
                return jsonify({'error': 'MFA is already enabled'}), 400

            # Generate new TOTP secret
            secret = pyotp.random_base32()

            # Create provisioning URI for QR code
            totp = pyotp.TOTP(secret)
            app_name = "CW Budget Manager"
            provisioning_uri = totp.provisioning_uri(
                name=username,
                issuer_name=app_name
            )

            # Generate QR code
            qr = qrcode.QRCode(version=1, box_size=10, border=4)
            qr.add_data(provisioning_uri)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")

            # Convert to base64 for embedding in HTML
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            buffer.seek(0)
            img_base64 = b64encode(buffer.getvalue()).decode('utf-8')

            # Store secret temporarily in session (not yet in DB)
            session['mfa_secret_pending'] = secret

            logger.info(f"MFA setup initiated for user {username} (ID: {user_id})")

            return jsonify({
                'qr_code': f'data:image/png;base64,{img_base64}',
                'secret': secret,
                'message': 'Scan the QR code with your authenticator app'
            }), 200

        except Error as e:
            logger.error(f"Database error during MFA setup: {str(e)}")
            return jsonify({'error': 'Database error occurred'}), 500
        finally:
            cursor.close()
            connection.close()

    @app.route('/api/mfa/verify-setup', methods=['POST'])
    @limiter.limit(RATE_LIMIT_API)
    def mfa_verify_setup():
        """Verify MFA setup by validating the TOTP code and enable MFA.

        Request JSON:
            code: 6-digit TOTP code from authenticator app

        Returns:
            JSON with backup codes if successful
        """
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401

        user_id = session['user_id']
        secret = session.get('mfa_secret_pending')

        if not secret:
            return jsonify({'error': 'MFA setup not initiated. Please start setup first.'}), 400

        data = request.get_json()
        code = data.get('code', '').strip()

        if not code or len(code) != 6:
            return jsonify({'error': 'Invalid code format. Please enter 6-digit code.'}), 400

        # Verify the TOTP code
        totp = pyotp.TOTP(secret)
        if not totp.verify(code, valid_window=1):
            return jsonify({'error': 'Invalid verification code. Please try again.'}), 401

        # Generate backup codes
        backup_codes = generate_backup_codes(10)
        # Hash backup codes before storing
        hashed_codes = [generate_password_hash(code) for code in backup_codes]
        backup_codes_json = json.dumps(hashed_codes)

        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = connection.cursor()

        try:
            # Enable MFA and store secret + backup codes
            cursor.execute(
                """UPDATE users 
                   SET mfa_enabled = TRUE, 
                       mfa_secret = %s, 
                       mfa_backup_codes = %s,
                       mfa_enabled_at = CURRENT_TIMESTAMP
                   WHERE id = %s""",
                (secret, backup_codes_json, user_id)
            )
            connection.commit()

            # Clear pending secret from session
            session.pop('mfa_secret_pending', None)

            logger.info(f"MFA successfully enabled for user ID: {user_id}")

            return jsonify({
                'message': 'MFA enabled successfully',
                'backup_codes': backup_codes,
                'warning': 'Save these backup codes in a safe place. Each can only be used once.'
            }), 200

        except Error as e:
            logger.error(f"Database error enabling MFA: {str(e)}")
            return jsonify({'error': 'Failed to enable MFA'}), 500
        finally:
            cursor.close()
            connection.close()

    @app.route('/mfa/verify', methods=['GET', 'POST'])
    @limiter.limit(RATE_LIMIT_API)
    def mfa_verify():
        """MFA verification page and handler during login."""
        if request.method == 'GET':
            # Check if user is in MFA verification state
            if 'mfa_user_id' not in session:
                flash('Invalid session. Please login again.', 'warning')
                return redirect(url_for('login'))

            return render_template('mfa_verify.html')

        # POST - verify MFA code
        if 'mfa_user_id' not in session:
            return jsonify({'error': 'Invalid session'}), 401

        user_id = session['mfa_user_id']
        data = request.get_json() if request.is_json else request.form
        code = data.get('code', '').strip()
        use_backup = data.get('use_backup', False)

        if not code:
            return jsonify({'error': 'Verification code is required'}), 400

        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = connection.cursor(dictionary=True)

        try:
            # Get user MFA details
            cursor.execute(
                """SELECT username, is_admin, mfa_secret, mfa_backup_codes 
                   FROM users WHERE id = %s AND mfa_enabled = TRUE""",
                (user_id,)
            )
            user = cursor.fetchone()

            if not user:
                return jsonify({'error': 'User not found or MFA not enabled'}), 404

            verified = False

            if use_backup:
                # Verify backup code
                if not user['mfa_backup_codes']:
                    return jsonify({'error': 'No backup codes available'}), 400

                backup_codes = json.loads(user['mfa_backup_codes'])

                # Check if provided code matches any backup code
                for idx, hashed_code in enumerate(backup_codes):
                    if check_password_hash(hashed_code, code):
                        verified = True
                        # Remove used backup code
                        backup_codes.pop(idx)
                        updated_codes = json.dumps(backup_codes)
                        cursor.execute(
                            "UPDATE users SET mfa_backup_codes = %s WHERE id = %s",
                            (updated_codes, user_id)
                        )
                        connection.commit()
                        logger.info(f"Backup code used for user ID: {user_id}")
                        break

                if not verified:
                    return jsonify({'error': 'Invalid backup code'}), 401
            else:
                # Verify TOTP code
                if len(code) != 6 or not code.isdigit():
                    return jsonify({'error': 'Invalid code format'}), 400

                totp = pyotp.TOTP(user['mfa_secret'])
                verified = totp.verify(code, valid_window=1)

                if not verified:
                    return jsonify({'error': 'Invalid verification code'}), 401

            # MFA verified - complete login
            session.pop('mfa_user_id', None)
            session.permanent = True
            session['user_id'] = user_id
            session['username'] = user['username']
            session['is_admin'] = user.get('is_admin', False)
            session.modified = True

            # Update last_login
            cursor.execute(
                "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s",
                (user_id,)
            )
            connection.commit()

            logger.info(f"MFA verification successful for user ID: {user_id}")

            return jsonify({'message': 'Login successful'}), 200

        except Error as e:
            logger.error(f"Database error during MFA verification: {str(e)}")
            return jsonify({'error': 'Verification failed'}), 500
        finally:
            cursor.close()
            connection.close()

    @app.route('/api/mfa/disable', methods=['POST'])
    @limiter.limit(RATE_LIMIT_API)
    def mfa_disable():
        """Disable MFA for the current user.

        Request JSON:
            password: User's password for confirmation

        Returns:
            Success message
        """
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401

        user_id = session['user_id']
        data = request.get_json()
        password = data.get('password')

        if not password:
            return jsonify({'error': 'Password is required'}), 400

        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = connection.cursor(dictionary=True)

        try:
            # Verify password
            cursor.execute(
                "SELECT password_hash, mfa_enabled FROM users WHERE id = %s",
                (user_id,)
            )
            user = cursor.fetchone()

            if not user:
                return jsonify({'error': 'User not found'}), 404

            if not user['mfa_enabled']:
                return jsonify({'error': 'MFA is not enabled'}), 400

            if not check_password_hash(user['password_hash'], password):
                return jsonify({'error': 'Invalid password'}), 401

            # Disable MFA
            cursor.execute(
                """UPDATE users 
                   SET mfa_enabled = FALSE, 
                       mfa_secret = NULL, 
                       mfa_backup_codes = NULL,
                       mfa_enabled_at = NULL
                   WHERE id = %s""",
                (user_id,)
            )
            connection.commit()

            logger.info(f"MFA disabled for user ID: {user_id}")

            return jsonify({'message': 'MFA has been disabled'}), 200

        except Error as e:
            logger.error(f"Database error disabling MFA: {str(e)}")
            return jsonify({'error': 'Failed to disable MFA'}), 500
        finally:
            cursor.close()
            connection.close()

    @app.route('/api/mfa/status', methods=['GET'])
    @limiter.limit(RATE_LIMIT_API)
    def mfa_status():
        """Get MFA status for the current user."""
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401

        user_id = session['user_id']
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = connection.cursor(dictionary=True)

        try:
            cursor.execute(
                "SELECT mfa_enabled, mfa_enabled_at FROM users WHERE id = %s",
                (user_id,)
            )
            user = cursor.fetchone()

            if not user:
                return jsonify({'error': 'User not found'}), 404

            return jsonify({
                'mfa_enabled': bool(user['mfa_enabled']),
                'mfa_enabled_at': user['mfa_enabled_at'].isoformat() if user['mfa_enabled_at'] else None
            }), 200

        except Error as e:
            logger.error(f"Database error getting MFA status: {str(e)}")
            return jsonify({'error': 'Failed to get MFA status'}), 500
        finally:
            cursor.close()
            connection.close()

    @app.route('/api/mfa/regenerate-backup-codes', methods=['POST'])
    @limiter.limit(RATE_LIMIT_API)
    def mfa_regenerate_backup_codes():
        """Regenerate backup codes for MFA.

        Request JSON:
            password: User's password for confirmation

        Returns:
            New backup codes
        """
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401

        user_id = session['user_id']
        data = request.get_json()
        password = data.get('password')

        if not password:
            return jsonify({'error': 'Password is required'}), 400

        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = connection.cursor(dictionary=True)

        try:
            # Verify password and MFA status
            cursor.execute(
                "SELECT password_hash, mfa_enabled FROM users WHERE id = %s",
                (user_id,)
            )
            user = cursor.fetchone()

            if not user:
                return jsonify({'error': 'User not found'}), 404

            if not user['mfa_enabled']:
                return jsonify({'error': 'MFA is not enabled'}), 400

            if not check_password_hash(user['password_hash'], password):
                return jsonify({'error': 'Invalid password'}), 401

            # Generate new backup codes
            backup_codes = generate_backup_codes(10)
            hashed_codes = [generate_password_hash(code) for code in backup_codes]
            backup_codes_json = json.dumps(hashed_codes)

            # Update backup codes
            cursor.execute(
                "UPDATE users SET mfa_backup_codes = %s WHERE id = %s",
                (backup_codes_json, user_id)
            )
            connection.commit()

            logger.info(f"Backup codes regenerated for user ID: {user_id}")

            return jsonify({
                'message': 'Backup codes regenerated successfully',
                'backup_codes': backup_codes,
                'warning': 'Save these backup codes in a safe place. Old codes are now invalid.'
            }), 200

        except Error as e:
            logger.error(f"Database error regenerating backup codes: {str(e)}")
            return jsonify({'error': 'Failed to regenerate backup codes'}), 500
        finally:
            cursor.close()
            connection.close()
