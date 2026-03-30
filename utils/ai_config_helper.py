"""
AI Configuration Helper
Fetches AI service configurations from the database.
"""

import logging
from typing import Dict, Optional
from db import get_db_connection

logger = logging.getLogger(__name__)


def get_ai_config(service_name: str) -> Optional[Dict[str, str]]:
    """
    Fetch AI configuration for a specific service from the database.

    Args:
        service_name: Name of the AI service (e.g., 'bill_scanner', 'exchange_analyzer')

    Returns:
        Dictionary with config keys: provider, api_key, api_url, model_name
        Returns None if service not found or not active
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT provider, api_key, api_url, model_name, description
            FROM ai_configs
            WHERE service_name = %s AND is_active = TRUE
            LIMIT 1
        """

        cursor.execute(query, (service_name,))
        config = cursor.fetchone()

        if not config:
            logger.warning(f"No active AI config found for service: {service_name}")
            return None

        logger.info(f"Successfully loaded AI config for service: {service_name}")
        return config

    except Exception as e:
        logger.error(f"Error fetching AI config for {service_name}: {e}")
        return None

    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def update_ai_config(service_name: str, provider: str = None, api_key: str = None,
                     api_url: str = None, model_name: str = None) -> bool:
    """
    Update AI configuration for a specific service.

    Args:
        service_name: Name of the AI service
        provider: AI provider name (optional)
        api_key: API key (optional)
        api_url: API endpoint URL (optional)
        model_name: AI model identifier (optional)

    Returns:
        True if update successful, False otherwise
    """
    conn = None
    try:
        # Build update query dynamically based on provided parameters
        updates = []
        params = []

        if provider is not None:
            updates.append("provider = %s")
            params.append(provider)

        if api_key is not None:
            updates.append("api_key = %s")
            params.append(api_key)

        if api_url is not None:
            updates.append("api_url = %s")
            params.append(api_url)

        if model_name is not None:
            updates.append("model_name = %s")
            params.append(model_name)

        if not updates:
            logger.warning("No fields to update")
            return False

        params.append(service_name)

        conn = get_db_connection()
        cursor = conn.cursor()

        query = f"""
            UPDATE ai_configs
            SET {', '.join(updates)}
            WHERE service_name = %s
        """

        cursor.execute(query, params)
        conn.commit()

        if cursor.rowcount > 0:
            logger.info(f"Successfully updated AI config for service: {service_name}")
            return True
        else:
            logger.warning(f"No AI config found to update for service: {service_name}")
            return False

    except Exception as e:
        logger.error(f"Error updating AI config for {service_name}: {e}")
        if conn:
            conn.rollback()
        return False

    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def list_ai_configs() -> list:
    """
    Get all AI service configurations.

    Returns:
        List of dictionaries containing all AI service configs
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT id, service_name, provider, api_key, api_url, model_name, 
                   is_active, description, created_at, updated_at
            FROM ai_configs
            ORDER BY service_name
        """

        cursor.execute(query)
        configs = cursor.fetchall()

        # Mask API keys for security (show only first 10 and last 4 characters)
        for config in configs:
            if config['api_key']:
                key = config['api_key']
                if len(key) > 14:
                    config['api_key_masked'] = f"{key[:10]}...{key[-4:]}"
                else:
                    config['api_key_masked'] = "***"

        return configs

    except Exception as e:
        logger.error(f"Error fetching AI configs: {e}")
        return []

    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
