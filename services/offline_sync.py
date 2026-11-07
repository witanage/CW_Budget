"""
Idempotency keys for transactions created from the offline queue.

The client tags every new transaction with a ``client_request_id`` (UUID).  If a
request reaches the server but the response is lost (flaky connection), the
client retries with the same id and we return the transaction that was already
created instead of inserting a duplicate.
"""

import logging

from mysql.connector import Error

from db import get_db_connection

logger = logging.getLogger(__name__)

MAX_KEY_LENGTH = 64
_table_ready = False


def normalize_key(value):
    """Return a clean key string, or None when absent/invalid."""
    if not value:
        return None
    key = str(value).strip()
    if not key or len(key) > MAX_KEY_LENGTH:
        return None
    return key


def ensure_table():
    """Create the key table once per process (DDL, so on its own connection)."""
    global _table_ready
    if _table_ready:
        return
    connection = get_db_connection()
    if not connection:
        return
    cursor = connection.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transaction_client_keys (
                user_id         INT         NOT NULL,
                client_id       VARCHAR(64) NOT NULL,
                transaction_id  INT         NOT NULL,
                created_at      TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, client_id)
            )
        """)
        connection.commit()
        _table_ready = True
    except Error as e:
        logger.warning("Could not create transaction_client_keys: %s", e)
    finally:
        cursor.close()
        connection.close()


def find_existing(cursor, user_id, key):
    """Return the transaction id previously created for this key, else None."""
    if not key:
        return None
    ensure_table()
    try:
        cursor.execute(
            "SELECT transaction_id FROM transaction_client_keys WHERE user_id = %s AND client_id = %s",
            (user_id, key))
        row = cursor.fetchone()
    except Error as e:
        logger.warning("Idempotency lookup failed: %s", e)
        return None
    if not row:
        return None
    return row['transaction_id'] if isinstance(row, dict) else row[0]


def record(cursor, user_id, key, transaction_id):
    """Remember the key inside the caller's transaction (commit is the caller's)."""
    if not key:
        return
    try:
        cursor.execute(
            "INSERT IGNORE INTO transaction_client_keys (user_id, client_id, transaction_id) "
            "VALUES (%s, %s, %s)",
            (user_id, key, transaction_id))
    except Error as e:
        # Never fail the real insert because bookkeeping failed.
        logger.warning("Could not record idempotency key: %s", e)
