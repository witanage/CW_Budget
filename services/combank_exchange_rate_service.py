"""
Commercial Bank (Combank) Exchange Rate Service

Scrapes USD and GBP to LKR exchange rates from Commercial Bank website
and stores them in the database.

URL: https://www.combank.lk/rates-tariff#exchange-rates
"""

import logging
from datetime import datetime
from decimal import Decimal

import requests
from bs4 import BeautifulSoup
from mysql.connector import Error

from db import get_db_connection

logger = logging.getLogger(__name__)

# Currency name mapping for Commercial Bank
CURRENCY_MAP = {
    'USD': 'US DOLLARS',
    'GBP': 'STERLING POUNDS'
}

# Column indices for Telegraphic Transfer rates (0-based)
TT_BUY_COL_IDX = 5  # Column 6 (1-based)
TT_SELL_COL_IDX = 6  # Column 7 (1-based)


class CombankExchangeRateService:
    """Service to fetch and store Commercial Bank exchange rates."""

    def __init__(self):
        self.url = "https://www.combank.lk/rates-tariff#exchange-rates"

    def fetch_combank_rates(self, currency='USD'):
        """
        Scrape exchange rates from Commercial Bank website for a specific currency.

        Extracts Telegraphic Transfer (TT) rates from the exchange rate table.

        Args:
            currency: Currency code ('USD' or 'GBP')

        Returns:
            dict: Exchange rate data or None if fetch fails
            Example: {
                'date': '2026-07-17',
                'buy_rate': 332.00,
                'sell_rate': 340.00,
                'source': 'COMBANK',
                'currency': 'USD'
            }
        """
        try:
            currency = currency.upper()
            currency_name = CURRENCY_MAP.get(currency)

            if not currency_name:
                logger.error(f"Unsupported currency: {currency}. Supported: {list(CURRENCY_MAP.keys())}")
                return None

            logger.info(f"Fetching {currency} exchange rates from Commercial Bank...")

            headers = {
                'User-Agent': (
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/144.0.0.0 Safari/537.36'
                )
            }

            response = requests.get(self.url, headers=headers, timeout=15)
            response.raise_for_status()

            # Parse HTML with BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')

            # Find the exchange rates table (id="exchange-rates")
            exchange_section = soup.find(id='exchange-rates')
            if not exchange_section:
                logger.error("Exchange rates section not found on page")
                return None

            # Find the table within the exchange rates section
            table = exchange_section.find('table')
            if not table:
                logger.error("Exchange rates table not found")
                return None

            # Find the currency row
            currency_row = None

            # Get all rows (first 3 are headers, data starts from row 4)
            all_rows = table.find_all('tr')

            # Skip header rows (first 3 rows) and search in data rows
            for row in all_rows[3:]:  # Start from row 4 (index 3)
                cells = row.find_all('td')
                if cells and currency_name in cells[0].get_text(strip=True):
                    currency_row = row
                    break

            if not currency_row:
                logger.error(f"{currency_name} row not found in exchange rates table")
                return None

            cells = currency_row.find_all('td')

            if len(cells) <= TT_SELL_COL_IDX:
                logger.error(
                    f"Expected at least {TT_SELL_COL_IDX + 1} columns in {currency} row, "
                    f"found {len(cells)}"
                )
                return None

            # Extract TT (Telegraphic Transfer) rates
            buy_text = cells[TT_BUY_COL_IDX].get_text(strip=True)
            sell_text = cells[TT_SELL_COL_IDX].get_text(strip=True)

            # Clean text (remove commas, currency symbols)
            buy_text = buy_text.replace(',', '').replace('Rs.', '').replace('LKR', '').strip()
            sell_text = sell_text.replace(',', '').replace('Rs.', '').replace('LKR', '').strip()

            # Handle missing data (shown as "-")
            if buy_text == '-' or sell_text == '-':
                logger.error(f"TT rates not available for {currency}")
                return None

            buy_rate = float(buy_text)
            sell_rate = float(sell_text)

            if buy_rate <= 0 or sell_rate <= 0:
                logger.error(f"Invalid {currency} rates from Commercial Bank: buy={buy_rate}, sell={sell_rate}")
                return None

            today = datetime.now().date()

            rate_data = {
                'date': today.strftime('%Y-%m-%d'),
                'buy_rate': buy_rate,
                'sell_rate': sell_rate,
                'source': 'COMBANK',
                'currency': currency
            }

            logger.info(
                f"Successfully fetched COMBANK {currency} rates for {rate_data['date']}: "
                f"Buy={buy_rate}, Sell={sell_rate}"
            )

            return rate_data

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error fetching Commercial Bank rates: {str(e)}")
            return None
        except (ValueError, TypeError, IndexError) as e:
            logger.error(f"Error parsing Commercial Bank page: {str(e)}")
            logger.debug(f"Buy text: {buy_text if 'buy_text' in locals() else 'N/A'}, "
                         f"Sell text: {sell_text if 'sell_text' in locals() else 'N/A'}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching Commercial Bank rates: {str(e)}", exc_info=True)
            return None

    def save_exchange_rate(self, date, buy_rate, sell_rate, source='COMBANK', currency='USD'):
        """
        Save exchange rate to database.

        Args:
            date: datetime.date or str (YYYY-MM-DD)
            buy_rate: float or Decimal
            sell_rate: float or Decimal
            source: str (default 'COMBANK')
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

            logger.info(f"Saved COMBANK exchange rate for {date_str}: Buy={buy_rate}, Sell={sell_rate}")
            return True

        except Error as e:
            logger.error(f"Database error saving COMBANK exchange rate: {str(e)}")
            if connection:
                connection.rollback()
            return False
        except Exception as e:
            logger.error(f"Unexpected error saving COMBANK exchange rate: {str(e)}", exc_info=True)
            if connection:
                connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def fetch_and_store_current_rate(self, currency='USD'):
        """
        Fetch current exchange rate and store it in the database.

        Args:
            currency: Currency code ('USD' or 'GBP')

        Returns:
            dict: Rate data if successful, None otherwise
        """
        rate_data = self.fetch_combank_rates(currency=currency)

        if rate_data:
            success = self.save_exchange_rate(
                date=rate_data['date'],
                buy_rate=rate_data['buy_rate'],
                sell_rate=rate_data['sell_rate'],
                source='COMBANK',
                currency=currency
            )

            if success:
                return rate_data
            else:
                logger.error(f"Failed to save COMBANK {currency} rate to database")
                return None
        else:
            logger.error(f"Failed to fetch COMBANK {currency} rate")
            return None


# Singleton instance
_combank_service_instance = None


def get_combank_exchange_rate_service():
    """Get or create the singleton instance of CombankExchangeRateService."""
    global _combank_service_instance
    if _combank_service_instance is None:
        _combank_service_instance = CombankExchangeRateService()
    return _combank_service_instance
