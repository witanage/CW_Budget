"""
User Tab Service

Manages user tab preferences for desktop and mobile views.
Handles tab visibility configuration and initialization for new users.
"""

import logging
from mysql.connector import Error

from db import get_db_connection

logger = logging.getLogger(__name__)


def get_enabled_tabs(user_id, device_type='desktop'):
    """
    Get list of enabled tabs for a user based on device type.
    
    Args:
        user_id: The user's ID
        device_type: 'desktop' or 'mobile' (default: 'desktop')
    
    Returns:
        List of enabled tab names in display order, e.g. ['transactions', 'tax', 'reports', 'rateTrends']
        Returns all tabs as default if database query fails.
    """
    enabled_tabs = []
    
    # Determine which column to check based on device type
    is_enabled_column = 'is_enabled' if device_type == 'desktop' else 'is_enabled_mobile'
    
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor(dictionary=True)
        try:
            # Fetch user's enabled tabs
            cursor.execute(f"""
                SELECT tab_name FROM user_tabs
                WHERE user_id = %s AND {is_enabled_column} = TRUE
                ORDER BY 
                    CASE tab_name
                        WHEN 'transactions' THEN 1
                        WHEN 'tax' THEN 2
                        WHEN 'reports' THEN 3
                        WHEN 'rateTrends' THEN 4
                        ELSE 5
                    END
            """, (user_id,))
            enabled_tabs = [row['tab_name'] for row in cursor.fetchall()]
            
            # If no tabs found, initialize with all tabs enabled (for existing/new users)
            if not enabled_tabs:
                enabled_tabs = initialize_user_tabs(cursor, connection, user_id)
                
        except Error as e:
            logger.error(f"Error fetching user tabs for user {user_id} ({device_type}): {str(e)}")
            # Default to all tabs on error
            enabled_tabs = ['transactions', 'tax', 'reports', 'rateTrends']
        finally:
            cursor.close()
            connection.close()
    else:
        # Default to all tabs if connection fails
        logger.warning(f"Database connection failed for user {user_id} tabs")
        enabled_tabs = ['transactions', 'tax', 'reports', 'rateTrends']
    
    return enabled_tabs


def initialize_user_tabs(cursor, connection, user_id):
    """
    Initialize all tabs as enabled for a user who doesn't have tab preferences yet.
    
    Args:
        cursor: Database cursor (already open)
        connection: Database connection (for commit)
        user_id: The user's ID
    
    Returns:
        List of all available tab names
    """
    available_tabs = ['transactions', 'tax', 'reports', 'rateTrends']
    
    try:
        for tab in available_tabs:
            cursor.execute("""
                INSERT INTO user_tabs (user_id, tab_name, is_enabled, is_enabled_mobile)
                VALUES (%s, %s, TRUE, TRUE)
            """, (user_id, tab))
        connection.commit()
        logger.info(f"Initialized tabs for user {user_id}")
    except Error as e:
        logger.error(f"Error initializing tabs for user {user_id}: {str(e)}")
        connection.rollback()
    
    return available_tabs


def update_tab_visibility(user_id, tab_name, is_enabled, device_type='desktop'):
    """
    Update visibility of a specific tab for a user.
    
    Args:
        user_id: The user's ID
        tab_name: Name of the tab (e.g., 'transactions', 'tax', 'reports', 'rateTrends')
        is_enabled: Boolean - whether tab should be enabled
        device_type: 'desktop' or 'mobile' (default: 'desktop')
    
    Returns:
        Boolean indicating success
    """
    is_enabled_column = 'is_enabled' if device_type == 'desktop' else 'is_enabled_mobile'
    
    connection = get_db_connection()
    if not connection:
        logger.error(f"Failed to connect to database for tab update")
        return False
    
    cursor = connection.cursor()
    try:
        cursor.execute(f"""
            UPDATE user_tabs
            SET {is_enabled_column} = %s
            WHERE user_id = %s AND tab_name = %s
        """, (is_enabled, user_id, tab_name))
        connection.commit()
        
        logger.info(f"Updated tab '{tab_name}' for user {user_id} ({device_type}): enabled={is_enabled}")
        return True
        
    except Error as e:
        logger.error(f"Error updating tab visibility: {str(e)}")
        connection.rollback()
        return False
    finally:
        cursor.close()
        connection.close()
