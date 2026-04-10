"""
Markup Rule Service
Handles all Flask routes for managing flexible markup rules
"""

import logging
from decimal import Decimal

from flask import request, jsonify, session
from db import get_db_connection

logger = logging.getLogger(__name__)


def get_markup_rules_handler():
    """Get all active markup rules for the current user."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = connection.cursor(dictionary=True)

    try:
        user_id = session.get('user_id')

        # Fetch all active markup rules with category and payment method names
        query = """
            SELECT 
                mr.id,
                mr.rule_name,
                mr.category_id,
                c.name as category_name,
                mr.payment_method_id,
                pm.name as payment_method_name,
                mr.percentage_markup,
                mr.priority,
                mr.is_active,
                mr.created_at,
                mr.updated_at
            FROM markup_rules mr
            LEFT JOIN categories c ON mr.category_id = c.id
            LEFT JOIN payment_methods pm ON mr.payment_method_id = pm.id
            WHERE mr.user_id = %s
            ORDER BY 
                mr.priority DESC,
                mr.created_at DESC
        """

        cursor.execute(query, (user_id,))
        rules = cursor.fetchall()

        # Format the response
        for rule in rules:
            rule['rule_type'] = 'combination' if rule['category_id'] and rule['payment_method_id'] else \
                'payment_method' if rule['payment_method_id'] else \
                    'category'

        return jsonify(rules), 200

    except Exception as e:
        logger.error(f"Error fetching markup rules: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


def create_markup_rule_handler():
    """Create a new markup rule."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = connection.cursor(dictionary=True)

    try:
        data = request.get_json()
        user_id = session.get('user_id')

        # Validate required fields
        if not data.get('rule_name'):
            return jsonify({'error': 'Rule name is required'}), 400

        if not data.get('percentage_markup'):
            return jsonify({'error': 'Percentage markup is required'}), 400

        # Validate that at least one of category or payment method is provided
        category_id = data.get('category_id')
        payment_method_id = data.get('payment_method_id')

        if not category_id and not payment_method_id:
            return jsonify({'error': 'At least one of category or payment method must be specified'}), 400

        # Validate percentage markup
        try:
            percentage_markup = Decimal(str(data['percentage_markup']))
            if percentage_markup < 0:
                return jsonify({'error': 'Percentage markup must be non-negative'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid percentage markup value'}), 400

        # Get priority (default to 0)
        priority = data.get('priority', 0)

        # Insert the new rule
        query = """
            INSERT INTO markup_rules 
            (user_id, rule_name, category_id, payment_method_id, percentage_markup, priority, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE)
        """

        cursor.execute(query, (
            user_id,
            data['rule_name'],
            category_id,
            payment_method_id,
            percentage_markup,
            priority
        ))

        rule_id = cursor.lastrowid
        connection.commit()

        logger.info(f"Created markup rule {rule_id} for user {user_id}: {data['rule_name']}")

        return jsonify({
            'message': 'Markup rule created successfully',
            'id': rule_id
        }), 201

    except Exception as e:
        connection.rollback()
        logger.error(f"Error creating markup rule: {str(e)}")

        # Check for duplicate rule error
        if 'Duplicate entry' in str(e) or 'unique_rule' in str(e):
            return jsonify({'error': 'A rule with this category and payment method combination already exists'}), 409

        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


def update_markup_rule_handler(rule_id):
    """Update an existing markup rule."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = connection.cursor(dictionary=True)

    try:
        data = request.get_json()
        user_id = session.get('user_id')

        # Verify the rule exists and belongs to the user
        cursor.execute(
            "SELECT id FROM markup_rules WHERE id = %s AND user_id = %s",
            (rule_id, user_id)
        )

        if not cursor.fetchone():
            return jsonify({'error': 'Markup rule not found'}), 404

        # Build update query dynamically based on provided fields
        update_fields = []
        params = []

        if 'rule_name' in data:
            update_fields.append("rule_name = %s")
            params.append(data['rule_name'])

        if 'category_id' in data:
            update_fields.append("category_id = %s")
            params.append(data['category_id'])

        if 'payment_method_id' in data:
            update_fields.append("payment_method_id = %s")
            params.append(data['payment_method_id'])

        if 'percentage_markup' in data:
            try:
                percentage_markup = Decimal(str(data['percentage_markup']))
                if percentage_markup < 0:
                    return jsonify({'error': 'Percentage markup must be non-negative'}), 400
                update_fields.append("percentage_markup = %s")
                params.append(percentage_markup)
            except (ValueError, TypeError):
                return jsonify({'error': 'Invalid percentage markup value'}), 400

        if 'priority' in data:
            update_fields.append("priority = %s")
            params.append(data['priority'])

        if 'is_active' in data:
            update_fields.append("is_active = %s")
            params.append(bool(data['is_active']))

        if not update_fields:
            return jsonify({'error': 'No fields to update'}), 400

        # Add rule_id and user_id to params
        params.extend([rule_id, user_id])

        # Execute update
        query = f"""
            UPDATE markup_rules 
            SET {', '.join(update_fields)}
            WHERE id = %s AND user_id = %s
        """

        cursor.execute(query, params)
        connection.commit()

        logger.info(f"Updated markup rule {rule_id} for user {user_id}")

        return jsonify({'message': 'Markup rule updated successfully'}), 200

    except Exception as e:
        connection.rollback()
        logger.error(f"Error updating markup rule: {str(e)}")

        # Check for duplicate rule error
        if 'Duplicate entry' in str(e) or 'unique_rule' in str(e):
            return jsonify({'error': 'A rule with this category and payment method combination already exists'}), 409

        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


def delete_markup_rule_handler(rule_id):
    """Delete a markup rule."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = connection.cursor()

    try:
        user_id = session.get('user_id')

        # Delete the rule (only if it belongs to the user)
        cursor.execute(
            "DELETE FROM markup_rules WHERE id = %s AND user_id = %s",
            (rule_id, user_id)
        )

        if cursor.rowcount == 0:
            return jsonify({'error': 'Markup rule not found'}), 404

        connection.commit()

        logger.info(f"Deleted markup rule {rule_id} for user {user_id}")

        return jsonify({'message': 'Markup rule deleted successfully'}), 200

    except Exception as e:
        connection.rollback()
        logger.error(f"Error deleting markup rule: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


def get_applicable_markup_handler():
    """
    Get the applicable markup percentage for a given category and payment method.
    This is useful for previewing what markup will be applied before creating a transaction.
    """
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = connection.cursor(dictionary=True)

    try:
        user_id = session.get('user_id')
        category_id = request.args.get('category_id', type=int)
        payment_method_id = request.args.get('payment_method_id', type=int)

        # Use the same logic as apply_percentage_markup to find the best matching rule
        query = """
            SELECT 
                id, rule_name, category_id, payment_method_id, 
                percentage_markup, priority
            FROM markup_rules
            WHERE user_id = %s 
                AND is_active = TRUE
                AND percentage_markup > 0
                AND (
                    -- Exact match: both category and payment method
                    (category_id = %s AND payment_method_id = %s)
                    OR
                    -- Payment method only match
                    (category_id IS NULL AND payment_method_id = %s)
                    OR
                    -- Category only match
                    (category_id = %s AND payment_method_id IS NULL)
                )
            ORDER BY 
                -- Priority 1: Both category and payment method (most specific)
                CASE WHEN category_id IS NOT NULL AND payment_method_id IS NOT NULL THEN 1 ELSE 2 END,
                -- Priority 2: Sort by rule priority field
                priority DESC,
                -- Priority 3: Newer rules first
                created_at DESC
            LIMIT 1
        """

        cursor.execute(query, (
            user_id,
            category_id, payment_method_id,  # Exact match
            payment_method_id,  # Payment method only
            category_id  # Category only
        ))

        result = cursor.fetchone()

        if result:
            rule_type = "combination"
            if result['category_id'] and result['payment_method_id']:
                rule_type = "category + payment method"
            elif result['payment_method_id']:
                rule_type = "payment method only"
            elif result['category_id']:
                rule_type = "category only"

            return jsonify({
                'applicable': True,
                'rule_id': result['id'],
                'rule_name': result['rule_name'],
                'percentage_markup': float(result['percentage_markup']),
                'rule_type': rule_type
            }), 200
        else:
            return jsonify({
                'applicable': False,
                'percentage_markup': 0
            }), 200

    except Exception as e:
        logger.error(f"Error checking applicable markup: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


def register_markup_rule_routes(app, admin_required, limiter, rate_limit_admin):
    """Register all markup rule routes with the Flask app (admin-only)."""

    @app.route('/api/admin/markup-rules', methods=['GET'])
    @admin_required
    @limiter.limit(rate_limit_admin)
    def get_markup_rules():
        """Get all markup rules for the current user (admin-only)."""
        return get_markup_rules_handler()

    @app.route('/api/admin/markup-rules', methods=['POST'])
    @admin_required
    @limiter.limit(rate_limit_admin)
    def create_markup_rule():
        """Create a new markup rule (admin-only)."""
        return create_markup_rule_handler()

    @app.route('/api/admin/markup-rules/<int:rule_id>', methods=['PUT'])
    @admin_required
    @limiter.limit(rate_limit_admin)
    def update_markup_rule(rule_id):
        """Update an existing markup rule (admin-only)."""
        return update_markup_rule_handler(rule_id)

    @app.route('/api/admin/markup-rules/<int:rule_id>', methods=['DELETE'])
    @admin_required
    @limiter.limit(rate_limit_admin)
    def delete_markup_rule(rule_id):
        """Delete a markup rule (admin-only)."""
        return delete_markup_rule_handler(rule_id)

    @app.route('/api/admin/markup-rules/applicable', methods=['GET'])
    @admin_required
    @limiter.limit(rate_limit_admin)
    def get_applicable_markup():
        """Get the applicable markup for a category/payment method combination (admin-only)."""
        return get_applicable_markup_handler()

