"""
Category Service - Handles category management.

This service manages:
- Retrieving all categories
- Creating new categories
- Updating existing categories
- Deleting categories (with validation)
"""

import logging

from flask import request, jsonify
from mysql.connector import Error

from db import get_db_connection

logger = logging.getLogger(__name__)


def register_category_routes(app, login_required):
    """Register all category-related routes with the Flask app.

    Args:
        app: Flask application instance
        login_required: Decorator for authentication
    """

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

    logger.info("Category routes registered successfully")
