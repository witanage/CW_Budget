"""
Payment Method Service - Handles payment method management.

This service manages:
- Retrieving payment methods assigned to the current user
- Admin CRUD operations for global payment methods
- Assigning/unassigning payment methods to/from users
"""

import logging

from flask import request, jsonify, session
from mysql.connector import Error

from db import get_db_connection

logger = logging.getLogger(__name__)


def register_payment_method_routes(app, login_required, admin_required, limiter, rate_limit_admin):
    """Register all payment method-related routes with the Flask app.

    Args:
        app: Flask application instance
        login_required: Decorator for authentication
        admin_required: Decorator for admin authentication
        limiter: Flask-Limiter instance
        rate_limit_admin: Rate limit string for admin endpoints
    """

    # ── User Endpoints ─────────────────────────────────────────

    @app.route('/api/payment-methods')
    @login_required
    def get_payment_methods():
        """Get payment methods assigned to the current user."""
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("""
                           SELECT pm.id, pm.name, pm.type, pm.color
                           FROM payment_methods pm
                                    INNER JOIN user_payment_methods upm ON pm.id = upm.payment_method_id
                           WHERE upm.user_id = %s
                             AND pm.is_active = TRUE
                           ORDER BY pm.type, pm.name
                           """, (session['user_id'],))
            return jsonify(cursor.fetchall())
        except Error as e:
            return jsonify({'error': str(e)}), 500
        finally:
            cursor.close()
            connection.close()

    # ── Admin Endpoints ────────────────────────────────────────

    @app.route('/api/admin/payment-methods', methods=['GET'])
    @admin_required
    @limiter.limit(rate_limit_admin)
    def admin_get_payment_methods():
        """Get all payment methods with assigned user counts (admin)."""
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("""
                           SELECT pm.id,
                                  pm.name,
                                  pm.type,
                                  pm.color,
                                  pm.is_active,
                                  pm.created_at,
                                  COUNT(upm.user_id) as assigned_user_count
                           FROM payment_methods pm
                                    LEFT JOIN user_payment_methods upm ON pm.id = upm.payment_method_id
                           WHERE pm.is_active = TRUE
                           GROUP BY pm.id, pm.name, pm.type, pm.color, pm.is_active, pm.created_at
                           ORDER BY pm.type, pm.name
                           """)
            return jsonify(cursor.fetchall())
        except Error as e:
            return jsonify({'error': str(e)}), 500
        finally:
            cursor.close()
            connection.close()

    @app.route('/api/admin/payment-methods', methods=['POST'])
    @admin_required
    @limiter.limit(rate_limit_admin)
    def admin_create_payment_method():
        """Create a new global payment method (admin)."""
        data = request.get_json()

        if not data or not data.get('name'):
            return jsonify({'error': 'Payment method name is required'}), 400

        name = data['name'].strip()
        if not name:
            return jsonify({'error': 'Payment method name cannot be empty'}), 400

        pm_type = data.get('type', 'credit_card').strip()
        color = data.get('color', '#007bff').strip()

        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = connection.cursor(dictionary=True)
        try:
            # Check for duplicate name among active methods
            cursor.execute(
                "SELECT id FROM payment_methods WHERE name = %s AND is_active = TRUE",
                (name,)
            )
            if cursor.fetchone():
                return jsonify({'error': 'A payment method with this name already exists'}), 409

            cursor.execute(
                "INSERT INTO payment_methods (name, type, color) VALUES (%s, %s, %s)",
                (name, pm_type, color)
            )
            connection.commit()

            pm_id = cursor.lastrowid
            cursor.execute("SELECT * FROM payment_methods WHERE id = %s", (pm_id,))
            new_pm = cursor.fetchone()

            logger.info(f"Admin {session['user_id']} created payment method '{name}' (ID: {pm_id})")
            return jsonify(new_pm), 201
        except Error as e:
            connection.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cursor.close()
            connection.close()

    @app.route('/api/admin/payment-methods/<int:pm_id>', methods=['PUT'])
    @admin_required
    @limiter.limit(rate_limit_admin)
    def admin_update_payment_method(pm_id):
        """Update a payment method (admin)."""
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("SELECT * FROM payment_methods WHERE id = %s AND is_active = TRUE", (pm_id,))
            if not cursor.fetchone():
                return jsonify({'error': 'Payment method not found'}), 404

            update_fields = []
            params = []

            if 'name' in data:
                name = data['name'].strip()
                if not name:
                    return jsonify({'error': 'Payment method name cannot be empty'}), 400
                cursor.execute(
                    "SELECT id FROM payment_methods WHERE name = %s AND is_active = TRUE AND id != %s",
                    (name, pm_id)
                )
                if cursor.fetchone():
                    return jsonify({'error': 'Another payment method with this name already exists'}), 409
                update_fields.append("name = %s")
                params.append(name)

            if 'type' in data:
                update_fields.append("type = %s")
                params.append(data['type'].strip())

            if 'color' in data:
                update_fields.append("color = %s")
                params.append(data['color'].strip())

            if not update_fields:
                return jsonify({'error': 'No fields to update'}), 400

            params.append(pm_id)
            cursor.execute(
                f"UPDATE payment_methods SET {', '.join(update_fields)} WHERE id = %s",
                params
            )
            connection.commit()

            cursor.execute("SELECT * FROM payment_methods WHERE id = %s", (pm_id,))
            updated = cursor.fetchone()

            logger.info(f"Admin {session['user_id']} updated payment method {pm_id}")
            return jsonify(updated)
        except Error as e:
            connection.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cursor.close()
            connection.close()

    @app.route('/api/admin/payment-methods/<int:pm_id>', methods=['DELETE'])
    @admin_required
    @limiter.limit(rate_limit_admin)
    def admin_delete_payment_method(pm_id):
        """Soft-delete a payment method (admin). Fails if in use by transactions."""
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("SELECT * FROM payment_methods WHERE id = %s AND is_active = TRUE", (pm_id,))
            pm = cursor.fetchone()
            if not pm:
                return jsonify({'error': 'Payment method not found'}), 404

            # Check if in use by transactions
            cursor.execute(
                "SELECT COUNT(*) as count FROM transactions WHERE payment_method_id = %s",
                (pm_id,)
            )
            result = cursor.fetchone()
            if result and result['count'] > 0:
                return jsonify({
                    'error': f'Cannot delete payment method. It is being used by {result["count"]} transaction(s).',
                    'transaction_count': result['count']
                }), 409

            # Soft delete and remove all assignments
            cursor.execute("UPDATE payment_methods SET is_active = FALSE WHERE id = %s", (pm_id,))
            cursor.execute("DELETE FROM user_payment_methods WHERE payment_method_id = %s", (pm_id,))
            connection.commit()

            logger.info(f"Admin {session['user_id']} deleted payment method '{pm['name']}' (ID: {pm_id})")
            return jsonify({'message': 'Payment method deleted successfully'})
        except Error as e:
            connection.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cursor.close()
            connection.close()

    # ── Assignment Endpoints ───────────────────────────────────

    @app.route('/api/admin/payment-methods/<int:pm_id>/assigned-users', methods=['GET'])
    @admin_required
    @limiter.limit(rate_limit_admin)
    def admin_get_assigned_users(pm_id):
        """Get users assigned to a payment method."""
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("""
                           SELECT u.id, u.username, u.email, upm.created_at as assigned_at
                           FROM user_payment_methods upm
                                    INNER JOIN users u ON upm.user_id = u.id
                           WHERE upm.payment_method_id = %s
                           ORDER BY u.username
                           """, (pm_id,))
            return jsonify(cursor.fetchall())
        except Error as e:
            return jsonify({'error': str(e)}), 500
        finally:
            cursor.close()
            connection.close()

    @app.route('/api/admin/payment-methods/<int:pm_id>/assign-user', methods=['POST'])
    @admin_required
    @limiter.limit(rate_limit_admin)
    def admin_assign_payment_method(pm_id):
        """Assign a payment method to a user."""
        data = request.get_json()
        if not data or not data.get('user_id'):
            return jsonify({'error': 'user_id is required'}), 400

        user_id = data['user_id']

        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("SELECT id FROM payment_methods WHERE id = %s AND is_active = TRUE", (pm_id,))
            if not cursor.fetchone():
                return jsonify({'error': 'Payment method not found'}), 404

            cursor.execute("SELECT id, username FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            if not user:
                return jsonify({'error': 'User not found'}), 404

            cursor.execute(
                "SELECT id FROM user_payment_methods WHERE user_id = %s AND payment_method_id = %s",
                (user_id, pm_id)
            )
            if cursor.fetchone():
                return jsonify({'error': 'Payment method already assigned to this user'}), 409

            cursor.execute(
                "INSERT INTO user_payment_methods (user_id, payment_method_id) VALUES (%s, %s)",
                (user_id, pm_id)
            )
            connection.commit()

            logger.info(f"Admin {session['user_id']} assigned payment method {pm_id} to user {user_id}")
            return jsonify({'message': f'Payment method assigned to {user["username"]}'}), 201
        except Error as e:
            connection.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cursor.close()
            connection.close()

    @app.route('/api/admin/payment-methods/<int:pm_id>/unassign-user/<int:user_id>', methods=['DELETE'])
    @admin_required
    @limiter.limit(rate_limit_admin)
    def admin_unassign_payment_method(pm_id, user_id):
        """Unassign a payment method from a user."""
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT id FROM user_payment_methods WHERE user_id = %s AND payment_method_id = %s",
                (user_id, pm_id)
            )
            if not cursor.fetchone():
                return jsonify({'error': 'Assignment not found'}), 404

            cursor.execute(
                "DELETE FROM user_payment_methods WHERE user_id = %s AND payment_method_id = %s",
                (user_id, pm_id)
            )
            connection.commit()

            logger.info(f"Admin {session['user_id']} unassigned payment method {pm_id} from user {user_id}")
            return jsonify({'message': 'Payment method unassigned successfully'})
        except Error as e:
            connection.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cursor.close()
            connection.close()

    @app.route('/api/admin/payment-methods/bulk-assign', methods=['POST'])
    @admin_required
    @limiter.limit(rate_limit_admin)
    def admin_bulk_assign_payment_methods():
        """Bulk assign payment methods to a user. Replaces all current assignments."""
        data = request.get_json()
        if not data or 'user_id' not in data or 'payment_method_ids' not in data:
            return jsonify({'error': 'user_id and payment_method_ids are required'}), 400

        user_id = data['user_id']
        pm_ids = data['payment_method_ids']

        if not isinstance(pm_ids, list):
            return jsonify({'error': 'payment_method_ids must be a list'}), 400

        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
            if not cursor.fetchone():
                return jsonify({'error': 'User not found'}), 404

            # Replace all assignments for this user
            cursor.execute("DELETE FROM user_payment_methods WHERE user_id = %s", (user_id,))

            if pm_ids:
                values = [(user_id, pm_id) for pm_id in pm_ids]
                cursor.executemany(
                    "INSERT INTO user_payment_methods (user_id, payment_method_id) VALUES (%s, %s)",
                    values
                )
            connection.commit()

            logger.info(f"Admin {session['user_id']} bulk-assigned {len(pm_ids)} payment methods to user {user_id}")
            return jsonify({
                'message': f'{len(pm_ids)} payment method(s) assigned successfully',
                'assigned_count': len(pm_ids)
            })
        except Error as e:
            connection.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cursor.close()
            connection.close()

    logger.info("Payment method routes registered successfully")
