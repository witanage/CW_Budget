"""
Tax Service
Handles all Flask routes and business logic for tax calculation functionality
"""

import json
import logging

from flask import request, jsonify, session
from mysql.connector import Error

from db import get_db_connection

logger = logging.getLogger(__name__)


# ==================================================
# TAX CALCULATION ROUTE HANDLERS
# ==================================================

def save_tax_calculation_handler():
    """Save income data only (tax calculations are computed on-the-fly)."""
    connection = None
    cursor = None
    try:
        data = request.get_json()
        user_id = session['user_id']

        # Extract income data (input fields only)
        calculation_name = data.get('calculation_name')
        assessment_year = data.get('assessment_year')
        tax_rate = data.get('tax_rate', 0)
        tax_free_threshold = data.get('tax_free_threshold', 0)
        start_month = int(data.get('start_month', 0))
        monthly_data = data.get('monthly_data', [])
        is_active = data.get('is_active', False)

        # Validate required fields
        if not all([calculation_name, assessment_year]):
            return jsonify({'error': 'Calculation name and assessment year are required'}), 400

        logger.info(f"Saving tax calculation: name='{calculation_name}', year={assessment_year}, active={is_active}")
        logger.info(f"Monthly data entries: {len(monthly_data)}")

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # If marking as active, deactivate other calculations for this year
        if is_active:
            cursor.execute("""
                           UPDATE tax_calculations
                           SET is_active = FALSE
                           WHERE user_id = %s
                             AND assessment_year = %s
                           """, (user_id, assessment_year))
            logger.info(f"Deactivated other calculations for year {assessment_year}")

        # Insert income data only (tax calculations computed on load)
        cursor.execute("""
                       INSERT INTO tax_calculations
                       (user_id, calculation_name, assessment_year,
                        tax_rate, tax_free_threshold, start_month, monthly_data, is_active)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                       """, (
            user_id, calculation_name, assessment_year,
            tax_rate, tax_free_threshold, start_month,
            json.dumps(monthly_data), is_active
        ))

        tax_calculation_id = cursor.lastrowid
        connection.commit()

        logger.info(f"Tax calculation saved successfully: ID={tax_calculation_id}")

        return jsonify({
            'message': 'Tax calculation saved successfully',
            'id': tax_calculation_id
        }), 201

    except Error as e:
        if connection:
            connection.rollback()
        logger.error(f"Error saving tax calculation: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


def get_tax_calculations_handler():
    """Get all tax calculations for the current user, optionally filtered by year."""
    connection = None
    cursor = None
    try:
        user_id = session['user_id']
        year = request.args.get('year')  # Optional year filter

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Build query based on whether year filter is provided
        if year:
            cursor.execute("""
                           SELECT id,
                                  calculation_name,
                                  assessment_year,
                                  tax_rate,
                                  tax_free_threshold,
                                  start_month,
                                  is_active,
                                  created_at,
                                  updated_at
                           FROM tax_calculations
                           WHERE user_id = %s
                             AND assessment_year = %s
                           ORDER BY is_active DESC, created_at DESC
                           """, (user_id, year))
        else:
            cursor.execute("""
                           SELECT id,
                                  calculation_name,
                                  assessment_year,
                                  tax_rate,
                                  tax_free_threshold,
                                  start_month,
                                  is_active,
                                  created_at,
                                  updated_at
                           FROM tax_calculations
                           WHERE user_id = %s
                           ORDER BY assessment_year DESC, is_active DESC, created_at DESC
                           """, (user_id,))

        calculations = cursor.fetchall()

        # Convert Decimal types to float for proper JSON serialization
        for calc in calculations:
            if calc.get('tax_rate') is not None:
                calc['tax_rate'] = float(calc['tax_rate'])
            if calc.get('tax_free_threshold') is not None:
                calc['tax_free_threshold'] = float(calc['tax_free_threshold'])

        logger.info(f"Returning {len(calculations)} tax calculation(s)")
        return jsonify(calculations), 200

    except Error as e:
        logger.error(f"Error fetching tax calculations: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


def get_tax_calculation_handler(calculation_id):
    """Get a specific tax calculation with all income data."""
    connection = None
    cursor = None
    try:
        user_id = session['user_id']

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Get main calculation with all income data
        cursor.execute("""
                       SELECT id,
                              calculation_name,
                              assessment_year,
                              tax_rate,
                              tax_free_threshold,
                              start_month,
                              monthly_data,
                              is_active,
                              created_at,
                              updated_at
                       FROM tax_calculations
                       WHERE id = %s
                         AND user_id = %s
                       """, (calculation_id, user_id))

        calculation = cursor.fetchone()

        if not calculation:
            return jsonify({'error': 'Tax calculation not found'}), 404

        # Convert Decimal types to float for proper JSON serialization
        if calculation.get('tax_rate') is not None:
            calculation['tax_rate'] = float(calculation['tax_rate'])
        if calculation.get('tax_free_threshold') is not None:
            calculation['tax_free_threshold'] = float(calculation['tax_free_threshold'])

        # Parse JSON monthly_data (contains all income details)
        if calculation.get('monthly_data'):
            if isinstance(calculation['monthly_data'], str):
                calculation['monthly_data'] = json.loads(calculation['monthly_data'])
            # else it's already parsed by MySQL JSON type

        logger.info(
            f"Loaded calculation ID={calculation['id']}, has {len(calculation.get('monthly_data', []))} monthly entries")
        return jsonify(calculation), 200

    except Error as e:
        logger.error(f"Error fetching tax calculation {calculation_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


def delete_tax_calculation_handler(calculation_id):
    """Delete a tax calculation."""
    connection = None
    cursor = None
    try:
        user_id = session['user_id']

        connection = get_db_connection()
        cursor = connection.cursor()

        # Verify ownership before deleting
        cursor.execute("""
                       SELECT id
                       FROM tax_calculations
                       WHERE id = %s
                         AND user_id = %s
                       """, (calculation_id, user_id))

        if not cursor.fetchone():
            return jsonify({'error': 'Tax calculation not found'}), 404

        # Delete the calculation
        cursor.execute("""
                       DELETE
                       FROM tax_calculations
                       WHERE id = %s
                         AND user_id = %s
                       """, (calculation_id, user_id))

        connection.commit()
        logger.info(f"Tax calculation ID={calculation_id} deleted successfully")

        return jsonify({'message': 'Tax calculation deleted successfully'}), 200

    except Error as e:
        if connection:
            connection.rollback()
        logger.error(f"Error deleting tax calculation {calculation_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


def set_active_tax_calculation_handler(calculation_id):
    """Set a tax calculation as active for its assessment year."""
    connection = None
    cursor = None
    try:
        user_id = session['user_id']

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Verify ownership and get assessment year
        cursor.execute("""
                       SELECT assessment_year
                       FROM tax_calculations
                       WHERE id = %s
                         AND user_id = %s
                       """, (calculation_id, user_id))

        calculation = cursor.fetchone()

        if not calculation:
            return jsonify({'error': 'Tax calculation not found'}), 404

        assessment_year = calculation['assessment_year']

        # Deactivate all calculations for this year
        cursor.execute("""
                       UPDATE tax_calculations
                       SET is_active = FALSE
                       WHERE user_id = %s
                         AND assessment_year = %s
                       """, (user_id, assessment_year))

        # Activate the specified calculation
        cursor.execute("""
                       UPDATE tax_calculations
                       SET is_active  = TRUE,
                           updated_at = CURRENT_TIMESTAMP
                       WHERE id = %s
                         AND user_id = %s
                       """, (calculation_id, user_id))

        connection.commit()
        logger.info(f"Tax calculation ID={calculation_id} set as active for year {assessment_year}")

        return jsonify({
            'message': 'Tax calculation set as active successfully',
            'id': calculation_id,
            'assessment_year': assessment_year
        }), 200

    except Error as e:
        if connection:
            connection.rollback()
        logger.error(f"Error setting tax calculation {calculation_id} as active: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


# ==================================================
# ROUTE REGISTRATION
# ==================================================

def register_tax_routes(app, login_required):
    """
    Register all tax calculation routes with the Flask app

    Args:
        app: Flask application instance
        login_required: Login required decorator
    """

    @app.route('/api/tax-calculations', methods=['POST'])
    @login_required
    def save_tax_calculation():
        return save_tax_calculation_handler()

    @app.route('/api/tax-calculations', methods=['GET'])
    @login_required
    def get_tax_calculations():
        return get_tax_calculations_handler()

    @app.route('/api/tax-calculations/<int:calculation_id>', methods=['GET'])
    @login_required
    def get_tax_calculation(calculation_id):
        return get_tax_calculation_handler(calculation_id)

    @app.route('/api/tax-calculations/<int:calculation_id>', methods=['DELETE'])
    @login_required
    def delete_tax_calculation(calculation_id):
        return delete_tax_calculation_handler(calculation_id)

    @app.route('/api/tax-calculations/<int:calculation_id>/set-active', methods=['PUT'])
    @login_required
    def set_active_tax_calculation(calculation_id):
        return set_active_tax_calculation_handler(calculation_id)

    logger.info("Tax calculation routes registered successfully")
