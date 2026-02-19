"""
Centralised database connection helper.

Every module that needs a MySQL connection should call::

    from db import get_db_connection

Each call returns a fresh direct connection to MySQL.  No connection pool
is used so that the application stays within the server's 5-connection limit.
"""

import logging
import os

import mysql.connector
from dotenv import load_dotenv
from mysql.connector import Error

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Build DB_CONFIG from environment
# ---------------------------------------------------------------------------

def _build_db_config():
    host = os.environ.get('DB_HOST')
    port = os.environ.get('DB_PORT', '3306')
    database = os.environ.get('DB_NAME')
    user = os.environ.get('DB_USER')
    password = os.environ.get('DB_PASSWORD')

    if not all([host, database, user, password]):
        logger.error("Missing required database configuration in environment variables")
        logger.error(
            f"DB_HOST: {host}, DB_NAME: {database}, DB_USER: {user}, "
            f"DB_PASSWORD: {'***' if password else None}")
        return None

    try:
        port_int = int(port)
    except (ValueError, TypeError):
        logger.error(f"Invalid DB_PORT value: {port}, using default 3306")
        port_int = 3306

    return {
        'host': host,
        'port': port_int,
        'database': database,
        'user': user,
        'password': password,
        'charset': 'utf8mb4',
        'use_unicode': True,
    }


DB_CONFIG = _build_db_config()


def get_db_connection():
    """Return a new direct MySQL connection.

    The caller is responsible for closing the connection when done.
    Returns ``None`` if the configuration is missing or the connection fails.
    """
    if DB_CONFIG is None:
        logger.error(
            "Cannot connect to database: DB_CONFIG is not properly configured")
        return None
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        logger.debug("Database connection established")
        return connection
    except Error as e:
        logger.error(f"Error connecting to MySQL: {e}")
        return None
    except Exception as e:
        logger.error(
            f"Unexpected error connecting to database: {e}", exc_info=True)
        return None
