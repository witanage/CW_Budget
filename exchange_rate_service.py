"""
Exchange Rate Service - Fetches USD to LKR exchange rates from Central Bank of Sri Lanka
"""
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import logging
from typing import Optional, Dict
import mysql.connector
from mysql.connector import Error
import os

logger = logging.getLogger(__name__)

class ExchangeRateService:
    """Service to fetch and cache exchange rates from CBSL"""

    CBSL_URL = "https://www.cbsl.gov.lk/cbsl_custom/exratestt/exrates_resultstt.php"

    def __init__(self, db_config=None):
        self.db_config = db_config or self._get_db_config()

    def _get_db_config(self):
        """Get database configuration from environment variables"""
        return {
            'host': os.environ.get('DB_HOST', 'localhost'),
            'port': int(os.environ.get('DB_PORT', 3306)),
            'user': os.environ.get('DB_USER', 'root'),
            'password': os.environ.get('DB_PASSWORD', ''),
            'database': os.environ.get('DB_NAME', 'budget_app')
        }

    def get_exchange_rate(self, date: datetime) -> Optional[Dict[str, float]]:
        """
        Fetch exchange rate for a specific date

        Checks database first, then attempts to fetch from CBSL if not found

        Args:
            date: The date for which to fetch the exchange rate

        Returns:
            Dictionary with 'buy_rate' and 'sell_rate' or None if not found
        """
        date_str = date.strftime('%Y-%m-%d')

        # Check database first
        db_rate = self._get_rate_from_db(date)
        if db_rate:
            logger.info(f"Returning database exchange rate for {date_str}")
            return db_rate

        # Try to fetch from CBSL if not in database
        logger.info(f"Exchange rate for {date_str} not in database, attempting to fetch from CBSL")
        cbsl_rate = self._fetch_from_cbsl(date)
        if cbsl_rate:
            # Save to database for future use
            self.save_exchange_rate(
                date,
                cbsl_rate['buy_rate'],
                cbsl_rate['sell_rate'],
                source='CBSL'
            )
            logger.info(f"Successfully fetched and saved exchange rate from CBSL for {date_str}")
            return cbsl_rate

        # If CBSL fetch fails, try to find nearest previous date in DB
        logger.info(f"CBSL fetch failed for {date_str}, looking for nearest date in database")
        nearest_rate = self._get_nearest_rate_from_db(date)
        if nearest_rate:
            logger.info(f"Using nearest rate from database for {date_str}")
            return nearest_rate

        logger.warning(f"No exchange rate found for {date_str}")
        return None

    def _get_rate_from_db(self, date: datetime) -> Optional[Dict[str, float]]:
        """Get exchange rate from database for specific date"""
        try:
            connection = mysql.connector.connect(**self.db_config)
            cursor = connection.cursor(dictionary=True)

            cursor.execute("""
                SELECT date, buy_rate, sell_rate, source
                FROM exchange_rates
                WHERE date = %s
                LIMIT 1
            """, (date.strftime('%Y-%m-%d'),))

            result = cursor.fetchone()
            cursor.close()
            connection.close()

            if result:
                return {
                    'buy_rate': float(result['buy_rate']),
                    'sell_rate': float(result['sell_rate']),
                    'date': result['date'].strftime('%Y-%m-%d'),
                    'source': result['source']
                }

            return None

        except Error as e:
            logger.error(f"Database error getting exchange rate: {str(e)}")
            return None

    def _get_nearest_rate_from_db(self, date: datetime) -> Optional[Dict[str, float]]:
        """Get nearest previous exchange rate from database"""
        try:
            connection = mysql.connector.connect(**self.db_config)
            cursor = connection.cursor(dictionary=True)

            cursor.execute("""
                SELECT date, buy_rate, sell_rate, source
                FROM exchange_rates
                WHERE date <= %s
                ORDER BY date DESC
                LIMIT 1
            """, (date.strftime('%Y-%m-%d'),))

            result = cursor.fetchone()
            cursor.close()
            connection.close()

            if result:
                return {
                    'buy_rate': float(result['buy_rate']),
                    'sell_rate': float(result['sell_rate']),
                    'date': result['date'].strftime('%Y-%m-%d'),
                    'source': result['source'],
                    'note': f"Rate from {result['date'].strftime('%Y-%m-%d')} (nearest available date)"
                }

            return None

        except Error as e:
            logger.error(f"Database error getting nearest exchange rate: {str(e)}")
            return None

    def save_exchange_rate(self, date: datetime, buy_rate: float, sell_rate: float,
                          source: str = 'CBSL') -> bool:
        """Save exchange rate to database"""
        try:
            connection = mysql.connector.connect(**self.db_config)
            cursor = connection.cursor()

            cursor.execute("""
                INSERT INTO exchange_rates (date, buy_rate, sell_rate, source)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    buy_rate = VALUES(buy_rate),
                    sell_rate = VALUES(sell_rate),
                    source = VALUES(source),
                    updated_at = CURRENT_TIMESTAMP
            """, (date.strftime('%Y-%m-%d'), buy_rate, sell_rate, source))

            connection.commit()
            cursor.close()
            connection.close()

            logger.info(f"Saved exchange rate for {date.strftime('%Y-%m-%d')}: {buy_rate}/{sell_rate}")
            return True

        except Error as e:
            logger.error(f"Database error saving exchange rate: {str(e)}")
            return False

    def _fetch_from_cbsl(self, date: datetime) -> Optional[Dict[str, float]]:
        """
        Fetch exchange rates from CBSL website using their form submission

        Args:
            date: The date for which to fetch the exchange rate

        Returns:
            Dictionary with buy_rate and sell_rate or None if not found
        """
        try:
            # Prepare POST payload matching CBSL's form structure
            date_str = date.strftime('%Y-%m-%d')

            payload = {
                'lookupPage': 'lookup_daily_exchange_rates.php',
                'startRange': '2006-11-11',  # CBSL's minimum date
                'txtStart': date_str,
                'txtEnd': date_str,
                'rangeType': 'range',
                'rangeValue': '1',
                'chk_cur[]': 'USD~United States Dollar',
                'submit_button': 'Submit'
            }

            # Add headers to make the request look like it's from a browser
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://www.cbsl.gov.lk',
                'Referer': 'https://www.cbsl.gov.lk/cbsl_custom/exratestt/exrates_resultstt.php',
                'Connection': 'keep-alive'
            }

            # POST request to CBSL
            response = requests.post(self.CBSL_URL, data=payload, headers=headers, timeout=15)
            response.raise_for_status()

            # Parse the HTML response
            soup = BeautifulSoup(response.text, 'html.parser')

            # Find the table with exchange rates
            table = soup.find('table', class_='table')
            if not table:
                logger.error("Could not find exchange rate table in CBSL response")
                return None

            # Look for the specific date in the table
            target_date_str = date.strftime('%Y-%m-%d')
            rows = table.find_all('tr', class_='odd')

            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 3:
                    row_date = cells[0].text.strip()
                    if row_date == target_date_str:
                        buy_rate = float(cells[1].text.strip())
                        sell_rate = float(cells[2].text.strip())
                        return {
                            'buy_rate': buy_rate,
                            'sell_rate': sell_rate,
                            'date': target_date_str
                        }

            # If exact date not found, try to find the nearest previous date
            logger.info(f"Exact date {target_date_str} not found, looking for nearest previous date")
            return self._find_nearest_rate(rows, date)

        except requests.RequestException as e:
            logger.error(f"HTTP request error: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error parsing CBSL data: {str(e)}")
            return None

    def _find_nearest_rate(self, rows, target_date: datetime) -> Optional[Dict[str, float]]:
        """
        Find the nearest previous exchange rate if exact date is not available
        (e.g., weekends, holidays)
        """
        try:
            target_date_str = target_date.strftime('%Y-%m-%d')
            nearest_date = None
            nearest_rates = None

            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 3:
                    row_date_str = cells[0].text.strip()
                    row_date = datetime.strptime(row_date_str, '%Y-%m-%d')

                    # Find the most recent date before or equal to target date
                    if row_date <= target_date:
                        if nearest_date is None or row_date > nearest_date:
                            nearest_date = row_date
                            buy_rate = float(cells[1].text.strip())
                            sell_rate = float(cells[2].text.strip())
                            nearest_rates = {
                                'buy_rate': buy_rate,
                                'sell_rate': sell_rate,
                                'date': row_date_str,
                                'note': f'Rate from {row_date_str} (nearest available date)'
                            }

            if nearest_rates:
                logger.info(f"Using nearest rate from {nearest_rates['date']} for requested date {target_date_str}")

            return nearest_rates
        except Exception as e:
            logger.error(f"Error finding nearest rate: {str(e)}")
            return None

    def get_rates_for_month(self, year: int, month: int) -> Dict[str, Dict[str, float]]:
        """
        Get exchange rates for all days in a specific month

        Args:
            year: Year
            month: Month (1-12)

        Returns:
            Dictionary mapping date strings to rate dictionaries
        """
        import calendar
        rates = {}

        # Get the last day of the month
        last_day = calendar.monthrange(year, month)[1]

        # Fetch rates for each day
        for day in range(1, last_day + 1):
            date = datetime(year, month, day)
            rate = self.get_exchange_rate(date)
            if rate:
                date_str = date.strftime('%Y-%m-%d')
                rates[date_str] = rate

        return rates

# Singleton instance
_exchange_rate_service = None

def get_exchange_rate_service() -> ExchangeRateService:
    """Get or create the singleton exchange rate service instance"""
    global _exchange_rate_service
    if _exchange_rate_service is None:
        _exchange_rate_service = ExchangeRateService()
    return _exchange_rate_service
