"""TOTP two-factor helpers (RFC 6238: SHA-1, 6 digits, 30 s: works with Authy, Google Authenticator, etc.)."""

import base64
import hashlib
import hmac
import io
import json
import re
import secrets
import time

import pyotp
import qrcode

ISSUER = 'Parking Friend Messenger'
PERIOD = 30
RECOVERY_COUNT = 8
_CODE_RE = re.compile(r'^\d{6}$')


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, account: str) -> str:
    return pyotp.TOTP(secret, interval=PERIOD).provisioning_uri(name=account, issuer_name=ISSUER)


def qr_data_uri(uri: str) -> str:
    img = qrcode.make(uri, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=6, border=2)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()


def clean_code(raw) -> str:
    return re.sub(r'[\s-]', '', str(raw or ''))


def is_totp_code(raw) -> bool:
    return bool(_CODE_RE.match(clean_code(raw)))


def verify(secret: str, raw_code, last_step: int = 0):
    """Return the matched time step (> last_step) or None. Allows +/-1 step of clock drift."""
    code = clean_code(raw_code)
    if not secret or not _CODE_RE.match(code):
        return None
    totp = pyotp.TOTP(secret, interval=PERIOD)
    now = int(time.time() // PERIOD)
    for step in (now - 1, now, now + 1):
        if step > int(last_step or 0) and hmac.compare_digest(totp.at(step * PERIOD), code):
            return step
    return None


# ---- recovery codes ---------------------------------------------------------

def _hash(code: str) -> str:
    return hashlib.sha256(clean_code(code).upper().encode()).hexdigest()


def new_recovery_codes():
    """(plain codes to show once, JSON of their hashes to store)."""
    alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    plain = []
    for _ in range(RECOVERY_COUNT):
        raw = ''.join(secrets.choice(alphabet) for _ in range(10))
        plain.append(f'{raw[:5]}-{raw[5:]}')
    return plain, json.dumps([_hash(c) for c in plain])


def use_recovery_code(stored_json, raw_code):
    """Return the new JSON list with the code removed, or None if it does not match."""
    try:
        hashes = json.loads(stored_json or '[]')
    except ValueError:
        return None
    candidate = _hash(raw_code)
    match = None
    for h in hashes:  # no early exit: constant work per attempt
        if hmac.compare_digest(h, candidate):
            match = h
    if match is None:
        return None
    hashes.remove(match)
    return json.dumps(hashes)
