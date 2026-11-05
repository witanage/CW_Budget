"""
ntfy publisher for parking alerts.

Uses the JSON publish API (POST to the server root) so titles/messages with
emoji or Sinhala/Tamil text need no header encoding. Server URL and optional
credentials are shared with the existing ntfy integration via ``app_settings``.
"""

import logging

import requests

from db import get_setting

logger = logging.getLogger(__name__)

DEFAULT_NTFY_SERVER = 'https://ntfy.sh'

REASONS = {
    'blocking':    ('Your vehicle is blocking another vehicle. Please move it.', 4),
    'lights_on':   ('Your vehicle\'s lights appear to be on.', 3),
    'window_open': ('A window of your vehicle appears to be open.', 3),
    'alarm':       ('Your vehicle\'s alarm is going off.', 4),
    'towing':      ('Your vehicle may be towed or fined. Please attend urgently.', 5),
    'other':       ('Someone needs you at your vehicle.', 4),
}


def ntfy_server() -> str:
    return (get_setting('ntfy_server_url') or DEFAULT_NTFY_SERVER).strip().rstrip('/')


def build_message(plate_display, reason, message=None, scanner_mobile=None, lat=None, lng=None):
    reason_text, priority = REASONS.get(reason, REASONS['other'])
    lines = [reason_text]
    if message:
        lines.append(f'Note: {message}')
    if scanner_mobile:
        lines.append(f'Contact: {scanner_mobile}')
    if lat is not None and lng is not None:
        lines.append(f'Location: https://maps.google.com/?q={lat},{lng}')
    payload = {
        'title': f'🚗 Parking alert: {plate_display}',
        'message': '\n'.join(lines),
        'priority': priority,
        'tags': ['car', 'warning'],
    }
    actions = []
    if scanner_mobile:
        actions.append({'action': 'view', 'label': 'Call', 'url': f'tel:{scanner_mobile}', 'clear': False})
    if lat is not None and lng is not None:
        actions.append({'action': 'view', 'label': 'Map', 'url': f'https://maps.google.com/?q={lat},{lng}'})
    if actions:
        payload['actions'] = actions
    return payload


def send(topic: str, payload: dict) -> bool:
    if not topic:
        return False
    server = ntfy_server()
    user, pwd = get_setting('ntfy_username'), get_setting('ntfy_password')
    auth = (user, pwd) if user and pwd else None
    body = dict(payload, topic=topic)
    try:
        resp = requests.post(server, json=body, auth=auth, timeout=6)
        if resp.status_code == 200:
            return True
        logger.warning('ntfy publish failed: status=%s body=%s', resp.status_code, resp.text[:120])
    except requests.RequestException as e:
        logger.warning('ntfy publish error: %s', e)
    if server != DEFAULT_NTFY_SERVER and auth is None:
        # Same fallback behaviour as the existing exchange-rate notifier.
        try:
            return requests.post(DEFAULT_NTFY_SERVER, json=body, timeout=6).status_code == 200
        except requests.RequestException:
            return False
    return False
