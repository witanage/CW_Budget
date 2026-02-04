"""
People's Bank Exchange Rate Service

Scrapes USD to LKR exchange rates from People's Bank website
and stores them in the database.

URL: https://www.peoplesbank.lk/exchange-rates/

The USD row contains 6 rate columns.  Columns 5 and 6 (1-based) are
used as Buy and Sell respectively.
"""

import logging
import os
from datetime import datetime
from decimal import Decimal

import mysql.connector
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from mysql.connector import Error

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)

# 0-based indices into the <td> list of the USD row
_BUY_COL_IDX = 4   # column 5
_SELL_COL_IDX = 5  # column 6


class PeoplesBankExchangeRateService:
    """Service to fetch and store People's Bank exchange rates."""

    def __init__(self):
        self.url = "https://www.peoplesbank.lk/exchange-rates/"
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

    def fetch_pb_rates(self):
        """
        Scrape current USD exchange rates from People's Bank website.

        Finds the "US Dollars" row in the exchange-rate table and reads
        column 5 (Buy) and column 6 (Sell).

        Returns:
            dict: Exchange rate data or None if fetch fails
            Example: {
                'date': '2026-02-04',
                'buy_rate': 306.1574,
                'sell_rate': 312.4712,
                'source': 'PB'
            }
        """
        try:
            logger.info("Fetching exchange rates from People's Bank...")

            headers = {
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
            }

            response = requests.get(self.url, headers=headers, timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Locate the USD row: <th scope="row">US Dollars</th>
            usd_row = None
            for th in soup.find_all('th', attrs={'scope': 'row'}):
                if 'US Dollars' in th.get_text(strip=True):
                    usd_row = th.find_parent('tr')
                    break

            if not usd_row:
                # Fallback: any text node containing "US Dollars"
                for node in soup.find_all(string=lambda t: t and 'US Dollars' in t):
                    usd_row = node.find_parent('tr')
                    if usd_row:
                        break

            if not usd_row:
                logger.error("US Dollars row not found on People's Bank page")
                return None

            cells = usd_row.find_all('td')

            if len(cells) <= _SELL_COL_IDX:
                logger.error(
                    f"Expected at least {_SELL_COL_IDX + 1} <td> columns in USD row, "
                    f"found {len(cells)}"
                )
                return None

            buy_rate = float(cells[_BUY_COL_IDX].get_text(strip=True))
            sell_rate = float(cells[_SELL_COL_IDX].get_text(strip=True))

            if buy_rate <= 0 or sell_rate <= 0:
                logger.error(f"Invalid rates from People's Bank: buy={buy_rate}, sell={sell_rate}")
                return None

            today = datetime.now().date()

            rate_data = {
                'date': today.strftime('%Y-%m-%d'),
                'buy_rate': buy_rate,
                'sell_rate': sell_rate,
                'source': 'PB'
            }

            logger.info(
                f"Successfully fetched PB rates for {rate_data['date']}: "
                f"Buy={buy_rate}, Sell={sell_rate}"
            )

            return rate_data

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error fetching People's Bank rates: {str(e)}")
            return None
        except (ValueError, TypeError, IndexError) as e:
            logger.error(f"Error parsing People's Bank page: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching People's Bank rates: {str(e)}", exc_info=True)
            return None

    def save_exchange_rate(self, date, buy_rate, sell_rate, source='PB'):
        """
        Save exchange rate to database.

        Args:
            date: datetime.date or str (YYYY-MM-DD)
            buy_rate: float or Decimal
            sell_rate: float or Decimal
            source: str (default 'PB')

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

            logger.info(f"Saved PB exchange rate for {date_str}: Buy={buy_rate}, Sell={sell_rate}")
            return True

        except Error as e:
            logger.error(f"Database error saving PB exchange rate: {str(e)}")
            if connection:
                connection.rollback()
            return False
        except Exception as e:
            logger.error(f"Unexpected error saving PB exchange rate: {str(e)}", exc_info=True)
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
        Get PB exchange rate for a specific date from database.

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
                WHERE date = %s AND source = 'PB'
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
            logger.error(f"Error getting PB exchange rate for {date}: {str(e)}")
            return None
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def fetch_and_store_current_rate(self):
        """
        Fetch current exchange rate from People's Bank and store in database.

        Returns:
            dict: Saved exchange rate data or None if failed
        """
        rate_data = self.fetch_pb_rates()

        if not rate_data:
            logger.error("Failed to fetch exchange rate from People's Bank")
            return None

        success = self.save_exchange_rate(
            date=rate_data['date'],
            buy_rate=rate_data['buy_rate'],
            sell_rate=rate_data['sell_rate'],
            source='PB'
        )

        if success:
            logger.info(f"Successfully stored PB rate for {rate_data['date']}")
            return rate_data
        else:
            logger.error("Failed to store PB rate in database")
            return None

    def get_or_fetch_rate(self, date=None):
        """
        Get exchange rate from database, or scrape from People's Bank if today
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
            logger.info(f"Found cached PB rate for {date}: {rate}")
            return rate

        # If today's rate is missing, scrape People's Bank
        today = datetime.now().date()
        if date == today:
            logger.info(f"PB rate not in cache for today ({date}), fetching...")
            return self.fetch_and_store_current_rate()

        logger.warning(f"No PB exchange rate found for {date} (historical date)")
        return None


# Singleton instance
_pb_service_instance = None


def get_pb_exchange_rate_service():
    """Get singleton instance of PeoplesBankExchangeRateService."""
    global _pb_service_instance
    if _pb_service_instance is None:
        _pb_service_instance = PeoplesBankExchangeRateService()
    return _pb_service_instance
