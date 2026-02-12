"""
Centralised database connection pool.

Every module that needs a MySQL connection should call::

    from db import get_db_connection

The returned connection comes from a shared ``MySQLConnectionPool``.
Pool size and connection-timeout are read from the ``app_settings``
table at startup; if the table does not yet exist the defaults from
``schema.sql`` are used (pool_size=5, connection_timeout=10 s).
"""

import logging
import os

import mysql.connector
import mysql.connector.pooling
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

# ---------------------------------------------------------------------------
# Connection-pool management
# ---------------------------------------------------------------------------
_DB_POOL_SIZE_DEFAULT = 10
_DB_CONNECTION_TIMEOUT_DEFAULT = 10
_connection_pool = None


def _read_pool_settings_from_db():
    """Read pool_size and connection_timeout directly from the database.

    Uses a one-off raw connection (not from the pool) because this runs
    *before* the pool is created.  Returns ``(pool_size, timeout)``.
    """
    pool_size = _DB_POOL_SIZE_DEFAULT
    timeout = _DB_CONNECTION_TIMEOUT_DEFAULT
    if DB_CONFIG is None:
        return pool_size, timeout
    try:
        conn = mysql.connector.connect(
            **DB_CONFIG, connection_timeout=_DB_CONNECTION_TIMEOUT_DEFAULT)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT setting_key, value FROM app_settings "
            "WHERE setting_key IN ('db_pool_size', 'db_connection_timeout')"
        )
        for row in cursor.fetchall():
            if row['setting_key'] == 'db_pool_size':
                pool_size = max(1, min(32, int(row['value'])))
            elif row['setting_key'] == 'db_connection_timeout':
                timeout = max(1, min(60, int(row['value'])))
        cursor.close()
        conn.close()
    except Exception as e:
        logger.warning(
            f"Could not read pool settings from DB ({e}); using defaults "
            f"pool_size={pool_size}, timeout={timeout}")
    return pool_size, timeout


def _create_connection_pool():
    """Create (or recreate) the global connection pool."""
    global _connection_pool
    if DB_CONFIG is None:
        return

    pool_size, timeout = _read_pool_settings_from_db()

    pool_config = dict(DB_CONFIG)
    pool_config['connection_timeout'] = timeout

    try:
        _connection_pool = mysql.connector.pooling.MySQLConnectionPool(
            pool_name="cw_budget_pool",
            pool_size=pool_size,
            pool_reset_session=True,
            **pool_config,
        )
        logger.info(
            f"Database connection pool created "
            f"(pool_size={pool_size}, connection_timeout={timeout}s)")
    except Error as e:
        logger.error(f"Failed to create connection pool: {e}")
        _connection_pool = None


# Initialise the pool at import time (server start).
_create_connection_pool()


def get_db_connection():
    """Get a connection from the pool.

    Falls back to a direct connection if the pool is unavailable so the
    application can still operate (e.g. during first-time schema setup).
    """
    if _connection_pool is not None:
        try:
            connection = _connection_pool.get_connection()
            logger.debug("Database connection acquired from pool")
            return connection
        except Error as e:
            logger.warning(
                f"Pool connection failed ({e}), falling back to direct connection")

    if DB_CONFIG is None:
        logger.error(
            "Cannot connect to database: DB_CONFIG is not properly configured")
        return None
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        logger.debug("Database connection established (direct, non-pooled)")
        return connection
    except Error as e:
        logger.error(f"Error connecting to MySQL: {e}")
        return None
    except Exception as e:
        logger.error(
            f"Unexpected error connecting to database: {e}", exc_info=True)
        return None
