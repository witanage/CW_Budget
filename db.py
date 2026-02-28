"""
Centralised database connection helper.

Every module that needs a MySQL connection should call::

    from db import get_db_connection

Each call creates a fresh connection to the database.  This avoids holding
persistent pooled connections open, which is important for TiDB Serverless
(and similar services) that impose a low maximum-connection limit.

Connections are short-lived: callers open one, execute their queries, and
close it promptly.  Because the connection only exists for the duration of
the operation, concurrent connection usage stays well within server limits.

Retry logic with exponential back-off is included to handle transient
connection failures.
"""

import logging
import os
import time

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

    required = {'DB_HOST': host, 'DB_NAME': database,
                'DB_USER': user, 'DB_PASSWORD': password}
    missing = [name for name, val in required.items() if not val]

    if missing:
        logger.error(
            "Missing required database environment variable(s): %s. "
            "Copy .env.example to .env and fill in your values: "
            "cp .env.example .env",
            ', '.join(missing))
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
# On-demand connection (no pool — friendly to low connection-limit servers)
# ---------------------------------------------------------------------------


def get_db_connection():
    """Create and return a fresh MySQL connection.

    A new connection is opened on every call and closed by the caller when
    done.  This keeps the number of concurrent server-side connections to a
    minimum, which is essential for TiDB Serverless and other services that
    cap the maximum number of connections.

    Retries up to 3 times with exponential back-off when the server rejects
    the connection.  Returns ``None`` when all attempts fail.
    """
    if DB_CONFIG is None:
        logger.error(
            "Cannot connect to database: DB_CONFIG is not configured. "
            "Ensure DB_HOST, DB_NAME, DB_USER, and DB_PASSWORD are set "
            "in your .env file (see .env.example).")
        return None

    last_err = None
    for attempt in range(4):           # 0, 1, 2, 3 → up to 4 attempts
        try:
            connection = mysql.connector.connect(**DB_CONFIG)
            logger.debug("Database connection created (attempt %d)", attempt)
            return connection
        except Error as e:
            last_err = e
            if attempt < 3:
                wait = 0.5 * (2 ** attempt)   # 0.5s, 1s, 2s
                logger.warning(
                    "Connection attempt %d failed (%s), retrying in %.1fs …",
                    attempt, e, wait)
                time.sleep(wait)

    logger.error("All connection attempts failed: %s", last_err)
    return None
