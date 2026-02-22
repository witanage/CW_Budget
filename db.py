"""
Centralised database connection helper.

Every module that needs a MySQL connection should call::

    from db import get_db_connection

Connections are served from a small ``MySQLConnectionPool`` (pool_size=3)
so that the application stays within the server's 5-connection limit while
still reusing connections efficiently.

When a pool connection is not available (e.g. all slots busy), the caller
retries with exponential back-off before giving up.
"""

import logging
import os
import threading
import time

import mysql.connector
from dotenv import load_dotenv
from mysql.connector import Error, pooling

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
# Connection pool (lazy-initialised, thread-safe)
# ---------------------------------------------------------------------------
_pool = None
_pool_lock = threading.Lock()
_POOL_SIZE = 3  # Keep well under the server's max_user_connections (5)


def _get_pool():
    """Return the shared connection pool, creating it on first call."""
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is not None:          # double-check after acquiring lock
            return _pool
        if DB_CONFIG is None:
            return None
        try:
            _pool = pooling.MySQLConnectionPool(
                pool_name="cw_budget_pool",
                pool_size=_POOL_SIZE,
                pool_reset_session=True,
                **DB_CONFIG,
            )
            logger.info("Database connection pool created (pool_size=%d)", _POOL_SIZE)
            return _pool
        except Error as e:
            logger.error("Failed to create connection pool: %s", e)
            return None


def get_db_connection():
    """Return a pooled MySQL connection.

    Retries up to 3 times with short back-off when the pool is exhausted or
    the server rejects the connection.  Returns ``None`` when all attempts
    fail.

    The caller is still responsible for closing the connection (which returns
    it to the pool).
    """
    pool = _get_pool()
    if pool is None:
        if DB_CONFIG is None:
            logger.error(
                "Cannot connect to database: DB_CONFIG is not properly configured")
        return None

    last_err = None
    for attempt in range(4):           # 0, 1, 2, 3 → up to 4 attempts
        try:
            connection = pool.get_connection()
            # Ensure the connection is still alive after sitting in the pool.
            connection.ping(reconnect=True, attempts=1, delay=0)
            logger.debug("Database connection acquired from pool (attempt %d)", attempt)
            return connection
        except Error as e:
            last_err = e
            if attempt < 3:
                wait = 0.5 * (2 ** attempt)   # 0.5s, 1s, 2s
                logger.warning(
                    "Pool connection attempt %d failed (%s), retrying in %.1fs …",
                    attempt, e, wait)
                time.sleep(wait)

    logger.error("All pool connection attempts failed: %s", last_err)
    return None
