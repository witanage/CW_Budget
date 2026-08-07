"""
Ntfy.sh Notification Service
Sends push notifications via ntfy.sh when exchange rates change
Uses a global topic configured in app_settings
"""

import logging
import requests
import time
from typing import Dict

from db import get_db_connection

logger = logging.getLogger(__name__)

# Default ntfy server URL and retry attempts (can be overridden in app_settings)
DEFAULT_NTFY_SERVER = "https://ntfy.sh"
DEFAULT_RETRY_ATTEMPTS = 3


def _format_rate_change(bank: str, result: Dict) -> str:
    """Format a single bank's rate change for notification message (buy rate only)."""
    if result.get('status') != 'success':
        return f"{bank}: Failed to fetch"

    buy_rate = result.get('buy_rate')
    buy_change = result.get('buy_change')
    is_new = result.get('is_new', False)
    changed = result.get('changed', False)

    if is_new:
        return f"{bank}: New rate (Buy: {buy_rate})"
    elif not changed:
        return f"{bank}: No change (Buy: {buy_rate})"

    # Build change description with arrows (buy rate only)
    if buy_change is not None and buy_change != 0:
        arrow = "▲" if buy_change > 0 else "▼"
        prev_buy = result.get('previous_buy_rate')
        return f"{bank}: Buy {arrow}{abs(buy_change):.4f} ({prev_buy:.4f}→{buy_rate:.4f})"

    return f"{bank}: No buy rate change"


def send_rate_change_notifications(results: Dict) -> None:
    """
    Send push notifications to currency-specific ntfy topics when rates change.

    Args:
        results: Dict of bank results from refresh_all_exchange_rates()
                 Format: {'HNB_USD': {...}, 'HNB_GBP': {...}, 'PB_USD': {...}, etc.}
    """
    # Group results by currency
    currencies = {}
    for key, result in results.items():
        # Extract currency from key (e.g., 'HNB_USD' -> 'USD')
        if '_' in key:
            bank, currency = key.rsplit('_', 1)
            if currency not in currencies:
                currencies[currency] = {}
            currencies[currency][bank] = result
        else:
            # Backward compatibility: keys without currency suffix default to USD
            if 'USD' not in currencies:
                currencies['USD'] = {}
            currencies['USD'][key] = result

    # Process each currency separately
    for currency, currency_results in currencies.items():
        _send_currency_notification(currency, currency_results)


def _send_currency_notification(currency: str, results: Dict) -> None:
    """
    Send notification for a specific currency's rate changes (buy rate only).

    Args:
        currency: Currency code (e.g., 'USD', 'GBP')
        results: Dict of bank results for this currency
                 Format: {'HNB': {...}, 'PB': {...}, etc.}
    """
    # Check if any buy rate changes were detected for this currency
    changes_detected = any(
        r.get('status') == 'success' and
        r.get('changed', False) and
        r.get('buy_change') is not None and
        r.get('buy_change') != 0
        for r in results.values()
    )

    if not changes_detected:
        logger.info(f"No {currency} buy rate changes detected, skipping notification")
        return

    # Get currency-specific ntfy topic and server URL from app_settings
    topic_key = 'ntfy_topic_gbp' if currency == 'GBP' else 'ntfy_topic'
    ntfy_topic = None
    ntfy_server = DEFAULT_NTFY_SERVER
    ntfy_username = None
    ntfy_password = None
    retry_attempts = DEFAULT_RETRY_ATTEMPTS
    connection = None

    try:
        connection = get_db_connection()
        if not connection:
            logger.error(f"Cannot send {currency} notifications: database connection failed")
            return

        cursor = connection.cursor(dictionary=True)

        # Get ntfy topic
        cursor.execute("SELECT value FROM app_settings WHERE setting_key = %s", (topic_key,))
        result = cursor.fetchone()
        if result:
            ntfy_topic = result['value'].strip()

        # Get ntfy server URL (optional, defaults to public ntfy.sh)
        cursor.execute("SELECT value FROM app_settings WHERE setting_key = 'ntfy_server_url'")
        result = cursor.fetchone()
        if result and result['value']:
            ntfy_server = result['value'].strip()

        # Get ntfy username (optional, for authenticated servers)
        cursor.execute("SELECT value FROM app_settings WHERE setting_key = 'ntfy_username'")
        result = cursor.fetchone()
        if result and result['value']:
            ntfy_username = result['value'].strip()

        # Get ntfy password (optional, for authenticated servers)
        cursor.execute("SELECT value FROM app_settings WHERE setting_key = 'ntfy_password'")
        result = cursor.fetchone()
        if result and result['value']:
            ntfy_password = result['value'].strip()

        # Get retry attempts (optional, defaults to 3)
        cursor.execute("SELECT value FROM app_settings WHERE setting_key = 'ntfy_retry_attempts'")
        result = cursor.fetchone()
        if result and result['value']:
            try:
                retry_attempts = int(result['value'])
                if retry_attempts < 1:
                    logger.warning(f"Invalid ntfy_retry_attempts value: {result['value']}, using default: {DEFAULT_RETRY_ATTEMPTS}")
                    retry_attempts = DEFAULT_RETRY_ATTEMPTS
            except (ValueError, TypeError):
                logger.warning(f"Invalid ntfy_retry_attempts value: {result['value']}, using default: {DEFAULT_RETRY_ATTEMPTS}")
                retry_attempts = DEFAULT_RETRY_ATTEMPTS

        cursor.close()
        connection.close()

        if not ntfy_topic:
            logger.info(f"No ntfy topic configured for {currency} (key: {topic_key}), skipping notification")
            return

    except Exception as e:
        logger.error(f"Error reading ntfy settings for {currency} from app_settings: {str(e)}")
        if connection:
            connection.close()
        return

    # Build notification message
    try:
        changes_lines = []
        max_abs_change = 0.0

        for bank in ['HNB', 'PB', 'SAMPATH', 'COMBANK', 'CBSL']:
            if bank in results:
                bank_result = results[bank]
                changes_lines.append(_format_rate_change(bank, bank_result))

                # Track maximum absolute buy rate change for priority
                if bank_result.get('status') == 'success':
                    buy_change = abs(bank_result.get('buy_change', 0) or 0)
                    max_abs_change = max(max_abs_change, buy_change)

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

        # Send notification to ntfy server (with fallback to default)
        def send_notification(server_url: str, is_fallback: bool = False) -> bool:
            """
            Send notification to specified server with retry logic. Returns True if successful.

            Args:
                server_url: The ntfy server URL to use
                is_fallback: Whether this is a fallback attempt
            """
            for attempt in range(1, retry_attempts + 1):
                try:
                    url = f"{server_url}/{ntfy_topic}"
                    headers = {
                        "Title": f"Buy Rate Update - {currency}/LKR",
                        "Priority": priority,
                        "Tags": tags
                    }

                    # Prepare auth if credentials are provided
                    auth = None
                    if ntfy_username and ntfy_password:
                        auth = (ntfy_username, ntfy_password)

                    response = requests.post(
                        url,
                        data=message_body.encode('utf-8'),
                        headers=headers,
                        auth=auth,
                        timeout=10
                    )

                    if response.status_code == 200:
                        fallback_msg = " (fallback to default server)" if is_fallback else ""
                        retry_msg = f" (attempt {attempt}/{retry_attempts})" if attempt > 1 else ""
                        logger.info(f"{currency} notification sent successfully to topic: {ntfy_topic}{fallback_msg}{retry_msg}")
                        return True
                    else:
                        logger.warning(
                            f"Failed to send {currency} notification to {server_url} (attempt {attempt}/{retry_attempts}): "
                            f"status={response.status_code}, response={response.text[:100]}"
                        )

                except requests.exceptions.Timeout:
                    logger.warning(f"Timeout sending {currency} notification to {server_url} (attempt {attempt}/{retry_attempts})")
                except requests.exceptions.RequestException as e:
                    logger.warning(f"Error sending {currency} notification to {server_url} (attempt {attempt}/{retry_attempts}): {str(e)}")
                except Exception as e:
                    logger.warning(f"Unexpected error sending {currency} notification to {server_url} (attempt {attempt}/{retry_attempts}): {str(e)}")

                # Don't sleep after the last attempt
                if attempt < retry_attempts:
                    time.sleep(1)  # Wait 1 second between retries

            return False

        # Try custom server first, fallback to default if it fails
        success = send_notification(ntfy_server)

        if not success and ntfy_server != DEFAULT_NTFY_SERVER:
            logger.info(f"Custom server failed after {retry_attempts} attempts, falling back to default ntfy.sh for {currency}")
            success = send_notification(DEFAULT_NTFY_SERVER, is_fallback=True)

        if not success:
            logger.error(f"All attempts to send {currency} notification failed after {retry_attempts} retries")

    except Exception as e:
        logger.error(f"Unexpected error in notification sending logic: {str(e)}")
