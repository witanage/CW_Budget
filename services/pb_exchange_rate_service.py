"""
People's Bank Exchange Rate Service

Scrapes USD to LKR exchange rates from People's Bank website
and stores them in the database.

URL: https://www.peoplesbank.lk/exchange-rates/

The USD row contains 6 rate columns.  Columns 5 and 6 (1-based) are
used as Buy and Sell respectively.
"""

import logging
from datetime import datetime
from decimal import Decimal

import requests
from bs4 import BeautifulSoup
from mysql.connector import Error

from db import get_db_connection

logger = logging.getLogger(__name__)

# 0-based indices into the <td> list of currency rows
_BUY_COL_IDX = 4   # column 5
_SELL_COL_IDX = 5  # column 6

# Currency name mapping for People's Bank
CURRENCY_MAP = {
    'USD': 'US Dollars',
    'GBP': 'British Pound Sterling'
}


class PeoplesBankExchangeRateService:
    """Service to fetch and store People's Bank exchange rates."""

    def __init__(self):
        self.url = "https://www.peoplesbank.lk/exchange-rates/"

    def fetch_pb_rates(self, currency='USD'):
        """
        Scrape exchange rates from People's Bank website for a specific currency.

        Finds the currency row in the exchange-rate table and reads
        column 5 (Buy) and column 6 (Sell).

        Args:
            currency: Currency code ('USD' or 'GBP')

        Returns:
            dict: Exchange rate data or None if fetch fails
            Example: {
                'date': '2026-02-04',
                'buy_rate': 306.1574,
                'sell_rate': 312.4712,
                'source': 'PB',
                'currency': 'USD'
            }
        """
        try:
            currency = currency.upper()
            currency_name = CURRENCY_MAP.get(currency)

            if not currency_name:
                logger.error(f"Unsupported currency: {currency}. Supported: {list(CURRENCY_MAP.keys())}")
                return None

            logger.info(f"Fetching {currency} exchange rates from People's Bank...")

            headers = {
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
            }

            response = requests.get(self.url, headers=headers, timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Locate the currency row
            currency_row = None
            for th in soup.find_all('th', attrs={'scope': 'row'}):
                if currency_name in th.get_text(strip=True):
                    currency_row = th.find_parent('tr')
                    break

            if not currency_row:
                # Fallback: any text node containing the currency name
                for node in soup.find_all(string=lambda t: t and currency_name in t):
                    currency_row = node.find_parent('tr')
                    if currency_row:
                        break

            if not currency_row:
                logger.error(f"{currency_name} row not found on People's Bank page")
                return None

            cells = currency_row.find_all('td')

            if len(cells) <= _SELL_COL_IDX:
                logger.error(
                    f"Expected at least {_SELL_COL_IDX + 1} <td> columns in {currency} row, "
                    f"found {len(cells)}"
                )
                return None

            buy_rate = float(cells[_BUY_COL_IDX].get_text(strip=True))
            sell_rate = float(cells[_SELL_COL_IDX].get_text(strip=True))

            if buy_rate <= 0 or sell_rate <= 0:
                logger.error(f"Invalid {currency} rates from People's Bank: buy={buy_rate}, sell={sell_rate}")
                return None

            today = datetime.now().date()

            rate_data = {
                'date': today.strftime('%Y-%m-%d'),
                'buy_rate': buy_rate,
                'sell_rate': sell_rate,
                'source': 'PB',
                'currency': currency
            }

            logger.info(
                f"Successfully fetched PB {currency} rates for {rate_data['date']}: "
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

    def save_exchange_rate(self, date, buy_rate, sell_rate, source='PB', currency='USD'):
        """
        Save exchange rate to database.

        Args:
            date: datetime.date or str (YYYY-MM-DD)
            buy_rate: float or Decimal
            sell_rate: float or Decimal
            source: str (default 'PB')
            currency: str (default 'USD')

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

            connection = get_db_connection()
            if not connection:
                return False

            cursor = connection.cursor()

            cursor.execute("""
                INSERT INTO exchange_rates (date, buy_rate, sell_rate, source, currency)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    buy_rate = VALUES(buy_rate),
                    sell_rate = VALUES(sell_rate),
                    updated_at = CURRENT_TIMESTAMP
            """, (date_str, buy_rate_decimal, sell_rate_decimal, source, currency.upper()))

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

    def get_exchange_rate(self, date=None, currency='USD'):
        """
        Get PB exchange rate for a specific date and currency from database.

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
                WHERE date = %s AND source = 'PB' AND currency = %s
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
            logger.error(f"Error getting PB exchange rate for {date}: {str(e)}")
            return None
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def fetch_and_store_current_rate(self, currency='USD'):
        """
        Fetch current exchange rate from People's Bank and store in database.

        Args:
            currency: Currency code ('USD' or 'GBP')

        Returns:
            dict: Saved exchange rate data or None if failed
        """
        rate_data = self.fetch_pb_rates(currency=currency)

        if not rate_data:
            logger.error(f"Failed to fetch {currency} exchange rate from People's Bank")
            return None

        success = self.save_exchange_rate(
            date=rate_data['date'],
            buy_rate=rate_data['buy_rate'],
            sell_rate=rate_data['sell_rate'],
            source='PB',
            currency=currency
        )

        if success:
            logger.info(f"Successfully stored PB {currency} rate for {rate_data['date']}")
            return rate_data
        else:
            logger.error(f"Failed to store PB {currency} rate in database")
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
