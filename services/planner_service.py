"""
Planner service: category budgets, recurring transactions, bill reminders and
savings goals.

Conventions (same as the rest of the app):
  * ``credit`` is money going out (expense), ``debit`` is money coming in.
  * Categories are global; everything else here is per user.

Tables are created on first use (``CREATE TABLE IF NOT EXISTS``) so no manual
migration is needed.

Background work has no scheduler of its own.  ``run_scheduled_jobs()`` is called
after every exchange-rate refresh (driven by the existing cron), and recurring
rules are also caught up when a user opens the dashboard or the Planner.

Alerts go to a per-user ntfy topic (``planner_settings.ntfy_topic``) using the
server configured in ``app_settings``.  Without a topic, alerts are skipped and
the Planner page still shows the same information.
"""

import calendar
import logging
import math
import re
import threading
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from flask import request, jsonify, session
from mysql.connector import Error

from db import get_db_connection
from services.ntfy_service import send_ntfy_message

logger = logging.getLogger(__name__)

TOPIC_RE = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
FREQUENCIES = ('weekly', 'monthly', 'yearly')
MAX_RECURRING_CATCHUP = 200         # occurrences created per rule per run
BILL_STAGE_WINDOW_DAYS = 30         # stop reminding this long after the due date

# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------

_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS category_budgets (
        id            INT AUTO_INCREMENT PRIMARY KEY,
        user_id       INT NOT NULL,
        category_id   INT NOT NULL,
        monthly_limit DECIMAL(14,2) NOT NULL,
        alert_percent TINYINT UNSIGNED NOT NULL DEFAULT 80,
        created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_budget_user_cat (user_id, category_id)
    )""",
    """CREATE TABLE IF NOT EXISTS combined_budgets (
        user_id       INT NOT NULL PRIMARY KEY,
        alert_percent TINYINT UNSIGNED NOT NULL DEFAULT 80,
        created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS budget_alerts_sent (
        user_id     INT NOT NULL,
        category_id INT NOT NULL,
        year        SMALLINT NOT NULL,
        month       TINYINT NOT NULL,
        level       SMALLINT NOT NULL,
        sent_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, category_id, year, month, level)
    )""",
    """CREATE TABLE IF NOT EXISTS recurring_rules (
        id                INT AUTO_INCREMENT PRIMARY KEY,
        user_id           INT NOT NULL,
        description       VARCHAR(255) NOT NULL,
        category_id       INT NULL,
        payment_method_id INT NULL,
        kind              VARCHAR(7) NOT NULL DEFAULT 'expense',
        amount            DECIMAL(14,2) NOT NULL,
        notes             TEXT NULL,
        frequency         VARCHAR(8) NOT NULL DEFAULT 'monthly',
        interval_count    SMALLINT UNSIGNED NOT NULL DEFAULT 1,
        anchor_day        TINYINT UNSIGNED NOT NULL,
        start_date        DATE NOT NULL,
        end_date          DATE NULL,
        next_run          DATE NOT NULL,
        last_run          DATE NULL,
        due_offset_days   SMALLINT NULL,
        remind_days       TINYINT UNSIGNED NOT NULL DEFAULT 3,
        is_active         TINYINT(1) NOT NULL DEFAULT 1,
        created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        KEY idx_rec_user (user_id),
        KEY idx_rec_due (is_active, next_run)
    )""",
    """CREATE TABLE IF NOT EXISTS recurring_runs (
        rule_id         INT NOT NULL,
        occurrence_date DATE NOT NULL,
        transaction_id  INT NULL,
        PRIMARY KEY (rule_id, occurrence_date)
    )""",
    """CREATE TABLE IF NOT EXISTS transaction_due_dates (
        transaction_id INT NOT NULL PRIMARY KEY,
        user_id        INT NOT NULL,
        due_date       DATE NOT NULL,
        remind_days    TINYINT UNSIGNED NOT NULL DEFAULT 3,
        last_stage     TINYINT UNSIGNED NOT NULL DEFAULT 0,
        KEY idx_due_user (user_id, due_date)
    )""",
    """CREATE TABLE IF NOT EXISTS planner_settings (
        user_id    INT NOT NULL PRIMARY KEY,
        ntfy_topic VARCHAR(64) NULL
    )""",
    """CREATE TABLE IF NOT EXISTS savings_goals (
        id            INT AUTO_INCREMENT PRIMARY KEY,
        user_id       INT NOT NULL,
        name          VARCHAR(120) NOT NULL,
        target_amount DECIMAL(14,2) NOT NULL,
        target_date   DATE NULL,
        archived      TINYINT(1) NOT NULL DEFAULT 0,
        completed_notified TINYINT(1) NOT NULL DEFAULT 0,
        created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        KEY idx_goal_user (user_id)
    )""",
    """CREATE TABLE IF NOT EXISTS savings_contributions (
        id             INT AUTO_INCREMENT PRIMARY KEY,
        goal_id        INT NOT NULL,
        user_id        INT NOT NULL,
        amount         DECIMAL(14,2) NOT NULL,
        contributed_on DATE NOT NULL,
        note           VARCHAR(255) NULL,
        KEY idx_contrib_goal (goal_id)
    )""",
]

_schema_ready = False
_schema_lock = threading.Lock()


def ensure_schema():
    """Create the planner tables once per process. Returns True when ready."""
    global _schema_ready
    if _schema_ready:
        return True
    with _schema_lock:
        if _schema_ready:
            return True
        connection = get_db_connection()
        if not connection:
            return False
        cursor = connection.cursor()
        try:
            for ddl in _SCHEMA:
                cursor.execute(ddl)
            connection.commit()
            _schema_ready = True
        except Error as e:
            logger.error("Planner schema creation failed: %s", e)
        finally:
            cursor.close()
            connection.close()
    return _schema_ready


@contextmanager
def _db(dictionary=True):
    """Yield (connection, cursor); always closes both. Callers commit explicitly."""
    ensure_schema()
    connection = get_db_connection()
    if not connection:
        raise RuntimeError('Database connection failed')
    cursor = connection.cursor(dictionary=dictionary)
    try:
        yield connection, cursor
    finally:
        cursor.close()
        connection.close()


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

class ValidationError(ValueError):
    pass


def _money(value, field, allow_zero=False):
    try:
        amount = Decimal(str(value).replace(',', '').strip())
    except (InvalidOperation, ValueError, AttributeError):
        raise ValidationError(f'{field} must be a number')
    if amount < 0 or (amount == 0 and not allow_zero):
        raise ValidationError(f'{field} must be greater than 0')
    if amount >= Decimal('1000000000000'):
        raise ValidationError(f'{field} is too large')
    return amount.quantize(Decimal('0.01'))


def _date(value, field, required=True):
    if value in (None, ''):
        if required:
            raise ValidationError(f'{field} is required')
        return None
    try:
        return datetime.strptime(str(value)[:10], '%Y-%m-%d').date()
    except ValueError:
        raise ValidationError(f'{field} must be a date (YYYY-MM-DD)')


def _int(value, field, low, high, default=None):
    if value in (None, ''):
        if default is not None:
            return default
        raise ValidationError(f'{field} is required')
    try:
        number = int(value)
    except (ValueError, TypeError):
        raise ValidationError(f'{field} must be a whole number')
    if number < low or number > high:
        raise ValidationError(f'{field} must be between {low} and {high}')
    return number


def _clean(row):
    """Make a DB row JSON friendly."""
    out = {}
    for key, val in row.items():
        if isinstance(val, Decimal):
            out[key] = float(val)
        elif isinstance(val, (date, datetime)):
            out[key] = val.isoformat()
        else:
            out[key] = val
    return out


def _fmt_money(amount):
    return f"Rs {float(amount):,.2f}"


def _user_topic(cursor, user_id):
    cursor.execute("SELECT ntfy_topic FROM planner_settings WHERE user_id = %s", (user_id,))
    row = cursor.fetchone()
    if not row:
        return None
    topic = row['ntfy_topic'] if isinstance(row, dict) else row[0]
    return (topic or '').strip() or None


def _notify_user(user_id, title, message, priority='default', tags=''):
    """Send an ntfy push to the user's topic. Returns False when not configured/failed."""
    try:
        with _db() as (_, cursor):
            topic = _user_topic(cursor, user_id)
    except Exception as e:
        logger.error("Could not read ntfy topic for user %s: %s", user_id, e)
        return False
    if not topic:
        logger.info("Planner alert for user %s skipped (no ntfy topic): %s", user_id, title)
        return False
    return send_ntfy_message(topic, title, message, priority=priority, tags=tags)


def _in_background(func, *args):
    """Run slow follow-up work (notifications) without delaying the request."""
    def runner():
        try:
            func(*args)
        except Exception as e:  # never let a worker thread crash noisily
            logger.error("Planner background task %s failed: %s", func.__name__, e)
    threading.Thread(target=runner, daemon=True).start()


# --------------------------------------------------------------------------
# 1. Category budgets
# --------------------------------------------------------------------------

def _budget_status(spent, limit, alert_percent):
    pct = (float(spent) / float(limit) * 100) if limit else 0.0
    if pct >= 100:
        status = 'over'
    elif pct >= alert_percent:
        status = 'warning'
    else:
        status = 'ok'
    return round(pct, 1), status


def get_budgets(user_id, year, month):
    with _db() as (_, cursor):
        cursor.execute("""
            SELECT b.category_id, c.name AS category_name, b.monthly_limit, b.alert_percent,
                   COALESCE(s.spent, 0) AS spent
            FROM category_budgets b
            JOIN categories c ON c.id = b.category_id
            LEFT JOIN (SELECT t.category_id, SUM(t.credit) AS spent
                       FROM transactions t
                       JOIN monthly_records mr ON mr.id = t.monthly_record_id
                       WHERE mr.user_id = %s AND mr.year = %s AND mr.month = %s
                         AND t.category_id IS NOT NULL
                       GROUP BY t.category_id) s ON s.category_id = b.category_id
            WHERE b.user_id = %s
            ORDER BY c.name
        """, (user_id, year, month, user_id))
        rows = cursor.fetchall()

    result = []
    for row in rows:
        pct, status = _budget_status(row['spent'], row['monthly_limit'], row['alert_percent'])
        item = _clean(row)
        item.update(percent=pct, status=status,
                    remaining=float(row['monthly_limit']) - float(row['spent']))
        result.append(item)
    return result


DEFAULT_ALERT_PERCENT = 80
COMBINED_ALERT_KEY = 0      # category_id used in budget_alerts_sent for the combined budget


def _combined_figures(cursor, user_id, year, month):
    """(limit, spent) for the combined budget.

    limit = total debit (income) of the month; spent = all spending in categories
    that have no budget of their own (including uncategorised transactions)."""
    cursor.execute("""
        SELECT COALESCE(SUM(t.debit), 0) AS total_debit,
               COALESCE(SUM(CASE WHEN t.category_id IS NULL OR t.category_id NOT IN
                                      (SELECT category_id FROM category_budgets WHERE user_id = %s)
                                 THEN t.credit ELSE 0 END), 0) AS spent
        FROM transactions t JOIN monthly_records mr ON mr.id = t.monthly_record_id
        WHERE mr.user_id = %s AND mr.year = %s AND mr.month = %s
    """, (user_id, user_id, year, month))
    row = cursor.fetchone()
    return float(row['total_debit']), float(row['spent'])


def get_combined_budget(user_id, year, month):
    with _db() as (_, cursor):
        cursor.execute("SELECT alert_percent FROM combined_budgets WHERE user_id = %s", (user_id,))
        cfg = cursor.fetchone() or {'alert_percent': DEFAULT_ALERT_PERCENT}
        limit, spent = _combined_figures(cursor, user_id, year, month)
    pct, status = _budget_status(spent, limit, cfg['alert_percent'])
    return {'monthly_limit': limit, 'spent': spent, 'alert_percent': cfg['alert_percent'],
            'percent': pct, 'status': status, 'remaining': limit - spent}


def set_combined_budget(user_id, alert_percent):
    with _db() as (connection, cursor):
        cursor.execute("""
            INSERT INTO combined_budgets (user_id, alert_percent) VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE alert_percent = VALUES(alert_percent)
        """, (user_id, alert_percent))
        cursor.execute("DELETE FROM budget_alerts_sent WHERE user_id = %s AND category_id = %s",
                       (user_id, COMBINED_ALERT_KEY))
        connection.commit()


def delete_combined_budget(user_id):
    with _db() as (connection, cursor):
        cursor.execute("DELETE FROM combined_budgets WHERE user_id = %s", (user_id,))
        cursor.execute("DELETE FROM budget_alerts_sent WHERE user_id = %s AND category_id = %s",
                       (user_id, COMBINED_ALERT_KEY))
        connection.commit()


def _check_combined_budget(user_id, year, month):
    """Alert when combined (un-budgeted) spending crosses its warning/100% level."""
    with _db() as (connection, cursor):
        cursor.execute("SELECT alert_percent FROM combined_budgets WHERE user_id = %s", (user_id,))
        cfg = cursor.fetchone() or {'alert_percent': DEFAULT_ALERT_PERCENT}
        limit, spent = _combined_figures(cursor, user_id, year, month)
        if limit <= 0:
            return
        pct = spent / limit * 100
        crossed = [lv for lv in (cfg['alert_percent'], 100) if pct >= lv]
        if not crossed:
            return
        level = max(crossed)
        cursor.execute("""
            INSERT IGNORE INTO budget_alerts_sent (user_id, category_id, year, month, level)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, COMBINED_ALERT_KEY, year, month, level))
        first_time = cursor.rowcount == 1
        if level == 100:
            cursor.execute("""
                INSERT IGNORE INTO budget_alerts_sent (user_id, category_id, year, month, level)
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, COMBINED_ALERT_KEY, year, month, cfg['alert_percent']))
        connection.commit()
        if not first_time:
            return

    over = level >= 100
    title = f"{'Over budget' if over else 'Budget warning'}: Combined categories"
    message = (f"Other categories: {_fmt_money(spent)} of {_fmt_money(limit)} "
               f"({pct:.0f}%) of this month's total debit")
    _notify_user(user_id, title, message,
                 priority='high' if over else 'default',
                 tags='rotating_light' if over else 'warning')


def set_budget(user_id, category_id, limit, alert_percent):
    with _db() as (connection, cursor):
        cursor.execute("SELECT type FROM categories WHERE id = %s", (category_id,))
        category = cursor.fetchone()
        if not category:
            raise ValidationError('Category not found')
        if category['type'] != 'expense':
            raise ValidationError('Budgets can only be set on expense categories')
        cursor.execute("""
            INSERT INTO category_budgets (user_id, category_id, monthly_limit, alert_percent)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE monthly_limit = VALUES(monthly_limit),
                                    alert_percent = VALUES(alert_percent)
        """, (user_id, category_id, limit, alert_percent))
        # A changed limit/threshold deserves fresh alerts for the month
        cursor.execute("DELETE FROM budget_alerts_sent WHERE user_id = %s AND category_id = %s",
                       (user_id, category_id))
        connection.commit()


def delete_budget(user_id, category_id):
    with _db() as (connection, cursor):
        cursor.execute("DELETE FROM category_budgets WHERE user_id = %s AND category_id = %s",
                       (user_id, category_id))
        cursor.execute("DELETE FROM budget_alerts_sent WHERE user_id = %s AND category_id = %s",
                       (user_id, category_id))
        connection.commit()
        return cursor.rowcount >= 0


def _check_budget(user_id, transaction_id):
    """Alert when the transaction's category crossed its warning/over-budget level."""
    with _db() as (connection, cursor):
        cursor.execute("""
            SELECT t.category_id, t.credit, mr.year, mr.month
            FROM transactions t JOIN monthly_records mr ON mr.id = t.monthly_record_id
            WHERE t.id = %s AND mr.user_id = %s
        """, (transaction_id, user_id))
        tx = cursor.fetchone()
        if not tx:
            return
        today = date.today()
        if (tx['year'], tx['month']) != (today.year, today.month):
            return                                    # only the running month alerts
        _check_combined_budget(user_id, tx['year'], tx['month'])
        if not tx['category_id'] or not tx['credit']:
            return

        cursor.execute("""
            SELECT b.monthly_limit, b.alert_percent, c.name
            FROM category_budgets b JOIN categories c ON c.id = b.category_id
            WHERE b.user_id = %s AND b.category_id = %s
        """, (user_id, tx['category_id']))
        budget = cursor.fetchone()
        if not budget:
            return

        cursor.execute("""
            SELECT COALESCE(SUM(t.credit), 0) AS spent
            FROM transactions t JOIN monthly_records mr ON mr.id = t.monthly_record_id
            WHERE mr.user_id = %s AND mr.year = %s AND mr.month = %s AND t.category_id = %s
        """, (user_id, tx['year'], tx['month'], tx['category_id']))
        spent = cursor.fetchone()['spent']

        pct = float(spent) / float(budget['monthly_limit']) * 100
        crossed = [lv for lv in (budget['alert_percent'], 100) if pct >= lv]
        if not crossed:
            return
        level = max(crossed)
        cursor.execute("""
            INSERT IGNORE INTO budget_alerts_sent (user_id, category_id, year, month, level)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, tx['category_id'], tx['year'], tx['month'], level))
        first_time = cursor.rowcount == 1
        if level == 100:        # also mark the lower level so it never fires after going over
            cursor.execute("""
                INSERT IGNORE INTO budget_alerts_sent (user_id, category_id, year, month, level)
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, tx['category_id'], tx['year'], tx['month'], budget['alert_percent']))
        connection.commit()
        if not first_time:
            return

    over = level >= 100
    title = f"{'Over budget' if over else 'Budget warning'}: {budget['name']}"
    message = (f"{budget['name']}: {_fmt_money(spent)} of {_fmt_money(budget['monthly_limit'])} "
               f"({pct:.0f}%) this month")
    _notify_user(user_id, title, message,
                 priority='high' if over else 'default',
                 tags='rotating_light' if over else 'warning')


def after_transaction_change(user_id, transaction_id):
    """Hook for transaction create/update: check budgets without blocking the request."""
    if user_id and transaction_id:
        _in_background(_check_budget, user_id, transaction_id)


# --------------------------------------------------------------------------
# 2. Recurring transactions
# --------------------------------------------------------------------------

def _add_months(d, months, anchor_day):
    index = d.year * 12 + (d.month - 1) + months
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(anchor_day, calendar.monthrange(year, month)[1]))


def next_occurrence(frequency, interval, anchor_day, current):
    if frequency == 'weekly':
        return current + timedelta(days=7 * interval)
    if frequency == 'yearly':
        return _add_months(current, 12 * interval, anchor_day)
    return _add_months(current, interval, anchor_day)


def occurrence_number(frequency, interval, start, occurrence):
    """1-based position of *occurrence* in the schedule that begins at *start*."""
    if frequency == 'weekly':
        return (occurrence - start).days // (7 * interval) + 1
    months = (occurrence.year - start.year) * 12 + occurrence.month - start.month
    step = 12 * interval if frequency == 'yearly' else interval
    return months // step + 1


def occurrence_total(rule):
    """Total occurrences up to end_date, or None when the rule is open-ended."""
    if not rule['end_date']:
        return None
    count, current = 0, rule['start_date']
    while current <= rule['end_date'] and count < 5000:
        count += 1
        current = next_occurrence(rule['frequency'], rule['interval_count'],
                                  rule['anchor_day'], current)
    return count


def numbered_description(rule, occurrence):
    number = occurrence_number(rule['frequency'], rule['interval_count'],
                               rule['start_date'], occurrence)
    total = occurrence_total(rule)
    label = f"({number}/{total})" if total else f"#{number}"
    return f"{rule['description']} {label}"[:255]


def _rule_from_payload(data):
    description = (data.get('description') or '').strip()
    if not description:
        raise ValidationError('Description is required')
    if len(description) > 255:
        raise ValidationError('Description is too long')

    kind = data.get('kind', 'expense')
    if kind not in ('expense', 'income'):
        raise ValidationError("Type must be 'expense' or 'income'")
    frequency = data.get('frequency', 'monthly')
    if frequency not in FREQUENCIES:
        raise ValidationError('Frequency must be weekly, monthly or yearly')

    start = _date(data.get('start_date'), 'Start date')
    end = _date(data.get('end_date'), 'End date', required=False)
    if end and end < start:
        raise ValidationError('End date must not be before the start date')

    due_offset = data.get('due_offset_days')
    due_offset = None if due_offset in (None, '') else _int(due_offset, 'Due days after', 0, 365)

    return {
        'description': description,
        'category_id': _int(data.get('category_id'), 'Category', 1, 2**31 - 1, default=0) or None,
        'payment_method_id': _int(data.get('payment_method_id'), 'Payment method', 1, 2**31 - 1, default=0) or None,
        'kind': kind,
        'amount': _money(data.get('amount'), 'Amount'),
        'notes': (data.get('notes') or '').strip() or None,
        'frequency': frequency,
        'interval_count': _int(data.get('interval_count'), 'Repeat every', 1, 24, default=1),
        'anchor_day': start.day,
        'start_date': start,
        'end_date': end,
        'due_offset_days': due_offset,
        'remind_days': _int(data.get('remind_days'), 'Remind days', 0, 30, default=3),
    }


def list_rules(user_id):
    with _db() as (_, cursor):
        cursor.execute("""
            SELECT r.*, c.name AS category_name, pm.name AS payment_method_name
            FROM recurring_rules r
            LEFT JOIN categories c ON c.id = r.category_id
            LEFT JOIN payment_methods pm ON pm.id = r.payment_method_id
            WHERE r.user_id = %s
            ORDER BY r.is_active DESC, r.next_run
        """, (user_id,))
        return [_clean(r) for r in cursor.fetchall()]


def create_rule(user_id, data):
    rule = _rule_from_payload(data)
    with _db() as (connection, cursor):
        cursor.execute("""
            INSERT INTO recurring_rules
                (user_id, description, category_id, payment_method_id, kind, amount, notes,
                 frequency, interval_count, anchor_day, start_date, end_date, next_run,
                 due_offset_days, remind_days)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (user_id, rule['description'], rule['category_id'], rule['payment_method_id'],
              rule['kind'], rule['amount'], rule['notes'], rule['frequency'],
              rule['interval_count'], rule['anchor_day'], rule['start_date'], rule['end_date'],
              rule['start_date'], rule['due_offset_days'], rule['remind_days']))
        connection.commit()
        return cursor.lastrowid


def update_rule(user_id, rule_id, data):
    rule = _rule_from_payload(data)
    is_active = 1 if data.get('is_active', True) else 0
    with _db() as (connection, cursor):
        cursor.execute("SELECT frequency, interval_count, start_date, next_run "
                       "FROM recurring_rules WHERE id = %s AND user_id = %s", (rule_id, user_id))
        existing = cursor.fetchone()
        if not existing:
            return False
        # Schedule changes restart from the (possibly new) start date; otherwise keep position.
        schedule_changed = (existing['frequency'] != rule['frequency']
                            or existing['interval_count'] != rule['interval_count']
                            or existing['start_date'] != rule['start_date'])
        next_run = rule['start_date'] if schedule_changed else existing['next_run']
        cursor.execute("""
            UPDATE recurring_rules
               SET description=%s, category_id=%s, payment_method_id=%s, kind=%s, amount=%s,
                   notes=%s, frequency=%s, interval_count=%s, anchor_day=%s, start_date=%s,
                   end_date=%s, next_run=%s, due_offset_days=%s, remind_days=%s, is_active=%s
             WHERE id=%s AND user_id=%s
        """, (rule['description'], rule['category_id'], rule['payment_method_id'], rule['kind'],
              rule['amount'], rule['notes'], rule['frequency'], rule['interval_count'],
              rule['anchor_day'], rule['start_date'], rule['end_date'], next_run,
              rule['due_offset_days'], rule['remind_days'], is_active, rule_id, user_id))
        connection.commit()
        return True


def set_rule_active(user_id, rule_id, active):
    with _db() as (connection, cursor):
        cursor.execute("UPDATE recurring_rules SET is_active=%s WHERE id=%s AND user_id=%s",
                       (1 if active else 0, rule_id, user_id))
        connection.commit()
        return cursor.rowcount > 0


def delete_rule(user_id, rule_id):
    """Remove the rule. Transactions it already created are kept."""
    with _db() as (connection, cursor):
        cursor.execute("DELETE FROM recurring_rules WHERE id=%s AND user_id=%s", (rule_id, user_id))
        deleted = cursor.rowcount > 0
        if deleted:
            cursor.execute("DELETE FROM recurring_runs WHERE rule_id=%s", (rule_id,))
        connection.commit()
        return deleted


def _create_from_rule(connection, cursor, rule, occurrence):
    """Insert one transaction for *occurrence*. Returns its id, or None if already created."""
    from services.transaction_service import apply_percentage_markup   # avoid import cycle

    cursor.execute("INSERT IGNORE INTO recurring_runs (rule_id, occurrence_date) VALUES (%s, %s)",
                   (rule['id'], occurrence))
    if cursor.rowcount == 0:
        return None                      # another worker already created this occurrence

    cursor.execute("""
        INSERT INTO monthly_records (user_id, year, month, month_name)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id), updated_at = CURRENT_TIMESTAMP
    """, (rule['user_id'], occurrence.year, occurrence.month, calendar.month_name[occurrence.month]))
    monthly_record_id = cursor.lastrowid

    amount = Decimal(str(rule['amount']))
    if rule['category_id'] or rule['payment_method_id']:
        amount = apply_percentage_markup(amount, rule['category_id'], rule['payment_method_id'],
                                         rule['user_id'], connection)
    debit = amount if rule['kind'] == 'income' else None
    credit = amount if rule['kind'] == 'expense' else None

    cursor.execute("UPDATE transactions SET display_order = display_order + 1 "
                   "WHERE monthly_record_id = %s", (monthly_record_id,))
    cursor.execute("""
        INSERT INTO transactions
            (monthly_record_id, description, category_id, debit, credit, transaction_date, notes,
             display_order, bill_content, attachments, payment_method_id, is_paid, paid_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,1,NULL,NULL,%s,FALSE,NULL)
    """, (monthly_record_id, numbered_description(rule, occurrence), rule['category_id'], debit, credit,
          occurrence, rule['notes'], rule['payment_method_id']))
    transaction_id = cursor.lastrowid

    cursor.execute("UPDATE recurring_runs SET transaction_id=%s WHERE rule_id=%s AND occurrence_date=%s",
                   (transaction_id, rule['id'], occurrence))

    if rule['due_offset_days'] is not None and rule['kind'] == 'expense':
        cursor.execute("""
            INSERT INTO transaction_due_dates (transaction_id, user_id, due_date, remind_days)
            VALUES (%s, %s, %s, %s)
        """, (transaction_id, rule['user_id'], occurrence + timedelta(days=rule['due_offset_days']),
              rule['remind_days']))
    return transaction_id


def process_due_rules(user_id=None, today=None):
    """Create the transactions of every recurring rule that is due. Returns how many were created."""
    today = today or date.today()
    created = 0
    created_ids = []

    with _db() as (_, cursor):
        # Rules with an end date are generated in full (future dates included)
        sql = "SELECT * FROM recurring_rules WHERE is_active = 1 AND next_run <= COALESCE(end_date, %s)"
        params = [today]
        if user_id:
            sql += " AND user_id = %s"
            params.append(user_id)
        cursor.execute(sql, params)
        rules = cursor.fetchall()

    for rule in rules:
        try:
            with _db() as (connection, cursor):
                occurrence = rule['next_run']
                limit = rule['end_date'] or today
                steps = 0
                while occurrence <= limit and steps < MAX_RECURRING_CATCHUP:
                    if rule['end_date'] and occurrence > rule['end_date']:
                        break
                    try:
                        tx_id = _create_from_rule(connection, cursor, rule, occurrence)
                        following = next_occurrence(rule['frequency'], rule['interval_count'],
                                                    rule['anchor_day'], occurrence)
                        cursor.execute("UPDATE recurring_rules SET next_run=%s, last_run=%s WHERE id=%s",
                                       (following, occurrence, rule['id']))
                        connection.commit()
                    except Error:
                        connection.rollback()
                        raise
                    if tx_id:
                        created += 1
                        created_ids.append((rule['user_id'], tx_id))
                    occurrence = following
                    steps += 1
                if rule['end_date'] and occurrence > rule['end_date']:
                    cursor.execute("UPDATE recurring_rules SET is_active=0 WHERE id=%s", (rule['id'],))
                    connection.commit()
        except Exception as e:
            logger.error("Recurring rule %s failed: %s", rule['id'], e)

    for uid, tx_id in created_ids:
        after_transaction_change(uid, tx_id)
    if created:
        logger.info("Recurring transactions created: %s", created)
    return created


def catch_up_for_user(user_id):
    """Cheap check used when a user opens the dashboard/Planner."""
    try:
        with _db() as (_, cursor):
            cursor.execute("SELECT 1 FROM recurring_rules WHERE user_id=%s AND is_active=1 "
                           "AND next_run <= COALESCE(end_date, %s) LIMIT 1", (user_id, date.today()))
            if not cursor.fetchone():
                return 0
        return process_due_rules(user_id=user_id)
    except Exception as e:
        logger.error("Recurring catch-up failed for user %s: %s", user_id, e)
        return 0


# --------------------------------------------------------------------------
# 3. Bills / due dates
# --------------------------------------------------------------------------

def save_due_date(cursor, user_id, transaction_id, data):
    """Create/update/clear the due date of a transaction from a create/update payload.

    Leaves the due date alone when the payload has no ``due_date`` key, so older
    clients (e.g. the mobile page) never wipe it. Runs inside the caller's
    transaction; the caller commits.
    """
    if not data or 'due_date' not in data:
        return
    ensure_schema()
    try:
        raw = data.get('due_date')
        if not raw:
            cursor.execute("DELETE FROM transaction_due_dates WHERE transaction_id=%s AND user_id=%s",
                           (transaction_id, user_id))
            return
        due = _date(raw, 'Due date')
        remind = _int(data.get('remind_days'), 'Remind days', 0, 30, default=3)
        cursor.execute("""
            INSERT INTO transaction_due_dates (transaction_id, user_id, due_date, remind_days)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                last_stage  = IF(due_date <> VALUES(due_date) OR remind_days <> VALUES(remind_days),
                                 0, last_stage),
                due_date    = VALUES(due_date),
                remind_days = VALUES(remind_days)
        """, (transaction_id, user_id, due, remind))
    except (ValidationError, Error) as e:
        logger.warning("Due date not saved for transaction %s: %s", transaction_id, e)


def attach_due_dates(cursor, rows):
    """Add due_date/remind_days to a list of transaction dicts (one query)."""
    if not rows:
        return
    ensure_schema()
    ids = [r['id'] for r in rows if r.get('id') is not None]
    found = {}
    try:
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            cursor.execute("SELECT transaction_id, due_date, remind_days FROM transaction_due_dates "
                           f"WHERE transaction_id IN ({','.join(['%s'] * len(chunk))})", chunk)
            for row in cursor.fetchall():
                found[row['transaction_id']] = row
    except Error as e:
        logger.warning("Could not load due dates: %s", e)
    for r in rows:
        d = found.get(r.get('id'))
        r['due_date'] = d['due_date'].isoformat() if d else None
        r['remind_days'] = d['remind_days'] if d else None


def _bill_state(days_left, remind_days):
    if days_left < 0:
        return 'overdue'
    if days_left == 0:
        return 'today'
    if days_left <= remind_days:
        return 'soon'
    return 'upcoming'


def list_bills(user_id):
    with _db() as (_, cursor):
        cursor.execute("""
            SELECT t.id AS transaction_id, t.description, t.credit, t.debit, t.payment_method_id,
                   d.due_date, d.remind_days,
                   DATEDIFF(d.due_date, CURDATE()) AS days_left,
                   c.name AS category_name, pm.name AS payment_method_name
            FROM transaction_due_dates d
            JOIN transactions t ON t.id = d.transaction_id
            JOIN monthly_records mr ON mr.id = t.monthly_record_id AND mr.user_id = %s
            LEFT JOIN categories c ON c.id = t.category_id
            LEFT JOIN payment_methods pm ON pm.id = t.payment_method_id
            WHERE d.user_id = %s AND COALESCE(t.is_paid, 0) = 0
            ORDER BY d.due_date, t.id
            LIMIT 200
        """, (user_id, user_id))
        rows = cursor.fetchall()
    bills = []
    for row in rows:
        item = _clean(row)
        item['amount'] = float(row['credit'] or row['debit'] or 0)
        item['is_income'] = not row['credit']
        item['state'] = _bill_state(row['days_left'], row['remind_days'])
        bills.append(item)
    return bills


def clear_due_date(user_id, transaction_id):
    with _db() as (connection, cursor):
        cursor.execute("DELETE FROM transaction_due_dates WHERE transaction_id=%s AND user_id=%s",
                       (transaction_id, user_id))
        connection.commit()
        return cursor.rowcount > 0


def _bill_stage(days_left, remind_days):
    """0 = nothing to say yet; higher = more urgent. Reminders fire when the stage rises."""
    if days_left <= -7:
        return 5
    if days_left <= -3:
        return 4
    if days_left <= 0:
        return 3
    if days_left <= 1:
        return 2
    if days_left <= remind_days:
        return 1
    return 0


def _describe_due(days_left, due_date):
    if days_left < 0:
        n = -days_left
        return f"overdue by {n} day{'s' if n != 1 else ''}"
    if days_left == 0:
        return "due today"
    if days_left == 1:
        return "due tomorrow"
    return f"due in {days_left} days ({due_date})"


def send_bill_reminders():
    """Push reminders for unpaid bills. Returns the number of reminder lines sent."""
    with _db() as (_, cursor):
        cursor.execute("""
            SELECT d.transaction_id, d.user_id, d.due_date, d.remind_days, d.last_stage,
                   t.description, COALESCE(t.credit, t.debit) AS amount,
                   DATEDIFF(d.due_date, CURDATE()) AS days_left
            FROM transaction_due_dates d
            JOIN transactions t ON t.id = d.transaction_id
            WHERE COALESCE(t.is_paid, 0) = 0
              AND DATEDIFF(d.due_date, CURDATE()) <= d.remind_days
              AND DATEDIFF(d.due_date, CURDATE()) >= %s
        """, (-BILL_STAGE_WINDOW_DAYS,))
        rows = cursor.fetchall()

    per_user = {}
    for row in rows:
        stage = _bill_stage(row['days_left'], row['remind_days'])
        if stage > row['last_stage']:
            per_user.setdefault(row['user_id'], []).append((row, stage))

    sent = 0
    for user_id, items in per_user.items():
        lines = [f"{r['description']} - {_fmt_money(r['amount'])} {_describe_due(r['days_left'], r['due_date'])}"
                 for r, _ in items]
        urgent = any(r['days_left'] <= 1 for r, _ in items)
        title = f"{len(items)} bill{'s' if len(items) != 1 else ''} to pay"
        if _notify_user(user_id, title, "\n".join(lines),
                        priority='high' if urgent else 'default',
                        tags='alarm_clock' if urgent else 'bell'):
            with _db() as (connection, cursor):
                for r, stage in items:
                    cursor.execute("UPDATE transaction_due_dates SET last_stage=%s WHERE transaction_id=%s",
                                   (stage, r['transaction_id']))
                connection.commit()
            sent += len(items)
    return sent


# --------------------------------------------------------------------------
# 4. Savings goals
# --------------------------------------------------------------------------

def _goal_view(goal, contributions, today=None):
    today = today or date.today()
    target = float(goal['target_amount'])
    saved = round(sum(float(c['amount']) for c in contributions), 2)
    remaining = max(target - saved, 0.0)
    view = _clean(goal)
    view.update(
        saved=saved,
        remaining=round(remaining, 2),
        percent=round(min(saved / target * 100, 100), 1) if target else 0,
        completed=saved >= target,
        monthly_needed=None,
        months_left=None,
        overdue=False,
        contributions=[_clean(c) for c in contributions],
    )
    target_date = goal['target_date']
    if target_date and remaining > 0:
        if target_date < today:
            view['overdue'] = True
        else:
            months_left = max(1, math.ceil((target_date - today).days / 30.44))
            view['months_left'] = months_left
            view['monthly_needed'] = round(remaining / months_left, 2)
    return view


def list_goals(user_id, include_archived=False):
    with _db() as (_, cursor):
        cursor.execute("SELECT * FROM savings_goals WHERE user_id=%s"
                       + ("" if include_archived else " AND archived=0")
                       + " ORDER BY archived, target_date IS NULL, target_date, id", (user_id,))
        goals = cursor.fetchall()
        by_goal = {g['id']: [] for g in goals}
        if by_goal:
            cursor.execute("SELECT id, goal_id, amount, contributed_on, note FROM savings_contributions "
                           f"WHERE user_id=%s AND goal_id IN ({','.join(['%s'] * len(by_goal))}) "
                           "ORDER BY contributed_on DESC, id DESC", [user_id, *by_goal])
            for c in cursor.fetchall():
                by_goal[c['goal_id']].append(c)
    return [_goal_view(g, by_goal[g['id']]) for g in goals]


def _goal_payload(data, partial=False):
    out = {}
    if not partial or 'name' in data:
        name = (data.get('name') or '').strip()
        if not name:
            raise ValidationError('Name is required')
        if len(name) > 120:
            raise ValidationError('Name is too long')
        out['name'] = name
    if not partial or 'target_amount' in data:
        out['target_amount'] = _money(data.get('target_amount'), 'Target amount')
    if not partial or 'target_date' in data:
        out['target_date'] = _date(data.get('target_date'), 'Target date', required=False)
    if 'archived' in data:
        out['archived'] = 1 if data.get('archived') else 0
    return out


def create_goal(user_id, data):
    goal = _goal_payload(data)
    with _db() as (connection, cursor):
        cursor.execute("INSERT INTO savings_goals (user_id, name, target_amount, target_date) "
                       "VALUES (%s, %s, %s, %s)",
                       (user_id, goal['name'], goal['target_amount'], goal['target_date']))
        connection.commit()
        return cursor.lastrowid


def update_goal(user_id, goal_id, data):
    changes = _goal_payload(data, partial=True)
    if not changes:
        raise ValidationError('Nothing to update')
    if 'target_amount' in changes:
        changes['completed_notified'] = 0       # allow the "goal reached" push again
    assignments = ', '.join(f"{col}=%s" for col in changes)
    with _db() as (connection, cursor):
        cursor.execute(f"UPDATE savings_goals SET {assignments} WHERE id=%s AND user_id=%s",
                       [*changes.values(), goal_id, user_id])
        connection.commit()
        cursor.execute("SELECT 1 FROM savings_goals WHERE id=%s AND user_id=%s", (goal_id, user_id))
        return cursor.fetchone() is not None


def delete_goal(user_id, goal_id):
    with _db() as (connection, cursor):
        cursor.execute("DELETE FROM savings_goals WHERE id=%s AND user_id=%s", (goal_id, user_id))
        deleted = cursor.rowcount > 0
        if deleted:
            cursor.execute("DELETE FROM savings_contributions WHERE goal_id=%s AND user_id=%s",
                           (goal_id, user_id))
        connection.commit()
        return deleted


def add_contribution(user_id, goal_id, data):
    """Add money to (or, with a negative amount, take money out of) a goal."""
    raw = str(data.get('amount') or '').strip()
    negative = raw.startswith('-')
    amount = _money(raw.lstrip('-'), 'Amount')
    if negative:
        amount = -amount
    when = _date(data.get('contributed_on') or date.today().isoformat(), 'Date')
    note = (data.get('note') or '').strip()[:255] or None

    with _db() as (connection, cursor):
        cursor.execute("SELECT * FROM savings_goals WHERE id=%s AND user_id=%s", (goal_id, user_id))
        goal = cursor.fetchone()
        if not goal:
            return None
        cursor.execute("SELECT COALESCE(SUM(amount),0) AS saved FROM savings_contributions "
                       "WHERE goal_id=%s AND user_id=%s", (goal_id, user_id))
        saved = cursor.fetchone()['saved']
        if saved + amount < 0:
            raise ValidationError('That would take the saved amount below zero')
        cursor.execute("INSERT INTO savings_contributions (goal_id, user_id, amount, contributed_on, note) "
                       "VALUES (%s, %s, %s, %s, %s)", (goal_id, user_id, amount, when, note))
        contribution_id = cursor.lastrowid
        reached = (saved + amount >= goal['target_amount'] and not goal['completed_notified'])
        if reached:
            cursor.execute("UPDATE savings_goals SET completed_notified=1 WHERE id=%s", (goal_id,))
        connection.commit()

    if reached:
        _in_background(_notify_user, user_id, f"Goal reached: {goal['name']}",
                       f"You have saved {_fmt_money(saved + amount)} of {_fmt_money(goal['target_amount'])}.",
                       'default', 'tada')
    return contribution_id


def delete_contribution(user_id, goal_id, contribution_id):
    with _db() as (connection, cursor):
        cursor.execute("DELETE FROM savings_contributions WHERE id=%s AND goal_id=%s AND user_id=%s",
                       (contribution_id, goal_id, user_id))
        connection.commit()
        return cursor.rowcount > 0


# --------------------------------------------------------------------------
# Settings (ntfy topic)
# --------------------------------------------------------------------------

def get_settings(user_id):
    with _db() as (_, cursor):
        return {'ntfy_topic': _user_topic(cursor, user_id) or ''}


def save_settings(user_id, data):
    topic = (data.get('ntfy_topic') or '').strip()
    if topic and not TOPIC_RE.match(topic):
        raise ValidationError('Topic may only contain letters, numbers, "-" and "_" (max 64 characters)')
    with _db() as (connection, cursor):
        cursor.execute("""
            INSERT INTO planner_settings (user_id, ntfy_topic) VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE ntfy_topic = VALUES(ntfy_topic)
        """, (user_id, topic or None))
        connection.commit()


# --------------------------------------------------------------------------
# Scheduled entry point (called after each exchange-rate refresh)
# --------------------------------------------------------------------------

def run_scheduled_jobs():
    for name, job in (('recurring transactions', process_due_rules),
                      ('bill reminders', send_bill_reminders)):
        try:
            job()
        except Exception as e:
            logger.error("Planner job '%s' failed: %s", name, e)


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

def register_planner_routes(app, login_required):
    ensure_schema()       # create tables at startup; retried lazily if the DB is not up yet

    def ok(payload=None, status=200):
        return jsonify(payload if payload is not None else {'ok': True}), status

    def not_found(what):
        return jsonify({'error': f'{what} not found'}), 404

    def body():
        return request.get_json(silent=True) or {}

    uid = lambda: session['user_id']

    # ---- budgets -----------------------------------------------------------
    @app.route('/api/planner/budgets', methods=['GET'])
    @login_required
    def planner_get_budgets():
        today = date.today()
        year = request.args.get('year', today.year, type=int)
        month = request.args.get('month', today.month, type=int)
        if not 1 <= month <= 12:
            return jsonify({'error': 'Invalid month'}), 400
        try:
            return ok({'year': year, 'month': month, 'budgets': get_budgets(uid(), year, month),
                       'combined': get_combined_budget(uid(), year, month)})
        except Exception as e:
            logger.error("Planner budgets failed: %s", e)
            return jsonify({'error': 'Could not load budgets'}), 500

    @app.route('/api/planner/budgets/combined', methods=['PUT'])
    @login_required
    def planner_set_combined_budget():
        try:
            alert = _int(body().get('alert_percent'), 'Alert at', 50, 99, default=80)
            set_combined_budget(uid(), alert)
            return ok()
        except ValidationError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error("Planner set combined budget failed: %s", e)
            return jsonify({'error': 'Could not save combined budget'}), 500

    @app.route('/api/planner/budgets/combined', methods=['DELETE'])
    @login_required
    def planner_delete_combined_budget():
        try:
            delete_combined_budget(uid())
            return ok()
        except Exception as e:
            logger.error("Planner delete combined budget failed: %s", e)
            return jsonify({'error': 'Could not delete combined budget'}), 500

    @app.route('/api/planner/budgets/<int:category_id>', methods=['PUT'])
    @login_required
    def planner_set_budget(category_id):
        data = body()
        try:
            limit = _money(data.get('monthly_limit'), 'Monthly limit')
            alert = _int(data.get('alert_percent'), 'Alert at', 50, 99, default=80)
            set_budget(uid(), category_id, limit, alert)
            return ok()
        except ValidationError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error("Planner set budget failed: %s", e)
            return jsonify({'error': 'Could not save budget'}), 500

    @app.route('/api/planner/budgets/<int:category_id>', methods=['DELETE'])
    @login_required
    def planner_delete_budget(category_id):
        try:
            delete_budget(uid(), category_id)
            return ok()
        except Exception as e:
            logger.error("Planner delete budget failed: %s", e)
            return jsonify({'error': 'Could not delete budget'}), 500

    # ---- recurring ---------------------------------------------------------
    @app.route('/api/planner/recurring', methods=['GET'])
    @login_required
    def planner_list_recurring():
        try:
            catch_up_for_user(uid())
            return ok(list_rules(uid()))
        except Exception as e:
            logger.error("Planner recurring list failed: %s", e)
            return jsonify({'error': 'Could not load recurring transactions'}), 500

    @app.route('/api/planner/recurring', methods=['POST'])
    @login_required
    def planner_create_recurring():
        try:
            rule_id = create_rule(uid(), body())
            created = catch_up_for_user(uid())       # a past start date back-fills right away
            return ok({'id': rule_id, 'created_now': created}, 201)
        except ValidationError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error("Planner create recurring failed: %s", e)
            return jsonify({'error': 'Could not save recurring transaction'}), 500

    @app.route('/api/planner/recurring/<int:rule_id>', methods=['PUT'])
    @login_required
    def planner_update_recurring(rule_id):
        try:
            if not update_rule(uid(), rule_id, body()):
                return not_found('Recurring transaction')
            created = catch_up_for_user(uid())
            return ok({'created_now': created})
        except ValidationError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error("Planner update recurring failed: %s", e)
            return jsonify({'error': 'Could not update recurring transaction'}), 500

    @app.route('/api/planner/recurring/<int:rule_id>/active', methods=['PUT'])
    @login_required
    def planner_toggle_recurring(rule_id):
        try:
            if not set_rule_active(uid(), rule_id, bool(body().get('is_active'))):
                return not_found('Recurring transaction')
            return ok()
        except Exception as e:
            logger.error("Planner toggle recurring failed: %s", e)
            return jsonify({'error': 'Could not update recurring transaction'}), 500

    @app.route('/api/planner/recurring/<int:rule_id>', methods=['DELETE'])
    @login_required
    def planner_delete_recurring(rule_id):
        try:
            if not delete_rule(uid(), rule_id):
                return not_found('Recurring transaction')
            return ok()
        except Exception as e:
            logger.error("Planner delete recurring failed: %s", e)
            return jsonify({'error': 'Could not delete recurring transaction'}), 500

    # ---- bills -------------------------------------------------------------
    @app.route('/api/planner/bills', methods=['GET'])
    @login_required
    def planner_list_bills():
        try:
            return ok(list_bills(uid()))
        except Exception as e:
            logger.error("Planner bills failed: %s", e)
            return jsonify({'error': 'Could not load bills'}), 500

    @app.route('/api/planner/bills/<int:transaction_id>', methods=['DELETE'])
    @login_required
    def planner_clear_bill(transaction_id):
        try:
            clear_due_date(uid(), transaction_id)
            return ok()
        except Exception as e:
            logger.error("Planner clear due date failed: %s", e)
            return jsonify({'error': 'Could not remove the reminder'}), 500

    # ---- goals -------------------------------------------------------------
    @app.route('/api/planner/goals', methods=['GET'])
    @login_required
    def planner_list_goals():
        try:
            return ok(list_goals(uid(), include_archived=request.args.get('archived') == '1'))
        except Exception as e:
            logger.error("Planner goals failed: %s", e)
            return jsonify({'error': 'Could not load goals'}), 500

    @app.route('/api/planner/goals', methods=['POST'])
    @login_required
    def planner_create_goal():
        try:
            return ok({'id': create_goal(uid(), body())}, 201)
        except ValidationError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error("Planner create goal failed: %s", e)
            return jsonify({'error': 'Could not save goal'}), 500

    @app.route('/api/planner/goals/<int:goal_id>', methods=['PUT'])
    @login_required
    def planner_update_goal(goal_id):
        try:
            if not update_goal(uid(), goal_id, body()):
                return not_found('Goal')
            return ok()
        except ValidationError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error("Planner update goal failed: %s", e)
            return jsonify({'error': 'Could not update goal'}), 500

    @app.route('/api/planner/goals/<int:goal_id>', methods=['DELETE'])
    @login_required
    def planner_delete_goal(goal_id):
        try:
            if not delete_goal(uid(), goal_id):
                return not_found('Goal')
            return ok()
        except Exception as e:
            logger.error("Planner delete goal failed: %s", e)
            return jsonify({'error': 'Could not delete goal'}), 500

    @app.route('/api/planner/goals/<int:goal_id>/contributions', methods=['POST'])
    @login_required
    def planner_add_contribution(goal_id):
        try:
            contribution_id = add_contribution(uid(), goal_id, body())
            if contribution_id is None:
                return not_found('Goal')
            return ok({'id': contribution_id}, 201)
        except ValidationError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error("Planner add contribution failed: %s", e)
            return jsonify({'error': 'Could not save contribution'}), 500

    @app.route('/api/planner/goals/<int:goal_id>/contributions/<int:contribution_id>', methods=['DELETE'])
    @login_required
    def planner_delete_contribution(goal_id, contribution_id):
        try:
            if not delete_contribution(uid(), goal_id, contribution_id):
                return not_found('Contribution')
            return ok()
        except Exception as e:
            logger.error("Planner delete contribution failed: %s", e)
            return jsonify({'error': 'Could not delete contribution'}), 500

    # ---- notification settings --------------------------------------------
    @app.route('/api/planner/settings', methods=['GET'])
    @login_required
    def planner_get_settings():
        try:
            return ok(get_settings(uid()))
        except Exception as e:
            logger.error("Planner settings failed: %s", e)
            return jsonify({'error': 'Could not load settings'}), 500

    @app.route('/api/planner/settings', methods=['PUT'])
    @login_required
    def planner_save_settings():
        try:
            save_settings(uid(), body())
            return ok()
        except ValidationError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error("Planner save settings failed: %s", e)
            return jsonify({'error': 'Could not save settings'}), 500

    @app.route('/api/planner/settings/test', methods=['POST'])
    @login_required
    def planner_test_notification():
        sent = _notify_user(uid(), 'Planner test', 'Budget alerts and bill reminders will arrive here.',
                            tags='white_check_mark')
        if sent:
            return ok({'message': 'Test notification sent'})
        return jsonify({'error': 'Could not send. Save a topic first and check the ntfy server settings.'}), 400

    logger.info("Planner routes registered successfully")
