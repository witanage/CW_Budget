"""
Data access for the parking module. All SQL touching ``park_*`` tables lives here.

Every query that reads or changes owner data takes ``user_id`` and filters on
it, so route handlers cannot accidentally expose another user's records.
"""

import logging
import os
import secrets
from contextlib import contextmanager

from db import get_db_connection

from . import security

logger = logging.getLogger(__name__)

SCHEMA_FILE = os.path.join(os.path.dirname(__file__), 'schema.sql')


class DatabaseUnavailable(RuntimeError):
    pass


class DuplicateError(RuntimeError):
    pass


@contextmanager
def _cursor(commit=False):
    conn = get_db_connection()
    if not conn:
        raise DatabaseUnavailable('Database connection failed')
    cur = conn.cursor(dictionary=True)
    try:
        # All park_* timestamps are read/written in UTC; the UI converts to local time.
        cur.execute("SET time_zone = '+00:00'")
        yield cur
        if commit:
            conn.commit()
    except Exception as e:
        conn.rollback()
        if getattr(e, 'errno', None) == 1062:  # ER_DUP_ENTRY
            raise DuplicateError(str(e)) from e
        raise
    finally:
        cur.close()
        conn.close()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def init_schema():
    with open(SCHEMA_FILE, encoding='utf-8') as fh:
        statements = [s.strip() for s in fh.read().split(';')]
    with _cursor(commit=True) as cur:
        for stmt in statements:
            body = '\n'.join(l for l in stmt.splitlines() if not l.strip().startswith('--')).strip()
            if not body:
                continue
            try:
                cur.execute(body)
            except Exception as e:
                # Re-running an ALTER ... ADD COLUMN on an up-to-date table (ER_DUP_FIELDNAME).
                if getattr(e, 'errno', None) != 1060:
                    raise


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

_USER_COLS = ('id, full_name, country_code, mobile_e164, ntfy_topic, is_admin, is_active, '
              'scan_window_minutes, created_at, last_login_at, totp_enabled')


def get_user(user_id):
    with _cursor() as cur:
        cur.execute(f'SELECT {_USER_COLS} FROM park_users WHERE id = %s', (user_id,))
        return cur.fetchone()


def get_user_for_login(mobile_e164):
    with _cursor() as cur:
        cur.execute(f'SELECT {_USER_COLS}, password_hash FROM park_users WHERE mobile_e164 = %s',
                    (mobile_e164,))
        return cur.fetchone()


def get_password_hash(user_id):
    with _cursor() as cur:
        cur.execute('SELECT password_hash FROM park_users WHERE id = %s', (user_id,))
        row = cur.fetchone()
        return row['password_hash'] if row else None


def create_user(full_name, country_code, mobile_e164, password_hash, is_admin=False, is_active=True):
    with _cursor(commit=True) as cur:
        cur.execute(
            'INSERT INTO park_users (full_name, country_code, mobile_e164, password_hash, ntfy_topic, '
            'is_admin, is_active) VALUES (%s, %s, %s, %s, %s, %s, %s)',
            (full_name or None, country_code, mobile_e164, password_hash, security.new_ntfy_topic(),
             bool(is_admin), bool(is_active)))
        return cur.lastrowid


def create_user_with_vehicle(full_name, country_code, mobile_e164, password_hash, plate, is_admin=False):
    """User + first vehicle in one transaction (self-registration / admin create)."""
    with _cursor(commit=True) as cur:
        cur.execute(
            'INSERT INTO park_users (full_name, country_code, mobile_e164, password_hash, ntfy_topic, is_admin) '
            'VALUES (%s, %s, %s, %s, %s, %s)',
            (full_name or None, country_code, mobile_e164, password_hash, security.new_ntfy_topic(),
             bool(is_admin)))
        user_id = cur.lastrowid
        _insert_vehicle(cur, user_id, country_code, plate, None)
        return user_id


def record_login(user_id):
    with _cursor(commit=True) as cur:
        cur.execute('UPDATE park_users SET last_login_at = UTC_TIMESTAMP() WHERE id = %s', (user_id,))


def update_password(user_id, password_hash):
    with _cursor(commit=True) as cur:
        cur.execute('UPDATE park_users SET password_hash = %s, password_changed_at = UTC_TIMESTAMP() '
                    'WHERE id = %s', (password_hash, user_id))


def rotate_ntfy_topic(user_id):
    topic = security.new_ntfy_topic()
    with _cursor(commit=True) as cur:
        cur.execute('UPDATE park_users SET ntfy_topic = %s WHERE id = %s', (topic, user_id))
    return topic


def set_scan_window(user_id, minutes):
    with _cursor(commit=True) as cur:
        cur.execute('UPDATE park_users SET scan_window_minutes = %s WHERE id = %s', (minutes, user_id))


def list_users():
    with _cursor() as cur:
        cur.execute(
            f'SELECT {_USER_COLS}, (SELECT COUNT(*) FROM park_vehicles v WHERE v.user_id = u.id) '
            'AS vehicle_count FROM park_users u ORDER BY u.created_at DESC')
        return cur.fetchall()


# ---------------------------------------------------------------------------
# Two-factor authentication
# ---------------------------------------------------------------------------

def get_totp(user_id):
    """Secret + state for verification. Never returned by the generic user queries."""
    with _cursor() as cur:
        cur.execute('SELECT totp_secret, totp_enabled, totp_last_step, totp_recovery '
                    'FROM park_users WHERE id = %s', (user_id,))
        return cur.fetchone()


def enable_totp(user_id, secret, recovery_json, step):
    with _cursor(commit=True) as cur:
        cur.execute('UPDATE park_users SET totp_secret = %s, totp_enabled = TRUE, totp_last_step = %s, '
                    'totp_recovery = %s WHERE id = %s', (secret, step, recovery_json, user_id))
        return cur.rowcount > 0


def disable_totp(user_id):
    with _cursor(commit=True) as cur:
        cur.execute('UPDATE park_users SET totp_secret = NULL, totp_enabled = FALSE, totp_last_step = 0, '
                    'totp_recovery = NULL WHERE id = %s', (user_id,))
        return cur.rowcount > 0


def claim_totp_step(user_id, step):
    """Atomically accept a time step once; False if it (or a later one) was already used."""
    with _cursor(commit=True) as cur:
        cur.execute('UPDATE park_users SET totp_last_step = %s WHERE id = %s AND totp_last_step < %s',
                    (step, user_id, step))
        return cur.rowcount > 0


def replace_recovery(user_id, old_json, new_json):
    """Compare-and-set so one recovery code cannot be spent twice concurrently."""
    with _cursor(commit=True) as cur:
        cur.execute('UPDATE park_users SET totp_recovery = %s WHERE id = %s AND totp_recovery = %s',
                    (new_json, user_id, old_json))
        return cur.rowcount > 0


def set_user_active(user_id, is_active):
    with _cursor(commit=True) as cur:
        cur.execute('UPDATE park_users SET is_active = %s WHERE id = %s', (bool(is_active), user_id))
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Vehicles
# ---------------------------------------------------------------------------

_VEHICLE_COLS = ('id, user_id, country_code, plate_normalized, plate_display, region_code, nickname, '
                 'qr_nonce, qr_rotated_at, is_active, created_at')


def _insert_vehicle(cur, user_id, country_code, plate, nickname):
    nonce = security.new_nonce()
    # Placeholder hash keeps the UNIQUE NOT NULL column satisfied until we know the id.
    cur.execute(
        'INSERT INTO park_vehicles (user_id, country_code, plate_normalized, plate_display, region_code, '
        'nickname, qr_nonce, qr_token_hash) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
        (user_id, country_code, plate.normalized, plate.display, plate.region, nickname or None,
         nonce, secrets.token_hex(32)))
    vehicle_id = cur.lastrowid
    token = security.derive_qr_token(vehicle_id, nonce)
    cur.execute('UPDATE park_vehicles SET qr_token_hash = %s WHERE id = %s',
                (security.hash_token(token), vehicle_id))
    return vehicle_id


def add_vehicle(user_id, country_code, plate, nickname=None):
    with _cursor(commit=True) as cur:
        return _insert_vehicle(cur, user_id, country_code, plate, nickname)


def list_all_vehicles():
    """Every vehicle with its owner (admin registry view). qr_nonce is deliberately not selected."""
    with _cursor() as cur:
        cur.execute(
            'SELECT v.id, v.user_id, v.plate_display, v.nickname, v.is_active, v.created_at, '
            'u.full_name AS owner_name, u.mobile_e164 AS owner_mobile '
            'FROM park_vehicles v JOIN park_users u ON u.id = v.user_id ORDER BY v.created_at DESC')
        return cur.fetchall()


def list_vehicles(user_id):
    with _cursor() as cur:
        cur.execute(
            f'SELECT {_VEHICLE_COLS}, '
            '(SELECT COUNT(*) FROM park_scans s WHERE s.vehicle_id = v.id) AS scan_count, '
            '(SELECT MAX(scanned_at) FROM park_scans s WHERE s.vehicle_id = v.id) AS last_scan_at '
            'FROM park_vehicles v WHERE user_id = %s ORDER BY created_at', (user_id,))
        return cur.fetchall()


def get_vehicle(user_id, vehicle_id):
    with _cursor() as cur:
        cur.execute(f'SELECT {_VEHICLE_COLS} FROM park_vehicles WHERE id = %s AND user_id = %s',
                    (vehicle_id, user_id))
        return cur.fetchone()


def rotate_vehicle_qr(user_id, vehicle_id):
    nonce = security.new_nonce()
    token_hash = security.hash_token(security.derive_qr_token(vehicle_id, nonce))
    with _cursor(commit=True) as cur:
        cur.execute(
            'UPDATE park_vehicles SET qr_nonce = %s, qr_token_hash = %s, qr_rotated_at = UTC_TIMESTAMP() '
            'WHERE id = %s AND user_id = %s', (nonce, token_hash, vehicle_id, user_id))
        return cur.rowcount > 0


def set_vehicle_active(user_id, vehicle_id, is_active):
    with _cursor(commit=True) as cur:
        cur.execute('UPDATE park_vehicles SET is_active = %s WHERE id = %s AND user_id = %s',
                    (bool(is_active), vehicle_id, user_id))
        return cur.rowcount > 0


def delete_vehicle(user_id, vehicle_id):
    with _cursor(commit=True) as cur:
        cur.execute('DELETE FROM park_vehicles WHERE id = %s AND user_id = %s', (vehicle_id, user_id))
        return cur.rowcount > 0


def find_vehicle_by_token(token):
    """Public lookup. Returns vehicle + owner topic only if both are active."""
    with _cursor() as cur:
        cur.execute(
            'SELECT v.id, v.plate_display, v.country_code, u.ntfy_topic, u.scan_window_minutes '
            'FROM park_vehicles v JOIN park_users u ON u.id = v.user_id '
            'WHERE v.qr_token_hash = %s AND v.is_active = TRUE AND u.is_active = TRUE',
            (security.hash_token(token),))
        return cur.fetchone()


# ---------------------------------------------------------------------------
# Scans
# ---------------------------------------------------------------------------

def seconds_since_last_sent(vehicle_id):
    with _cursor() as cur:
        cur.execute(
            "SELECT TIMESTAMPDIFF(SECOND, MAX(scanned_at), UTC_TIMESTAMP()) AS ago FROM park_scans "
            "WHERE vehicle_id = %s AND notify_status = 'sent'", (vehicle_id,))
        row = cur.fetchone()
        return row['ago'] if row else None


def record_scan(vehicle_id, ip_address, user_agent, scanner_mobile, latitude, longitude, accuracy,
                reason, message, notify_status):
    with _cursor(commit=True) as cur:
        cur.execute(
            'INSERT INTO park_scans (vehicle_id, scanned_at, ip_address, user_agent, scanner_mobile, '
            'latitude, longitude, location_accuracy_m, reason, message, notify_status) '
            'VALUES (%s, UTC_TIMESTAMP(), %s, %s, %s, %s, %s, %s, %s, %s, %s)',
            (vehicle_id, ip_address, (user_agent or '')[:255] or None, scanner_mobile or None,
             latitude, longitude, accuracy, reason, message or None, notify_status))
        return cur.lastrowid


def list_scans(user_id, vehicle_id=None, limit=200, offset=0):
    sql = ('SELECT s.id, s.vehicle_id, v.plate_display, s.scanned_at, s.ip_address, s.scanner_mobile, '
           's.latitude, s.longitude, s.location_accuracy_m, s.reason, s.message, s.notify_status '
           'FROM park_scans s JOIN park_vehicles v ON v.id = s.vehicle_id WHERE v.user_id = %s')
    params = [user_id]
    if vehicle_id:
        sql += ' AND v.id = %s'
        params.append(vehicle_id)
    sql += ' ORDER BY s.scanned_at DESC, s.id DESC LIMIT %s OFFSET %s'
    params += [int(limit), int(offset)]
    with _cursor() as cur:
        cur.execute(sql, tuple(params))
        return cur.fetchall()
