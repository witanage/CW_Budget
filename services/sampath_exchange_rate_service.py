"""
Sampath Bank Exchange Rate Service

Fetches USD to LKR exchange rates from Sampath Bank API
and stores them in the database.

API Endpoint: https://www.sampath.lk/api/exchange-rates
"""

import logging
import os
from datetime import datetime
from decimal import Decimal

import mysql.connector
import requests
from dotenv import load_dotenv
from mysql.connector import Error

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)


class SampathExchangeRateService:
    """Service to fetch and store Sampath Bank exchange rates."""

    def __init__(self):
        self.api_url = "https://www.sampath.lk/api/exchange-rates"
        self.headers = {
            'User-Agent': (
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/144.0.0.0 Safari/537.36'
            )
        }
        self.db_config = {
            'host': os.environ.get('DB_HOST'),
            'port': int(os.environ.get('DB_PORT', 3306)),
            'database': os.environ.get('DB_NAME'),
            'user': os.environ.get('DB_USER'),
            'password': os.environ.get('DB_PASSWORD'),
            'charset': 'utf8mb4',
            'use_unicode': True
        }

    def _get_db_connection(self):
        """Create a database connection."""
        try:
            connection = mysql.connector.connect(**self.db_config)
            return connection
        except Error as e:
            logger.error(f"Error connecting to MySQL: {e}")
            return None

    def fetch_sampath_rates(self):
        """
        Fetch current exchange rates from Sampath Bank API.

        Returns:
            dict: Exchange rate data or None if fetch fails
            Example: {
                'date': '2026-02-09',
                'buy_rate': 306.25,
                'sell_rate': 312.75,
                'source': 'SAMPATH',
                'updated_on': 'Monday, February 09 2026, 08:23:46 AM'
            }
        """
        try:
            logger.info("Fetching exchange rates from Sampath Bank API...")

            response = requests.get(self.api_url, headers=self.headers, timeout=10)
            response.raise_for_status()

            data = response.json()

            if not data.get('success'):
                logger.error("Sampath API returned success=false")
                return None

            exchange_rates = data.get('data', [])

            if not exchange_rates:
                logger.error("No exchange rates found in Sampath API response ('data' array is empty)")
                return None

            # Find USD entry in the exchange rates array
            usd_data = None
            for entry in exchange_rates:
                if entry.get('CurrCode') == 'USD':
                    usd_data = entry
                    break

            if not usd_data:
                logger.error("USD not found in Sampath API response")
                logger.debug(f"Available currencies: {[e.get('CurrCode') for e in exchange_rates[:5]]}")
                return None

            # TTBUY = TT Buying rate, TTSEL = TT Selling rate
            buy_rate = float(usd_data.get('TTBUY', 0))
            sell_rate = float(usd_data.get('TTSEL', 0))

            if buy_rate <= 0 or sell_rate <= 0:
                logger.error(f"Invalid rates from Sampath: buy={buy_rate}, sell={sell_rate}")
                return None

            today = datetime.now().date()

            # Get the RateWEF (Rate With Effect From) timestamp
            updated_on = usd_data.get('RateWEF')

            rate_data = {
                'date': today.strftime('%Y-%m-%d'),
                'buy_rate': buy_rate,
                'sell_rate': sell_rate,
                'source': 'SAMPATH',
                'updated_on': updated_on
            }

            logger.info(f"Successfully fetched Sampath rates for {rate_data['date']}: "
                        f"Buy={buy_rate}, Sell={sell_rate}, Updated={updated_on}")

            return rate_data

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error fetching Sampath rates: {str(e)}")
            return None
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Error parsing Sampath API response: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching Sampath rates: {str(e)}", exc_info=True)
            return None

    def save_exchange_rate(self, date, buy_rate, sell_rate, source='SAMPATH'):
        """
        Save exchange rate to database.

        Args:
            date: datetime.date or str (YYYY-MM-DD)
            buy_rate: float or Decimal
            sell_rate: float or Decimal
            source: str (default 'SAMPATH')

        Returns:
            bool: True if successful, False otherwise
        """
        connection = None
        cursor = None

        try:
            if isinstance(date, datetime):
                date_str = date.strftime('%Y-%m-%d')
            elif isinstance(date, str):
                date_str = date
            else:
                date_str = str(date)

            buy_rate_decimal = Decimal(str(buy_rate))
            sell_rate_decimal = Decimal(str(sell_rate))

            connection = self._get_db_connection()
            if not connection:
                return False

            cursor = connection.cursor()

            cursor.execute("""
                INSERT INTO exchange_rates (date, buy_rate, sell_rate, source)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    buy_rate = VALUES(buy_rate),
                    sell_rate = VALUES(sell_rate),
                    updated_at = CURRENT_TIMESTAMP
            """, (date_str, buy_rate_decimal, sell_rate_decimal, source))

            connection.commit()

            logger.info(f"Saved Sampath exchange rate for {date_str}: Buy={buy_rate}, Sell={sell_rate}")
            return True

        except Error as e:
            logger.error(f"Database error saving Sampath exchange rate: {str(e)}")
            if connection:
                connection.rollback()
            return False
        except Exception as e:
            logger.error(f"Unexpected error saving Sampath exchange rate: {str(e)}", exc_info=True)
            if connection:
                connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def get_exchange_rate(self, date=None):
        """
        Get Sampath exchange rate for a specific date from database.

        Args:
            date: datetime.date or str (YYYY-MM-DD). If None, uses today.

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

            connection = self._get_db_connection()
            if not connection:
                return None

            cursor = connection.cursor(dictionary=True)

            cursor.execute("""
                SELECT date, buy_rate, sell_rate, source, updated_at
                FROM exchange_rates
                WHERE date = %s AND source = 'SAMPATH'
            """, (date_str,))

            result = cursor.fetchone()

            if result:
                return {
                    'date': str(result['date']),
                    'buy_rate': float(result['buy_rate']),
                    'sell_rate': float(result['sell_rate']),
                    'source': result['source'],
                    'updated_at': str(result['updated_at']) if result['updated_at'] else None
                }

            return None

        except Exception as e:
            logger.error(f"Error getting Sampath exchange rate for {date}: {str(e)}")
            return None
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def fetch_and_store_current_rate(self):
        """
        Fetch current exchange rate from Sampath Bank and store in database.

        Returns:
            dict: Saved exchange rate data or None if failed
        """
        rate_data = self.fetch_sampath_rates()

        if not rate_data:
            logger.error("Failed to fetch exchange rate from Sampath Bank")
            return None

        success = self.save_exchange_rate(
            date=rate_data['date'],
            buy_rate=rate_data['buy_rate'],
            sell_rate=rate_data['sell_rate'],
            source='SAMPATH'
        )

        if success:
            logger.info(f"Successfully stored Sampath rate for {rate_data['date']}")
            return rate_data
        else:
            logger.error("Failed to store Sampath rate in database")
            return None

    def get_or_fetch_rate(self, date=None):
        """
        Get exchange rate from database, or fetch from Sampath Bank if today
        and not cached.

        Args:
            date: datetime.date or str (YYYY-MM-DD). If None, uses today.

        Returns:
            dict: Exchange rate data or None
        """
        if date is None:
            date = datetime.now().date()
        elif isinstance(date, str):
            date = datetime.strptime(date, '%Y-%m-%d').date()

        # First try database
        rate = self.get_exchange_rate(date)

        if rate:
            logger.info(f"Found cached Sampath rate for {date}: {rate}")
            return rate

        # If today's rate is missing, fetch from Sampath Bank
        today = datetime.now().date()
        if date == today:
            logger.info(f"Sampath rate not in cache for today ({date}), fetching...")
            return self.fetch_and_store_current_rate()

        logger.warning(f"No Sampath exchange rate found for {date} (historical date)")
        return None


# Singleton instance
_sampath_service_instance = None


def get_sampath_exchange_rate_service():
    """Get singleton instance of SampathExchangeRateService."""
    global _sampath_service_instance
    if _sampath_service_instance is None:
        _sampath_service_instance = SampathExchangeRateService()
    return _sampath_service_instance
