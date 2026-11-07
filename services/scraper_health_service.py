"""
Scraper health monitoring.

Every exchange-rate fetch attempt is already recorded in
``exchange_rate_refresh_logs`` (one row per source such as ``HNB_USD``).  This
module derives "last successful fetch" per source from that table, flags
sources that have gone stale, and alerts the admin through ntfy.

Settings (``app_settings``):
  * ``scraper_stale_minutes`` – minutes without a successful fetch before a
    source is considered stale (default 360).  CBSL publishes once per
    business day, so it always gets at least ``CBSL_MIN_STALE_MINUTES``.
  * ``ntfy_topic_admin``       – ntfy topic that receives the alerts.  Left
    empty, alerts are only logged.  Deliberately separate from the public
    rate-change topics, which every subscriber receives.

A fetch counts as successful whenever the scraper parsed a rate, even if the
rate did not change, so quiet days and weekends do not raise false alarms.
"""

import logging
import re
import time
from datetime import datetime

import requests
from flask import jsonify
from mysql.connector import Error

from db import get_db_connection, get_setting

logger = logging.getLogger(__name__)

DEFAULT_STALE_MINUTES = 360
CBSL_MIN_STALE_MINUTES = 2880          # 48 h
REALERT_AFTER_MINUTES = 720            # remind again after 12 h if still stale
LOOKBACK_DAYS = 7
SOURCE_RE = re.compile(r'^[A-Z]+_[A-Z]{3}$')   # HNB_USD, DFCC_GBP, ... (ignores legacy un-suffixed names)
CACHE_SECONDS = 60                     # admin page reloads reuse the last result

_cache = {'at': 0.0, 'data': None}

_schema_ready = False


# ---------------------------------------------------------------------------
# Schema / settings bootstrap (idempotent, once per process)
# ---------------------------------------------------------------------------

def _ensure_schema():
    global _schema_ready
    if _schema_ready:
        return
    connection = get_db_connection()
    if not connection:
        return
    cursor = connection.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scraper_alert_state (
                source      VARCHAR(64) NOT NULL PRIMARY KEY,
                alerted_at  DATETIME    NOT NULL,
                last_error  TEXT        NULL
            )
        """)
        # Seed settings so they show up (and are editable) in the admin settings page.
        seeds = [
            ('scraper_stale_minutes', str(DEFAULT_STALE_MINUTES),
             'Minutes without a successful exchange-rate fetch before a source is flagged stale'),
            ('ntfy_topic_admin', '',
             'ntfy topic for admin alerts (e.g. stale exchange-rate scrapers). Empty = log only'),
        ]
        for key, value, description in seeds:
            cursor.execute("SELECT 1 FROM app_settings WHERE setting_key = %s", (key,))
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO app_settings (setting_key, value, description) VALUES (%s, %s, %s)",
                    (key, value, description))
        connection.commit()
        _schema_ready = True
    except Error as e:
        logger.warning("Scraper health schema/settings bootstrap failed: %s", e)
    finally:
        cursor.close()
        connection.close()


def _stale_threshold_minutes():
    raw = get_setting('scraper_stale_minutes', str(DEFAULT_STALE_MINUTES))
    try:
        value = int(str(raw).strip())
        return value if value > 0 else DEFAULT_STALE_MINUTES
    except (ValueError, TypeError):
        return DEFAULT_STALE_MINUTES


# ---------------------------------------------------------------------------
# Health computation
# ---------------------------------------------------------------------------

def get_scraper_health():
    """Return per-source health derived from exchange_rate_refresh_logs."""
    _ensure_schema()
    threshold = _stale_threshold_minutes()

    connection = get_db_connection()
    if not connection:
        raise RuntimeError('Database connection failed')
    cursor = connection.cursor(dictionary=True)
    try:
        window = f"created_at >= NOW() - INTERVAL {LOOKBACK_DAYS} DAY"

        cursor.execute(f"""
            SELECT source,
                   MAX(CASE WHEN status = 'success' THEN created_at END) AS last_success,
                   TIMESTAMPDIFF(MINUTE,
                                 MAX(CASE WHEN status = 'success' THEN created_at END), NOW()) AS success_age,
                   MAX(created_at) AS last_attempt,
                   TIMESTAMPDIFF(MINUTE, MAX(created_at), NOW()) AS attempt_age
            FROM exchange_rate_refresh_logs
            WHERE {window}
            GROUP BY source
        """)
        rows = sorted((r for r in cursor.fetchall() if SOURCE_RE.match(r['source'])),
                      key=lambda r: r['source'])

        # Failures since the last success (consecutive failure streak)
        cursor.execute(f"""
            SELECT l.source, COUNT(*) AS failures
            FROM exchange_rate_refresh_logs l
            JOIN (SELECT source,
                         MAX(CASE WHEN status = 'success' THEN created_at END) AS ls
                  FROM exchange_rate_refresh_logs
                  WHERE {window}
                  GROUP BY source) s ON s.source = l.source
            WHERE l.status <> 'success'
              AND l.{window}
              AND (s.ls IS NULL OR l.created_at > s.ls)
            GROUP BY l.source
        """)
        failures = {r['source']: r['failures'] for r in cursor.fetchall()}

        # Most recent error message per source
        cursor.execute(f"""
            SELECT l.source, l.error_message
            FROM exchange_rate_refresh_logs l
            JOIN (SELECT source, MAX(created_at) AS mx
                  FROM exchange_rate_refresh_logs
                  WHERE status <> 'success' AND {window}
                  GROUP BY source) m ON m.source = l.source AND m.mx = l.created_at
            WHERE l.status <> 'success'
        """)
        last_errors = {}
        for r in cursor.fetchall():
            last_errors.setdefault(r['source'], r['error_message'])
    finally:
        cursor.close()
        connection.close()

    sources = []
    for row in rows:
        source = row['source']
        bank, _, currency = source.rpartition('_')
        limit = max(threshold, CBSL_MIN_STALE_MINUTES) if bank == 'CBSL' else threshold

        success_age = row['success_age']
        attempt_age = row['attempt_age']
        streak = int(failures.get(source, 0))

        if success_age is None:
            stale, reason = True, 'never_succeeded'
        elif success_age > limit:
            stale = True
            # Attempts are still being made but keep failing, or nothing is running at all
            reason = 'failing' if attempt_age is not None and attempt_age <= limit else 'no_recent_runs'
        else:
            stale, reason = False, None

        sources.append({
            'source': source,
            'bank': bank,
            'currency': currency,
            'status': 'stale' if stale else 'healthy',
            'reason': reason,
            'threshold_minutes': limit,
            'last_success': row['last_success'].isoformat() if row['last_success'] else None,
            'last_success_age_minutes': success_age,
            'last_attempt': row['last_attempt'].isoformat() if row['last_attempt'] else None,
            'consecutive_failures': streak,
            'last_error': last_errors.get(source),
        })

    result = {
        'checked_at': datetime.now().isoformat(),
        'stale_threshold_minutes': threshold,
        'stale_count': sum(1 for s in sources if s['status'] == 'stale'),
        'sources': sources,
    }
    _cache['at'], _cache['data'] = time.monotonic(), result
    return result


def get_scraper_health_cached():
    """Like get_scraper_health() but reuses a result younger than CACHE_SECONDS."""
    if _cache['data'] is not None and time.monotonic() - _cache['at'] < CACHE_SECONDS:
        return _cache['data']
    return get_scraper_health()


# ---------------------------------------------------------------------------
# Alerting
# ---------------------------------------------------------------------------

def _format_age(minutes):
    if minutes is None:
        return 'never'
    if minutes < 60:
        return f"{minutes}m ago"
    if minutes < 2880:
        return f"{minutes // 60}h ago"
    return f"{minutes // 1440}d ago"


def _send_admin_ntfy(title, message, priority='high', tags='warning'):
    """Send a message to the admin ntfy topic. Returns True when delivered."""
    topic = (get_setting('ntfy_topic_admin', '') or '').strip()
    if not topic:
        logger.warning("Admin alert not sent (ntfy_topic_admin not configured): %s | %s", title, message)
        return False

    server = (get_setting('ntfy_server_url', '') or '').strip() or 'https://ntfy.sh'
    username = (get_setting('ntfy_username', '') or '').strip()
    password = (get_setting('ntfy_password', '') or '').strip()
    auth = (username, password) if username and password else None

    try:
        response = requests.post(
            f"{server.rstrip('/')}/{topic}",
            data=message.encode('utf-8'),
            headers={'Title': title, 'Priority': priority, 'Tags': tags},
            auth=auth,
            timeout=10,
        )
        if response.status_code == 200:
            return True
        logger.error("Admin ntfy alert failed: HTTP %s", response.status_code)
    except requests.RequestException as e:
        logger.error("Admin ntfy alert failed: %s", e)
    return False


def check_and_alert():
    """Evaluate scraper health and notify the admin about new / recovered problems.

    Called after every exchange-rate refresh.  A source is alerted once, then
    reminded every REALERT_AFTER_MINUTES while it stays stale, and a recovery
    notice is sent when it starts succeeding again.
    """
    health = get_scraper_health()
    stale = {s['source']: s for s in health['sources'] if s['status'] == 'stale'}
    healthy = {s['source'] for s in health['sources'] if s['status'] == 'healthy'}

    connection = get_db_connection()
    if not connection:
        return health
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT source, TIMESTAMPDIFF(MINUTE, alerted_at, NOW()) AS age
            FROM scraper_alert_state
        """)
        alerted = {r['source']: r['age'] for r in cursor.fetchall()}

        to_alert = [s for name, s in stale.items()
                    if name not in alerted or alerted[name] >= REALERT_AFTER_MINUTES]
        recovered = [name for name in alerted if name in healthy]

        if to_alert:
            lines = []
            for s in to_alert:
                detail = (s['last_error'] or '').strip().splitlines()[0][:120] if s['last_error'] else ''
                line = f"{s['source']}: last OK {_format_age(s['last_success_age_minutes'])}"
                if s['consecutive_failures']:
                    line += f", {s['consecutive_failures']} failed attempts"
                if detail:
                    line += f" ({detail})"
                lines.append(line)
            if _send_admin_ntfy(f"{len(to_alert)} exchange-rate scraper(s) stale", "\n".join(lines)):
                for s in to_alert:
                    cursor.execute("""
                        INSERT INTO scraper_alert_state (source, alerted_at, last_error)
                        VALUES (%s, NOW(), %s)
                        ON DUPLICATE KEY UPDATE alerted_at = NOW(), last_error = VALUES(last_error)
                    """, (s['source'], s['last_error']))

        if recovered:
            if _send_admin_ntfy("Exchange-rate scraper(s) recovered", "\n".join(recovered),
                                priority='default', tags='white_check_mark'):
                for name in recovered:
                    cursor.execute("DELETE FROM scraper_alert_state WHERE source = %s", (name,))

        connection.commit()
    except Error as e:
        logger.error("Scraper health alert bookkeeping failed: %s", e)
    finally:
        cursor.close()
        connection.close()

    return health


# ---------------------------------------------------------------------------
# Route handler
# ---------------------------------------------------------------------------

def get_scraper_health_api():
    from flask import request
    try:
        fresh = request.args.get('refresh') == '1'
        return jsonify(get_scraper_health() if fresh else get_scraper_health_cached()), 200
    except Exception as e:
        logger.error("Error computing scraper health: %s", e)
        return jsonify({'error': 'Failed to compute scraper health'}), 500
