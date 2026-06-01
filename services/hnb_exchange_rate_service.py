"""
HNB Bank Exchange Rate Service

Fetches USD to LKR exchange rates from Hatton National Bank (HNB) API
and stores them in the database.

API Endpoint: https://venus.hnb.lk/api/get_rates_contents_web
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal

import requests
from mysql.connector import Error

from db import get_db_connection

logger = logging.getLogger(__name__)


class HNBExchangeRateService:
    """Service to fetch and store HNB bank exchange rates."""

    # Currency mapping: internal code -> HNB API currency name
    CURRENCY_MAP = {
        'USD': 'US Dollars',
        'GBP': 'British Pounds'
    }

    def __init__(self):
        self.api_url = "https://venus.hnb.lk/api/get_rates_contents_web"

    def fetch_hnb_rates(self, currency='USD'):
        """
        Fetch current exchange rates from HNB API.

        Args:
            currency: Currency code (USD, GBP, EUR, etc.)

        Returns:
            dict: Exchange rate data or None if fetch fails
            Example: {
                'date': '2024-02-01',
                'buy_rate': 308.50,
                'sell_rate': 318.75,
                'source': 'HNB',
                'currency': 'USD',
                'updated_on': '2026-01-30T03:55:26.000Z'
            }
        """
        try:
            logger.info("Fetching exchange rates from HNB API...")

            response = requests.get(self.api_url, timeout=10)
            response.raise_for_status()

            data = response.json()

            # Extract the 'ex' array from the response
            exchange_rates = data.get('ex', [])

            if not exchange_rates:
                logger.error("No exchange rates found in HNB API response ('ex' array is empty)")
                return None

            # Find the requested currency entry in the exchange rates array
            currency_name = self.CURRENCY_MAP.get(currency, currency)
            currency_data = None
            for entry in exchange_rates:
                # Check for both 'currency' field and 'currencyCode' for flexibility
                if (entry.get('currency') == currency_name or
                        entry.get('currencyCode') == currency):
                    currency_data = entry
                    break

            if not currency_data:
                logger.error(f"{currency} ({currency_name}) not found in HNB API response")
                logger.debug(f"Available currencies: {[e.get('currency') for e in exchange_rates[:5]]}")
                return None

            # Extract buy and sell rates (new field names: buyingRate, sellingRate)
            buy_rate = float(currency_data.get('buyingRate', 0))
            sell_rate = float(currency_data.get('sellingRate', 0))

            if buy_rate <= 0 or sell_rate <= 0:
                logger.error(f"Invalid rates from HNB: buy={buy_rate}, sell={sell_rate}")
                return None

            # Use today's date for the exchange rate
            today = datetime.now().date()

            # Get the updated_on timestamp from API if available
            updated_on = currency_data.get('updated_on')

            rate_data = {
                'date': today.strftime('%Y-%m-%d'),
                'buy_rate': buy_rate,
                'sell_rate': sell_rate,
                'source': 'HNB',
                'currency': currency,
                'updated_on': updated_on
            }

            logger.info(f"Successfully fetched HNB {currency} rates for {rate_data['date']}: "
                        f"Buy={buy_rate}, Sell={sell_rate}, Updated={updated_on}")

            return rate_data

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error fetching HNB rates: {str(e)}")
            return None
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Error parsing HNB API response: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching HNB rates: {str(e)}", exc_info=True)
            return None

    def save_exchange_rate(self, date, buy_rate, sell_rate, source='HNB', currency='USD'):
        """
        Save exchange rate to database.

        Args:
            date: datetime.date or str (YYYY-MM-DD)
            buy_rate: float or Decimal
            sell_rate: float or Decimal
            source: str (default 'HNB')

        Returns:
            bool: True if successful, False otherwise
        """
        connection = None
        cursor = None

        try:
            # Convert date to string if needed
            if isinstance(date, datetime):
                date_str = date.strftime('%Y-%m-%d')
            elif isinstance(date, str):
                date_str = date
            else:
                date_str = str(date)

            # Convert rates to Decimal for precision
            buy_rate_decimal = Decimal(str(buy_rate))
            sell_rate_decimal = Decimal(str(sell_rate))

            connection = get_db_connection()
            if not connection:
                return False

            cursor = connection.cursor()

            # Insert or update exchange rate
            cursor.execute("""
                           INSERT INTO exchange_rates (date, buy_rate, sell_rate, source, currency)
                           VALUES (%s, %s, %s, %s, %s) ON DUPLICATE KEY
                           UPDATE
                               buy_rate = VALUES(buy_rate),
                               sell_rate = VALUES(sell_rate),
                               source = VALUES(source),
                               updated_at = CURRENT_TIMESTAMP
                           """, (date_str, buy_rate_decimal, sell_rate_decimal, source, currency))

            connection.commit()

            logger.info(f"Saved {currency} exchange rate for {date_str}: Buy={buy_rate}, Sell={sell_rate}, Source={source}")
            return True

        except Error as e:
            logger.error(f"Database error saving exchange rate: {str(e)}")
            if connection:
                connection.rollback()
            return False
        except Exception as e:
            logger.error(f"Unexpected error saving exchange rate: {str(e)}", exc_info=True)
            if connection:
                connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def get_exchange_rate(self, date=None, currency='USD'):
        """
        Get exchange rate for a specific date and currency from database.

        Args:
            date: datetime.date or str (YYYY-MM-DD). If None, uses today.
            currency: Currency code (default 'USD')

        Returns:
            dict: Exchange rate data or None
        """
        connection = None
        cursor = None

        try:
            if date is None:
                date = datetime.now().date()
            elif isinstance(date, str):
                date = datetime.strptime(date, '%Y-%m-%d').date()

            date_str = date.strftime('%Y-%m-%d')
            currency = currency.upper()

            connection = get_db_connection()
            if not connection:
                return None

            cursor = connection.cursor(dictionary=True)

            cursor.execute("""
                           SELECT date, buy_rate, sell_rate, source, currency, updated_at
                           FROM exchange_rates
                           WHERE date = %s AND source = 'HNB' AND currency = %s
                           """, (date_str, currency))

            result = cursor.fetchone()

            if result:
                return {
                    'date': str(result['date']),
                    'buy_rate': float(result['buy_rate']),
                    'sell_rate': float(result['sell_rate']),
                    'source': result['source'],
                    'currency': result.get('currency', 'USD'),
                    'updated_at': str(result['updated_at']) if result['updated_at'] else None
                }

            return None

        except Exception as e:
            logger.error(f"Error getting exchange rate for {date_str}: {str(e)}")
            return None
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def fetch_and_store_current_rate(self, currency='USD'):
        """
        Fetch current exchange rate from HNB and store in database.

        Args:
            currency: Currency code (USD, GBP, EUR, etc.)

        Returns:
            dict: Saved exchange rate data or None if failed
        """
        # Fetch from HNB API
        rate_data = self.fetch_hnb_rates(currency=currency)

        if not rate_data:
            logger.error(f"Failed to fetch {currency} exchange rate from HNB")
            return None

        # Save to database
        success = self.save_exchange_rate(
            date=rate_data['date'],
            buy_rate=rate_data['buy_rate'],
            sell_rate=rate_data['sell_rate'],
            source='HNB',
            currency=currency
        )

        if success:
            logger.info(f"Successfully stored HNB {currency} rate for {rate_data['date']}")
            return rate_data
        else:
            logger.error(f"Failed to store HNB {currency} rate in database")
            return None

    def get_or_fetch_rate(self, date=None):
        """
        Get exchange rate from database, or fetch from HNB if not available.

        Args:
            date: datetime.date or str (YYYY-MM-DD). If None, uses today.

        Returns:
            dict: Exchange rate data or None
        """
        if date is None:
            date = datetime.now().date()
        elif isinstance(date, str):
            date = datetime.strptime(date, '%Y-%m-%d').date()

        # First try to get from database
        rate = self.get_exchange_rate(date)

        if rate:
            logger.info(f"Found cached rate for {date}: {rate}")
            return rate

        # If today's rate is missing, fetch from HNB
        today = datetime.now().date()
        if date == today:
            logger.info(f"Rate not in cache for today ({date}), fetching from HNB...")
            return self.fetch_and_store_current_rate()

        logger.warning(f"No exchange rate found for {date} (historical date)")
        return None

    def bulk_fetch_missing_dates(self, start_date, end_date):
        """
        Check for missing dates in database and fetch from HNB if current.

        Note: HNB API only provides current rates, so this will only
        fetch the current date if it's within the range.

        Args:
            start_date: datetime.date or str (YYYY-MM-DD)
            end_date: datetime.date or str (YYYY-MM-DD)

        Returns:
            dict: Summary of operation
        """
        connection = None
        cursor = None

        try:
            if isinstance(start_date, str):
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            if isinstance(end_date, str):
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()

            today = datetime.now().date()

            # Get existing dates from database
            connection = get_db_connection()
            if not connection:
                return {'error': 'Database connection failed'}

            cursor = connection.cursor()

            cursor.execute("""
                           SELECT date
                           FROM exchange_rates
                           WHERE date BETWEEN %s AND %s
                             AND source = 'HNB'
                           """, (start_date, end_date))

            existing_dates = {row[0] for row in cursor.fetchall()}

            # Check if today is in the range and missing
            fetched = 0
            if start_date <= today <= end_date and today not in existing_dates:
                logger.info(f"Today's rate ({today}) is missing, fetching from HNB...")
                rate_data = self.fetch_and_store_current_rate()
                if rate_data:
                    fetched = 1

            missing_count = 0
            current_date = start_date
            while current_date <= end_date:
                if current_date not in existing_dates and current_date != today:
                    missing_count += 1
                current_date += timedelta(days=1)

            return {
                'already_cached': len(existing_dates),
                'fetched_today': fetched,
                'missing_historical': missing_count,
                'message': f'Fetched {fetched} rate(s). {missing_count} historical dates still missing (HNB API only provides current rates).'
            }

        except Exception as e:
            logger.error(f"Error in bulk fetch: {str(e)}")
            return {'error': str(e)}
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()


# Singleton instance
_hnb_service_instance = None


def get_hnb_exchange_rate_service():
    """Get singleton instance of HNBExchangeRateService."""
    global _hnb_service_instance
    if _hnb_service_instance is None:
        _hnb_service_instance = HNBExchangeRateService()
    return _hnb_service_instance
