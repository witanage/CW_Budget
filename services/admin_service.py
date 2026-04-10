"""
Admin Service Module

Handles all admin-related routes including:
- User management (view, toggle active/admin status, delete)
- Audit logging
- Application settings management
- Database backups
- CSV imports
- Monthly record management
"""

import csv
import io
import json
import logging
import os
import re
import threading
import calendar
from datetime import datetime
from decimal import Decimal

from flask import request, jsonify, session, render_template
from mysql.connector import Error

from db import get_db_connection
from services.google_drive_file_service import get_google_drive_file_service
from services.backup_service import get_backup_service
from services.google_drive_backup_service import get_google_drive_backup_service

logger = logging.getLogger(__name__)

# Initialize Google Drive file service for bill storage
file_service = get_google_drive_file_service()


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


def register_admin_routes(app, admin_required, limiter, RATE_LIMIT_ADMIN):
    """Register all admin routes with the Flask app."""

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
                return jsonify({'error': 'Cannot deactivate your own account'}), 400

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
                return jsonify({'error': 'Cannot modify your own admin status'}), 400

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
                return jsonify({'error': 'Cannot delete your own account'}), 400

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

            # Delete all attachments from Google Drive before deleting user
            if file_service.is_available() and transactions_with_attachments:
                deleted_count = 0
                for txn in transactions_with_attachments:
                    if txn['attachments']:
                        try:
                            attachment_ids = json.loads(txn['attachments'])
                            for file_id in attachment_ids:
                                if file_service.delete_file(file_id):
                                    deleted_count += 1
                        except (json.JSONDecodeError, TypeError):
                            logger.warning(f"Invalid attachment format for user {user_id}")

                if deleted_count > 0:
                    logger.info(f"Deleted {deleted_count} attachments from Google Drive for user {user_id}")

            # Delete user (cascading will handle related records)
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            connection.commit()

            # Log the action
            log_audit(admin_id, 'Deleted user', None,
                      f"User '{user['username']}' ({user['email']}) permanently deleted")

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

            logger.info(
                f"Admin {admin_id} updated default_page for user {user_id} ({user['username']}) to {default_page}")

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
                    row['updated_at'] = row['updated_at'].isoformat() if hasattr(row['updated_at'],
                                                                                 'isoformat') else str(
                        row['updated_at'])
            return jsonify(settings), 200
        except Error as e:
            logger.error(f"Error fetching settings: {str(e)}")
            return jsonify({'error': str(e)}), 500
        finally:
            cursor.close()
            connection.close()

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
                return jsonify({'error': "bill_upload_mode must be 'sequential' or 'batch'"}), 400

        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = connection.cursor(dictionary=True)
        try:
            # Guard: only allow updating pre-existing keys
            cursor.execute("SELECT setting_key FROM app_settings WHERE setting_key = %s", (key,))
            if not cursor.fetchone():
                return jsonify({'error': f"Setting '{key}' does not exist"}), 404

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

    @app.route('/api/admin/trigger-backup', methods=['GET'])
    def trigger_db_backup():
        """Trigger a database backup that uploads to Google Drive.

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

        def _run_backup_and_upload():
            """Generate a MySQL database backup and upload it to Google Drive."""
            backup_service = get_backup_service()
            return backup_service.create_and_upload_backup()

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
                        logger.info("Async backup completed: %s", message)
                    else:
                        logger.error("Async backup failed: %s", message)
                except Exception as e:
                    logger.error("Async backup failed with exception: %s", e, exc_info=True)

            thread = threading.Thread(target=_async_backup_wrapper, daemon=True)
            thread.start()
            logger.info("Database backup triggered (background thread started)")

            return jsonify({
                'status': 'triggered',
                'message': 'Database backup started in background. It will be uploaded to Google Drive upon completion.',
            }), 202

    @app.route('/api/admin/cleanup-old-backups', methods=['GET'])
    def cleanup_old_backups():
        """Delete backup files older than 3 months from Google Drive.

        Uses the same authorization pattern as the backup endpoint.
        Can optionally specify the age threshold with ?months=N query parameter.
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
            logger.warning("Unauthorized cleanup trigger — Origin: %s, Referer: %s, UA: %s, Remote: %s",
                           origin, referer, user_agent, remote_addr)
            return jsonify({'error': 'Access denied',
                            'message': 'This endpoint is only accessible from authorized sources'}), 403

        # Get months parameter (default: 3)
        try:
            months = int(request.args.get('months', 3))
            if months < 1:
                months = 3
        except (ValueError, TypeError):
            months = 3

        logger.info("Starting cleanup of backups older than %d months", months)

        try:
            drive_service = get_google_drive_backup_service()

            success, message, deleted_count, deleted_files = drive_service.cleanup_old_backups(months)

            if success:
                return jsonify({
                    'status': 'completed',
                    'message': message,
                    'deleted_count': deleted_count,
                    'deleted_files': deleted_files
                }), 200
            else:
                return jsonify({
                    'status': 'failed',
                    'error': message
                }), 500
        except Exception as e:
            logger.error("Cleanup failed with exception: %s", e, exc_info=True)
            return jsonify({
                'status': 'failed',
                'error': str(e)
            }), 500

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
                    continue  # Skip rows without description

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
                return jsonify({'error': 'No valid transactions found in CSV'}), 400

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
                return jsonify({'error': f'User with ID {target_user_id} not found'}), 404

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
                    method_lower = row['method'].lower()

                    # Check if there's a mapping directive
                    if row['method'] in method_mapping:
                        directive = method_mapping[row['method']]
                        if directive == '__skip__':
                            payment_method_id = None
                        elif directive == '__create__':
                            # Create new method
                            if method_lower not in existing_methods:
                                cursor.execute("""
                                    INSERT INTO payment_methods (user_id, name, type, color, is_active)
                                    VALUES (%s, %s, 'card', '#6c757d', TRUE)
                                """, (target_user_id, row['method']))
                                new_pm_id = cursor.lastrowid
                                existing_methods[method_lower] = new_pm_id
                                methods_created.append(row['method'])
                                logger.info(
                                    f"Created payment method '{row['method']}' (ID: {new_pm_id}) for user {target_user_id}")
                            payment_method_id = existing_methods[method_lower]
                        elif isinstance(directive, int):
                            # Use specified payment method ID
                            payment_method_id = directive
                        else:
                            # Invalid directive, fall back to auto-match
                            payment_method_id = existing_methods.get(method_lower)
                            if not payment_method_id:
                                # Auto-create
                                cursor.execute("""
                                    INSERT INTO payment_methods (user_id, name, type, color, is_active)
                                    VALUES (%s, %s, 'card', '#6c757d', TRUE)
                                """, (target_user_id, row['method']))
                                new_pm_id = cursor.lastrowid
                                existing_methods[method_lower] = new_pm_id
                                methods_created.append(row['method'])
                                payment_method_id = new_pm_id
                    else:
                        # No mapping provided, auto-match or create
                        payment_method_id = existing_methods.get(method_lower)
                        if not payment_method_id:
                            # Auto-create
                            cursor.execute("""
                                INSERT INTO payment_methods (user_id, name, type, color, is_active)
                                VALUES (%s, %s, 'card', '#6c757d', TRUE)
                            """, (target_user_id, row['method']))
                            new_pm_id = cursor.lastrowid
                            existing_methods[method_lower] = new_pm_id
                            methods_created.append(row['method'])
                            logger.info(
                                f"Auto-created payment method '{row['method']}' (ID: {new_pm_id}) for user {target_user_id}")
                            payment_method_id = new_pm_id

                resolved_pm_ids.append(payment_method_id)

            # ── Phase 2: batch-insert all transactions in one query ──
            txn_values = []
            txn_params = []
            for idx, row in enumerate(rows):
                current_max_order += 1
                txn_values.append(
                    "(%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)")
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
                    audit_values.append("(%s, %s, %s, %s, %s, %s)")
                    audit_params.extend([
                        first_txn_id + i,
                        admin_id,
                        'CREATE',
                        audit_note,
                        ip_address,
                        user_agent,
                    ])

                try:
                    cursor.execute(
                        "INSERT INTO transaction_audit_logs "
                        "(transaction_id, user_id, action, notes, ip_address, user_agent) VALUES "
                        + ", ".join(audit_values),
                        audit_params,
                    )
                except Exception as e:
                    logger.error(f"Failed to insert audit logs for CSV import: {e}")

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
                return jsonify({'error': 'Monthly record not found or does not belong to this user'}), 404

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

            # Delete all attachments from Google Drive before deleting transactions
            if file_service.is_available() and transactions_with_attachments:
                for txn in transactions_with_attachments:
                    if txn['attachments']:
                        try:
                            attachment_ids = json.loads(txn['attachments'])
                            for file_id in attachment_ids:
                                file_service.delete_file(file_id)
                        except (json.JSONDecodeError, TypeError):
                            logger.warning(f"Invalid attachment format in monthly record {record_id}")

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

    logger.info("Admin routes registered successfully")
