"""
Ntfy.sh Notification Service
Sends push notifications via ntfy.sh when exchange rates change
Uses a global topic configured in app_settings
"""

import logging
import requests
from typing import Dict

from db import get_db_connection

logger = logging.getLogger(__name__)

# Ntfy.sh public server URL
NTFY_SERVER = "https://ntfy.sh"


def _format_rate_change(bank: str, result: Dict) -> str:
    """Format a single bank's rate change for notification message."""
    if result.get('status') != 'success':
        return f"{bank}: Failed to fetch"

    buy_rate = result.get('buy_rate')
    sell_rate = result.get('sell_rate')
    buy_change = result.get('buy_change')
    sell_change = result.get('sell_change')
    is_new = result.get('is_new', False)
    changed = result.get('changed', False)

    if is_new:
        return f"{bank}: New rate (Buy: {buy_rate}, Sell: {sell_rate})"
    elif not changed:
        return f"{bank}: No change (Buy: {buy_rate}, Sell: {sell_rate})"

    # Build change description with arrows
    parts = []
    if buy_change is not None and buy_change != 0:
        arrow = "▲" if buy_change > 0 else "▼"
        prev_buy = result.get('previous_buy_rate')
        parts.append(f"Buy {arrow}{abs(buy_change):.4f} ({prev_buy:.4f}→{buy_rate:.4f})")

    if sell_change is not None and sell_change != 0:
        arrow = "▲" if sell_change > 0 else "▼"
        prev_sell = result.get('previous_sell_rate')
        parts.append(f"Sell {arrow}{abs(sell_change):.4f} ({prev_sell:.4f}→{sell_rate:.4f})")

    return f"{bank}: {', '.join(parts)}" if parts else f"{bank}: No change"


def send_rate_change_notifications(results: Dict) -> None:
    """
    Send push notification to the configured global ntfy topic when exchange rates change.

    Args:
        results: Dict of bank results from refresh_all_exchange_rates()
                 Format: {'HNB': {...}, 'PB': {...}, 'SAMPATH': {...}, 'CBSL': {...}}
    """
    # Check if any changes were detected
    changes_detected = any(
        r.get('status') == 'success' and r.get('changed', False)
        for r in results.values()
    )

    if not changes_detected:
        logger.info("No exchange rate changes detected, skipping notifications")
        return

    # Get global ntfy topic from app_settings
    ntfy_topic = None
    connection = None

    try:
        connection = get_db_connection()
        if not connection:
            logger.error("Cannot send notifications: database connection failed")
            return

        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT value FROM app_settings WHERE setting_key = 'ntfy_topic'")
        result = cursor.fetchone()
        cursor.close()
        connection.close()

        if result:
            ntfy_topic = result['value'].strip()

        if not ntfy_topic:
            logger.info("No ntfy topic configured in app_settings, skipping notifications")
            return

    except Exception as e:
        logger.error(f"Error reading ntfy topic from app_settings: {str(e)}")
        if connection:
            connection.close()
        return

    # Build notification message
    try:
        changes_lines = []
        max_abs_change = 0.0

        for bank in ['HNB', 'PB', 'SAMPATH', 'CBSL']:
            if bank in results:
                result = results[bank]
                changes_lines.append(_format_rate_change(bank, result))

                # Track maximum absolute change for priority
                if result.get('status') == 'success':
                    buy_change = abs(result.get('buy_change', 0) or 0)
                    sell_change = abs(result.get('sell_change', 0) or 0)
                    max_abs_change = max(max_abs_change, buy_change, sell_change)

        message_body = "\n".join(changes_lines)

        # Determine priority and tags
        if max_abs_change > 0.50:
            priority = "high"
            tags = "chart_with_upwards_trend,warning"
        elif max_abs_change > 0:
            priority = "default"
            tags = "chart_with_upwards_trend"
        else:
            priority = "low"
            tags = "information_source"

        # Send notification to ntfy.sh
        url = f"{NTFY_SERVER}/{ntfy_topic}"
        headers = {
            "Title": "Exchange Rate Update - USD/LKR",
            "Priority": priority,
            "Tags": tags
        }

        response = requests.post(
            url,
            data=message_body.encode('utf-8'),
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            logger.info(f"Notification sent successfully to topic: {ntfy_topic}")
        else:
            logger.warning(
                f"Failed to send notification to topic {ntfy_topic}: "
                f"status={response.status_code}, response={response.text[:100]}"
            )

    except requests.exceptions.Timeout:
        logger.error(f"Timeout sending notification to topic: {ntfy_topic}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error sending notification: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error sending notification: {str(e)}")
