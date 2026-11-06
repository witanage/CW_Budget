"""
Security primitives for the parking module.

- QR tokens: opaque HMAC-derived values; only their SHA-256 is stored.
- reCAPTCHA v2 server-side verification (fails closed).
- CSRF token bound to the session.
- ``park_login_required`` / ``park_admin_required`` decorators using
  parking-only session keys (isolated from the budget app's ``user_id``).
"""

import base64
import hashlib
import hmac
import logging
import os
import re
import secrets
import time
from functools import wraps

import requests
from flask import current_app, jsonify, redirect, request, session, url_for, abort

logger = logging.getLogger(__name__)

TOKEN_LENGTH = 32
TOKEN_RE = re.compile(r'^[A-Za-z0-9_-]{%d}$' % TOKEN_LENGTH)

SESSION_USER = 'park_user_id'
SESSION_ADMIN = 'park_is_admin'
SESSION_NAME = 'park_name'
SESSION_LOGIN_AT = 'park_login_at'
SESSION_CSRF = 'park_csrf'

RECAPTCHA_VERIFY_URL = 'https://www.google.com/recaptcha/api/siteverify'


# ---------------------------------------------------------------------------
# QR token
# ---------------------------------------------------------------------------

def _qr_secret() -> bytes:
    secret = os.environ.get('PARK_QR_SECRET')
    if secret:
        return secret.encode()
    # Derived fallback so the feature works out of the box; set PARK_QR_SECRET
    # explicitly so rotating SECRET_KEY does not invalidate printed QR codes.
    base = current_app.config['SECRET_KEY'].encode()
    return hmac.new(base, b'park-qr-secret-v1', hashlib.sha256).digest()


def new_nonce() -> str:
    return secrets.token_hex(16)


def derive_qr_token(vehicle_id: int, nonce: str) -> str:
    mac = hmac.new(_qr_secret(), f'v1:{vehicle_id}:{nonce}'.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode().rstrip('=')[:TOKEN_LENGTH]


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def is_well_formed_token(token: str) -> bool:
    return bool(token) and bool(TOKEN_RE.match(token))


def public_scan_url(token: str) -> str:
    base = os.environ.get('PARK_PUBLIC_BASE_URL', '').rstrip('/')
    path = url_for('parking.scan_page', token=token)
    if base:
        return base + path
    return url_for('parking.scan_page', token=token, _external=True)


def new_ntfy_topic() -> str:
    return 'park-' + secrets.token_urlsafe(18).replace('-', 'x').replace('_', 'y')


# ---------------------------------------------------------------------------
# reCAPTCHA
# ---------------------------------------------------------------------------

def recaptcha_site_key() -> str:
    return os.environ.get('RECAPTCHA_SITE_KEY', '')


def verify_recaptcha(response_token: str, remote_ip: str) -> bool:
    secret = os.environ.get('RECAPTCHA_SECRET_KEY')
    if not secret:
        logger.error('RECAPTCHA_SECRET_KEY is not configured; rejecting request (fail closed).')
        return False
    if not response_token or len(response_token) > 4096:
        return False
    try:
        resp = requests.post(RECAPTCHA_VERIFY_URL, data={
            'secret': secret,
            'response': response_token,
            'remoteip': remote_ip,
        }, timeout=5)
        result = resp.json()
    except Exception as e:  # network error, bad JSON
        logger.warning('reCAPTCHA verification error: %s', e)
        return False
    if not result.get('success'):
        logger.info('reCAPTCHA failed: %s', result.get('error-codes'))
        return False
    return True


# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------

def csrf_token() -> str:
    token = session.get(SESSION_CSRF)
    if not token:
        token = secrets.token_urlsafe(32)
        session[SESSION_CSRF] = token
    return token


def csrf_valid() -> bool:
    expected = session.get(SESSION_CSRF)
    sent = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token')
    if not sent and request.is_json:
        sent = (request.get_json(silent=True) or {}).get('csrf_token')
    return bool(expected and sent and hmac.compare_digest(expected, sent))


# ---------------------------------------------------------------------------
# Session / auth
# ---------------------------------------------------------------------------

def _session_hours() -> int:
    try:
        return max(1, int(os.environ.get('PARK_SESSION_HOURS', '12')))
    except ValueError:
        return 12


def start_park_session(user: dict) -> None:
    # Fixation protection: drop any previous parking state (incl. CSRF token).
    end_park_session()
    session.permanent = True
    session[SESSION_USER] = user['id']
    session[SESSION_ADMIN] = bool(user.get('is_admin'))
    session[SESSION_NAME] = user.get('full_name') or user.get('mobile_e164')
    session[SESSION_LOGIN_AT] = int(time.time())
    csrf_token()


def end_park_session() -> None:
    for key in (SESSION_USER, SESSION_ADMIN, SESSION_NAME, SESSION_LOGIN_AT, SESSION_CSRF):
        session.pop(key, None)


def current_park_user_id():
    uid = session.get(SESSION_USER)
    if not uid:
        return None
    login_at = session.get(SESSION_LOGIN_AT, 0)
    if time.time() - login_at > _session_hours() * 3600:
        end_park_session()
        return None
    return uid


def _wants_json() -> bool:
    return '/api/' in request.path or request.is_json


def park_login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        from . import repository  # local import avoids a cycle

        uid = current_park_user_id()
        user = repository.get_user(uid) if uid else None
        if not user or not user['is_active']:
            end_park_session()
            if _wants_json():
                return jsonify({'error': 'Authentication required'}), 401
            return redirect(url_for('parking.login'))
        # Re-read role from DB so a demotion takes effect immediately.
        session[SESSION_ADMIN] = bool(user['is_admin'])
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE') and not csrf_valid():
            return jsonify({'error': 'Invalid CSRF token'}), 403
        return f(*args, **kwargs)
    return wrapper


def park_admin_required(f):
    @wraps(f)
    @park_login_required
    def wrapper(*args, **kwargs):
        if not session.get(SESSION_ADMIN):
            if _wants_json():
                return jsonify({'error': 'Admin privileges required'}), 403
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def client_ip() -> str:
    return (request.remote_addr or '')[:45]


# ---------------------------------------------------------------------------
# Scan window (time allowed to submit after scanning the QR)
# ---------------------------------------------------------------------------

MIN_SCAN_WINDOW_MINUTES = 1
MAX_SCAN_WINDOW_MINUTES = 120


def _window_serializer():
    from itsdangerous import URLSafeSerializer
    return URLSafeSerializer(current_app.secret_key, salt='park-scan-window')


def issue_scan_window(token: str) -> str:
    """Signed proof of *when* this QR was scanned (GET of the scan page). Tamper-proof, stateless."""
    return _window_serializer().dumps({'t': token, 'iat': int(time.time())})


def scan_window_remaining(token: str, proof: str, window_minutes: int) -> int:
    """Seconds left to submit; 0 if the proof is missing/forged/for another QR/expired."""
    if not proof or not isinstance(proof, str) or len(proof) > 512:
        return 0
    try:
        data = _window_serializer().loads(proof)
        if not hmac.compare_digest(str(data.get('t')), token):
            return 0
        left = int(data['iat']) + int(window_minutes) * 60 - int(time.time())
    except Exception:
        return 0
    return max(0, left)
