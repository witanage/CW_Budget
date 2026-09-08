"""
DFCC Bank Exchange Rate Service

Scrapes USD and GBP to LKR exchange rates from DFCC Bank website
and stores them in the database.

URL: https://www.dfcc.lk/rates-and-tariff/exchange-rates
"""

import logging
from datetime import datetime
from decimal import Decimal

import requests
from bs4 import BeautifulSoup
from mysql.connector import Error

from db import get_db_connection

logger = logging.getLogger(__name__)

# Currency codes supported (matches the text shown in the currency column)
SUPPORTED_CURRENCIES = ('USD', 'GBP')

# Column indices for Telegraphic Transfer rates (0-based)
TT_BUY_COL_IDX = 3  # "TT Buying" column
TT_SELL_COL_IDX = 4  # "DD / TT Selling" column


class DFCCExchangeRateService:
    """Service to fetch and store DFCC Bank exchange rates."""

    def __init__(self):
        self.url = "https://www.dfcc.lk/rates-and-tariff/exchange-rates"

    def fetch_dfcc_rates(self, currency='USD'):
        """
        Scrape exchange rates from DFCC Bank website for a specific currency.

        Extracts Telegraphic Transfer (TT) rates from the exchange rate table.

        Args:
            currency: Currency code ('USD' or 'GBP')

        Returns:
            dict: Exchange rate data or None if fetch fails
            Example: {
                'date': '2026-09-08',
                'buy_rate': 324.00,
                'sell_rate': 333.50,
                'source': 'DFCC',
                'currency': 'USD'
            }
        """
        try:
            currency = currency.upper()

            if currency not in SUPPORTED_CURRENCIES:
                logger.error(f"Unsupported currency: {currency}. Supported: {list(SUPPORTED_CURRENCIES)}")
                return None

            logger.info(f"Fetching {currency} exchange rates from DFCC Bank...")

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

            # Find the exchange rates table by locating the "TT Buying" header
            table = None
            for candidate in soup.find_all('table'):
                header_text = candidate.get_text(' ', strip=True)
                if 'TT Buying' in header_text:
                    table = candidate
                    break

            if not table:
                logger.error("Exchange rates table not found")
                return None

            # Find the currency row (currency code appears as text in the first cell)
            currency_row = None
            for row in table.find_all('tr'):
                cells = row.find_all('td')
                if cells and cells[0].get_text(strip=True) == currency:
                    currency_row = row
                    break

            if not currency_row:
                logger.error(f"{currency} row not found in exchange rates table")
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
                logger.error(f"Invalid {currency} rates from DFCC Bank: buy={buy_rate}, sell={sell_rate}")
                return None

            today = datetime.now().date()

            rate_data = {
                'date': today.strftime('%Y-%m-%d'),
                'buy_rate': buy_rate,
                'sell_rate': sell_rate,
                'source': 'DFCC',
                'currency': currency
            }

            logger.info(
                f"Successfully fetched DFCC {currency} rates for {rate_data['date']}: "
                f"Buy={buy_rate}, Sell={sell_rate}"
            )

            return rate_data

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error fetching DFCC Bank rates: {str(e)}")
            return None
        except (ValueError, TypeError, IndexError) as e:
            logger.error(f"Error parsing DFCC Bank page: {str(e)}")
            logger.debug(f"Buy text: {buy_text if 'buy_text' in locals() else 'N/A'}, "
                         f"Sell text: {sell_text if 'sell_text' in locals() else 'N/A'}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching DFCC Bank rates: {str(e)}", exc_info=True)
            return None

    def save_exchange_rate(self, date, buy_rate, sell_rate, source='DFCC', currency='USD'):
        """
        Save exchange rate to database.

        Args:
            date: datetime.date or str (YYYY-MM-DD)
            buy_rate: float or Decimal
            sell_rate: float or Decimal
            source: str (default 'DFCC')
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

            logger.info(f"Saved DFCC exchange rate for {date_str}: Buy={buy_rate}, Sell={sell_rate}")
            return True

        except Error as e:
            logger.error(f"Database error saving DFCC exchange rate: {str(e)}")
            if connection:
                connection.rollback()
            return False
        except Exception as e:
            logger.error(f"Unexpected error saving DFCC exchange rate: {str(e)}", exc_info=True)
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
        rate_data = self.fetch_dfcc_rates(currency=currency)

        if rate_data:
            success = self.save_exchange_rate(
                date=rate_data['date'],
                buy_rate=rate_data['buy_rate'],
                sell_rate=rate_data['sell_rate'],
                source='DFCC',
                currency=currency
            )

            if success:
                return rate_data
            else:
                logger.error(f"Failed to save DFCC {currency} rate to database")
                return None
        else:
            logger.error(f"Failed to fetch DFCC {currency} rate")
            return None


# Singleton instance
_dfcc_service_instance = None


def get_dfcc_exchange_rate_service():
    """Get or create the singleton instance of DFCCExchangeRateService."""
    global _dfcc_service_instance
    if _dfcc_service_instance is None:
        _dfcc_service_instance = DFCCExchangeRateService()
    return _dfcc_service_instance
