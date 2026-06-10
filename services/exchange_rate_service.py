"""
Exchange Rate Service - Fetches USD to LKR exchange rates from Central Bank of Sri Lanka
"""
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import logging
from typing import Optional, Dict
from mysql.connector import Error

from db import get_db_connection

logger = logging.getLogger(__name__)

class ExchangeRateService:
    """Service to fetch and cache exchange rates from CBSL"""

    CBSL_URL = "https://www.cbsl.gov.lk/cbsl_custom/exratestt/exrates_resultstt.php"

    # Currency name mapping for CBSL form submission
    CURRENCY_MAP = {
        'USD': 'United States Dollar',
        'GBP': 'British Pound',
        'EUR': 'Euro'
    }

    def __init__(self, db_config=None):
        # db_config kept for backward compatibility but is no longer used;
        # all connections now come from the shared pool in db.py.
        pass

    def get_exchange_rate(self, date: datetime, currency: str = 'USD') -> Optional[Dict[str, float]]:
        """
        Fetch exchange rate for a specific date and currency

        Checks database first, then attempts to fetch from CBSL if not found

        Args:
            date: The date for which to fetch the exchange rate
            currency: Currency code (USD, GBP, EUR) - default USD

        Returns:
            Dictionary with 'buy_rate', 'sell_rate', 'currency' or None if not found
        """
        date_str = date.strftime('%Y-%m-%d')
        currency = currency.upper()

        # Validate currency
        if currency not in self.CURRENCY_MAP:
            logger.error(f"Unsupported currency: {currency}")
            return None

        # Check database first
        db_rate = self._get_rate_from_db(date, currency)
        if db_rate:
            logger.info(f"Returning database exchange rate for {date_str} ({currency})")
            return db_rate

        # Check if database has ANY exchange rates
        # If empty, fetch bulk CSV to populate it
        db_is_empty = self._is_database_empty()
        logger.info(f"Database empty check: {db_is_empty}")

        if db_is_empty:
            logger.info("Database is empty. Fetching bulk CSV data from CBSL...")
            bulk_imported = self._fetch_and_import_bulk_csv()
            logger.info(f"Bulk import result: {bulk_imported}")

            if bulk_imported:
                logger.info("Bulk CSV import successful. Checking database again...")
                db_rate = self._get_rate_from_db(date, currency)
                if db_rate:
                    logger.info(f"Found rate after bulk import: {db_rate}")
                    return db_rate
                else:
                    logger.warning(f"Rate for {date_str} ({currency}) not found even after bulk import")
            else:
                logger.error("Bulk CSV import failed. Will try individual fetch.")

        # If still not found, try to fetch individual date from CBSL
        logger.info(f"Exchange rate for {date_str} ({currency}) not in database, attempting individual fetch from CBSL")
        cbsl_rate = self._fetch_from_cbsl(date, currency)

        if cbsl_rate:
            logger.info(f"Individual CBSL fetch successful for {date_str} ({currency}): {cbsl_rate}")
            # Save to database for future use
            saved = self.save_exchange_rate(
                date,
                cbsl_rate['buy_rate'],
                cbsl_rate['sell_rate'],
                source='CBSL',
                currency=currency
            )
            logger.info(f"Save to database result: {saved}")
            return cbsl_rate
        else:
            logger.warning(f"Individual CBSL fetch failed for {date_str} ({currency})")

        # If CBSL fetch fails, try to find nearest previous date in DB
        logger.info(f"CBSL fetch failed for {date_str} ({currency}), looking for nearest date in database")
        nearest_rate = self._get_nearest_rate_from_db(date, currency)
        if nearest_rate:
            logger.info(f"Using nearest rate from database for {date_str} ({currency})")
            return nearest_rate

        logger.warning(f"No exchange rate found for {date_str} ({currency})")
        return None

    def _get_rate_from_db(self, date: datetime, currency: str = 'USD') -> Optional[Dict[str, float]]:
        """Get exchange rate from database for specific date and currency"""
        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)

            cursor.execute("""
                SELECT date, buy_rate, sell_rate, source, currency
                FROM exchange_rates
                WHERE date = %s AND currency = %s AND source IN ('CBSL', 'CBSL_BULK')
                LIMIT 1
            """, (date.strftime('%Y-%m-%d'), currency.upper()))

            result = cursor.fetchone()

            if result:
                return {
                    'buy_rate': float(result['buy_rate']),
                    'sell_rate': float(result['sell_rate']),
                    'date': result['date'].strftime('%Y-%m-%d'),
                    'source': result['source'],
                    'currency': result['currency']
                }

            return None

        except Error as e:
            logger.error(f"Database error getting exchange rate: {str(e)}")
            return None
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def _get_nearest_rate_from_db(self, date: datetime, currency: str = 'USD') -> Optional[Dict[str, float]]:
        """Get nearest previous exchange rate from database for specific currency"""
        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)

            cursor.execute("""
                SELECT date, buy_rate, sell_rate, source, currency
                FROM exchange_rates
                WHERE date <= %s AND currency = %s AND source IN ('CBSL', 'CBSL_BULK')
                ORDER BY date DESC
                LIMIT 1
            """, (date.strftime('%Y-%m-%d'), currency.upper()))

            result = cursor.fetchone()

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
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def save_exchange_rate(self, date: datetime, buy_rate: float, sell_rate: float,
                          source: str = 'CBSL', currency: str = 'USD') -> bool:
        """Save exchange rate to database"""
        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor()

            cursor.execute("""
                INSERT INTO exchange_rates (date, buy_rate, sell_rate, source, currency)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    buy_rate = VALUES(buy_rate),
                    sell_rate = VALUES(sell_rate),
                    source = VALUES(source),
                    updated_at = CURRENT_TIMESTAMP
            """, (date.strftime('%Y-%m-%d'), buy_rate, sell_rate, source, currency.upper()))

            connection.commit()
            logger.info(f"Saved {currency} exchange rate for {date.strftime('%Y-%m-%d')}: {buy_rate}/{sell_rate}")
            return True

        except Error as e:
            logger.error(f"Database error saving exchange rate: {str(e)}")
            if connection:
                connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def _fetch_from_cbsl(self, date: datetime, currency: str = 'USD') -> Optional[Dict[str, float]]:
        """
        Fetch exchange rates from CBSL website using their form submission

        Args:
            date: The date for which to fetch the exchange rate
            currency: Currency code (USD, GBP, EUR)

        Returns:
            Dictionary with buy_rate, sell_rate, currency or None if not found
        """
        try:
            # Prepare POST payload matching CBSL's form structure
            date_str = date.strftime('%Y-%m-%d')
            currency = currency.upper()

            # Get currency name for CBSL form
            currency_name = self.CURRENCY_MAP.get(currency)
            if not currency_name:
                logger.error(f"Currency {currency} not supported by CBSL")
                return None

            payload = {
                'lookupPage': 'lookup_daily_exchange_rates.php',
                'startRange': '2006-11-11',  # CBSL's minimum date
                'txtStart': date_str,
                'txtEnd': date_str,
                'rangeType': 'range',
                'rangeValue': '1',
                'chk_cur[]': f'{currency}~{currency_name}',
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
                            'date': target_date_str,
                            'source': 'CBSL',
                            'currency': currency
                        }

            # If exact date not found, try to find the nearest previous date
            logger.info(f"Exact date {target_date_str} not found, looking for nearest previous date")
            return self._find_nearest_rate(rows, date, currency)

        except requests.RequestException as e:
            logger.error(f"HTTP request error: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error parsing CBSL data: {str(e)}")
            return None

    def _find_nearest_rate(self, rows, target_date: datetime, currency: str = 'USD') -> Optional[Dict[str, float]]:
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
                    row_date = datetime.strptime(row_date_str, '%Y-%m-%d').date()

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
                                'source': 'CBSL',
                                'currency': currency,
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
        Get exchange rates for all days in a specific month.

        Fetches all available rates for the month in a single query rather
        than opening a connection per day.

        Args:
            year: Year
            month: Month (1-12)

        Returns:
            Dictionary mapping date strings to rate dictionaries
        """
        import calendar
        rates = {}
        last_day = calendar.monthrange(year, month)[1]

        start_date = f"{year:04d}-{month:02d}-01"
        end_date = f"{year:04d}-{month:02d}-{last_day:02d}"

        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            if not connection:
                return rates
            cursor = connection.cursor(dictionary=True)

            cursor.execute("""
                SELECT date, buy_rate, sell_rate, source
                FROM exchange_rates
                WHERE date BETWEEN %s AND %s
                  AND source IN ('CBSL', 'CBSL_BULK')
                ORDER BY date
            """, (start_date, end_date))

            for row in cursor.fetchall():
                date_str = row['date'].strftime('%Y-%m-%d')
                rates[date_str] = {
                    'buy_rate': float(row['buy_rate']),
                    'sell_rate': float(row['sell_rate']),
                    'date': date_str,
                    'source': row['source'],
                }
        except Error as e:
            logger.error(f"Database error fetching monthly rates: {str(e)}")
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

        return rates

    def _is_database_empty(self) -> bool:
        """Check if the exchange_rates table is empty"""
        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM exchange_rates WHERE source IN ('CBSL', 'CBSL_BULK')")
            count = cursor.fetchone()[0]
            return count == 0
        except Error as e:
            logger.error(f"Database error checking if empty: {str(e)}")
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def _fetch_and_import_bulk_csv(self) -> bool:
        """
        Fetch bulk historical data from CBSL and import into database
        Fetches last 2 years of data using HTML table parsing.

        Uses a single database connection for all inserts to stay within
        the server's connection limit.

        Returns:
            True if successful, False otherwise
        """
        try:
            # Fetch last 2 years of data in chunks to avoid timeouts
            end_date = datetime.now()
            start_date = end_date - timedelta(days=730)  # 2 years

            start_str = start_date.strftime('%Y-%m-%d')
            end_str = end_date.strftime('%Y-%m-%d')

            logger.info(f"Fetching bulk data from CBSL for date range: {start_str} to {end_str}")

            # Prepare POST payload
            payload = {
                'lookupPage': 'lookup_daily_exchange_rates.php',
                'startRange': '2006-11-11',  # CBSL's minimum date
                'txtStart': start_str,
                'txtEnd': end_str,
                'rangeType': 'range',
                'rangeValue': '1',
                'chk_cur[]': 'USD~United States Dollar',
                'submit_button': 'Submit'
            }

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://www.cbsl.gov.lk',
                'Referer': 'https://www.cbsl.gov.lk/cbsl_custom/exratestt/exrates_resultstt.php',
                'Connection': 'keep-alive'
            }

            # Make the request
            logger.info("Sending bulk request to CBSL...")
            response = requests.post(self.CBSL_URL, data=payload, headers=headers, timeout=60)
            response.raise_for_status()
            logger.info(f"Received response from CBSL, status: {response.status_code}")

            # Parse HTML table
            soup = BeautifulSoup(response.text, 'html.parser')
            table = soup.find('table', class_='table')

            if not table:
                logger.error("Could not find exchange rate table in CBSL response")
                logger.debug(f"Response preview: {response.text[:500]}")
                return False

            # Parse all rows from the table
            rows = table.find_all('tr', class_='odd')
            logger.info(f"Found {len(rows)} rows in CBSL response")

            if len(rows) == 0:
                logger.error("No data rows found in CBSL table")
                return False

            # Import all rates using a SINGLE connection
            success_count = 0
            error_count = 0
            connection = None
            cursor = None

            try:
                connection = get_db_connection()
                if not connection:
                    logger.error("Bulk import: could not get DB connection")
                    return False
                cursor = connection.cursor()

                for row in rows:
                    try:
                        cells = row.find_all('td')
                        if len(cells) >= 3:
                            row_date_str = cells[0].text.strip()
                            buy_rate = float(cells[1].text.strip())
                            sell_rate = float(cells[2].text.strip())

                            cursor.execute("""
                                INSERT INTO exchange_rates (date, buy_rate, sell_rate, source, currency)
                                VALUES (%s, %s, %s, %s, %s)
                                ON DUPLICATE KEY UPDATE
                                    buy_rate = VALUES(buy_rate),
                                    sell_rate = VALUES(sell_rate),
                                    source = VALUES(source),
                                    updated_at = CURRENT_TIMESTAMP
                            """, (row_date_str, buy_rate, sell_rate, 'CBSL_BULK', 'USD'))

                            success_count += 1
                            if success_count % 100 == 0:
                                connection.commit()
                                logger.info(f"Imported {success_count} rates...")
                    except Exception as e:
                        logger.error(f"Error importing row: {str(e)}")
                        error_count += 1

                connection.commit()
            finally:
                if cursor:
                    cursor.close()
                if connection:
                    connection.close()

            logger.info(f"Bulk import complete: {success_count} successful, {error_count} errors")
            return success_count > 0

        except requests.RequestException as e:
            logger.error(f"HTTP error fetching bulk data: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error in bulk import: {str(e)}", exc_info=True)
            return False

    def fetch_cbsl_rates_multi(self, currencies=['USD', 'GBP'], date=None):
        """
        Fetch exchange rates from CBSL for multiple currencies at once.

        Args:
            currencies: List of currency codes (e.g., ['USD', 'GBP'])
            date: Date to fetch (default: today)

        Returns:
            dict: Dictionary with currency codes as keys and rate data as values
            Example: {
                'USD': {'date': '2026-06-01', 'buy_rate': 325.98, 'sell_rate': 335.70, 'source': 'CBSL', 'currency': 'USD'},
                'GBP': {'date': '2026-06-01', 'buy_rate': 437.11, 'sell_rate': 453.13, 'source': 'CBSL', 'currency': 'GBP'}
            }
        """
        if date is None:
            date = datetime.now()

        date_str = date.strftime('%Y-%m-%d')
        results = {}

        try:
            # Validate currencies
            valid_currencies = [c for c in currencies if c.upper() in self.CURRENCY_MAP]
            if not valid_currencies:
                logger.error(f"No valid currencies specified. Supported: {list(self.CURRENCY_MAP.keys())}")
                return results

            logger.info(f"Fetching CBSL rates for {valid_currencies} on {date_str}")

            # Build currency checkboxes for POST payload
            currency_checkboxes = [f"{c.upper()}~{self.CURRENCY_MAP[c.upper()]}" for c in valid_currencies]
            logger.info(f"CBSL currency checkboxes: {currency_checkboxes}")

            payload = {
                'lookupPage': 'lookup_daily_exchange_rates.php',
                'startRange': '2006-11-11',
                'txtStart': date_str,
                'txtEnd': date_str,
                'rangeType': 'range',
                'rangeValue': '1',
                'chk_cur[]': currency_checkboxes,
                'submit_button': 'Submit'
            }

            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://www.cbsl.gov.lk',
                'Referer': 'https://www.cbsl.gov.lk/en/rates-and-indicators/exchange-rates/daily-buy-and-sell-exchange-rates'
            }

            # Step 1: Make POST request to get the results page
            session = requests.Session()
            response = session.post(self.CBSL_URL, data=payload, headers=headers, timeout=20)
            response.raise_for_status()

            logger.info(f"CBSL initial response status: {response.status_code}, content length: {len(response.text)}")

            # Step 2: Look for CSV export button and submit to get CSV data
            # The results page has a form with btnCSV button that downloads the CSV
            soup = BeautifulSoup(response.text, 'html.parser')
            csv_button = soup.find('button', {'name': 'btnCSV'})

            if csv_button:
                logger.info("Found CSV export button, clicking it to download CSV data")

                # Find the parent form
                form = csv_button.find_parent('form')
                if not form:
                    logger.error("CSV button found but no parent form")
                    return results

                # Get form action (if any) or use same URL
                form_action = form.get('action', self.CBSL_URL)
                if not form_action.startswith('http'):
                    # Relative URL, make it absolute
                    form_action = 'https://www.cbsl.gov.lk' + form_action if form_action.startswith('/') else self.CBSL_URL

                # Build CSV download payload - include all hidden inputs from the form
                csv_payload = {'btnCSV': 'CSV'}
                for hidden_input in form.find_all('input', {'type': 'hidden'}):
                    name = hidden_input.get('name')
                    value = hidden_input.get('value')
                    if name:
                        csv_payload[name] = value

                logger.info(f"Submitting CSV download form to: {form_action}")

                # Submit the CSV download form
                csv_response = session.post(form_action, data=csv_payload, headers=headers, timeout=20)
                csv_response.raise_for_status()

                logger.info(f"CSV response status: {csv_response.status_code}, content length: {len(csv_response.text)}")
                logger.info(f"CSV response starts with: {csv_response.text[:200]}")

                response = csv_response  # Use CSV response for parsing
            else:
                logger.warning("No CSV export button found in CBSL response, will try parsing HTML table")

            # Now parse the response (either CSV or HTML)
            # CSV format uses commas: Currency,Date,"Buy Rate","Sell Rate"
            is_csv = (',' in response.text) and (('Currency' in response.text[:200]) or ('Buy Rate' in response.text[:200]))

            if is_csv:
                logger.info("CBSL returned CSV format (comma-separated)")
                # Parse CSV format
                # Expected format:
                # Currency,Date,"Buy Rate","Sell Rate"
                #
                # GBP,2026-06-01,437.1140,453.1250
                # USD,2026-06-01,325.9782,335.7046

                lines = response.text.strip().split('\n')

                if len(lines) < 2:
                    logger.error(f"CBSL CSV response too short: {len(lines)} lines")
                    logger.warning(f"Response content (first 1000 chars): {response.text[:1000]}")
                    return results

                # Skip header line and any empty lines
                for line in lines[1:]:
                    line = line.strip()
                    if not line:  # Skip empty lines
                        continue

                    # Split by comma (handle quoted values)
                    parts = line.split(',')

                    if len(parts) >= 4:
                        try:
                            currency_code = parts[0].strip().strip('"').upper()
                            rate_date = parts[1].strip().strip('"')
                            buy_rate = float(parts[2].strip().strip('"'))
                            sell_rate = float(parts[3].strip().strip('"'))

                            logger.info(f"Parsed CSV line: {currency_code}, {rate_date}, {buy_rate}, {sell_rate}")

                            if currency_code in [c.upper() for c in valid_currencies]:
                                results[currency_code] = {
                                    'date': rate_date,
                                    'buy_rate': buy_rate,
                                    'sell_rate': sell_rate,
                                    'source': 'CBSL',
                                    'currency': currency_code
                                }
                                logger.info(f"Parsed CBSL {currency_code} rate: Buy={buy_rate}, Sell={sell_rate}")
                            else:
                                logger.info(f"Skipping currency {currency_code} (not in requested list: {[c.upper() for c in valid_currencies]})")
                        except (ValueError, IndexError) as e:
                            logger.warning(f"Error parsing CBSL CSV line '{line}': {str(e)}")
                            continue
            else:
                logger.info("CBSL returned HTML format, parsing table")
                # Parse HTML table format
                soup = BeautifulSoup(response.text, 'html.parser')

                # Find all tables
                tables = soup.find_all('table')

                if not tables:
                    logger.error("No tables found in CBSL HTML response")
                    logger.debug(f"Response preview: {response.text[:500]}")
                    return results

                # The exchange rates table should have class 'table' or be the main data table
                table = soup.find('table', class_='table') or tables[0]

                # Find all data rows (both with and without class='odd')
                rows = table.find_all('tr')
                logger.info(f"Found {len(rows)} rows in CBSL HTML table")

                for row in rows:
                    cells = row.find_all('td')

                    # Each row should have: Currency, Date, Buy Rate, Sell Rate
                    if len(cells) >= 4:
                        try:
                            currency_code = cells[0].get_text(strip=True).upper()
                            rate_date = cells[1].get_text(strip=True)
                            buy_rate_str = cells[2].get_text(strip=True)
                            sell_rate_str = cells[3].get_text(strip=True)

                            logger.info(f"Parsing HTML row: {currency_code}, {rate_date}, {buy_rate_str}, {sell_rate_str}")

                            buy_rate = float(buy_rate_str)
                            sell_rate = float(sell_rate_str)

                            if currency_code in [c.upper() for c in valid_currencies]:
                                results[currency_code] = {
                                    'date': rate_date,
                                    'buy_rate': buy_rate,
                                    'sell_rate': sell_rate,
                                    'source': 'CBSL',
                                    'currency': currency_code
                                }
                                logger.info(f"Parsed CBSL {currency_code} rate from HTML: Buy={buy_rate}, Sell={sell_rate}")
                            else:
                                logger.info(f"Skipping currency {currency_code} (not in requested list: {valid_currencies})")
                        except (ValueError, IndexError, AttributeError) as e:
                            logger.debug(f"Skipping CBSL row (likely header or invalid data): {str(e)}")
                            continue

            if not results:
                logger.warning(f"No rates found in CBSL response for {valid_currencies}")
                logger.warning(f"Response content (first 1000 chars): {response.text[:1000]}")
            else:
                logger.info(f"Successfully fetched CBSL rates for {list(results.keys())}")

            return results

        except requests.RequestException as e:
            logger.error(f"HTTP error fetching CBSL rates: {str(e)}")
            return results
        except Exception as e:
            logger.error(f"Unexpected error fetching CBSL multi-currency rates: {str(e)}", exc_info=True)
            return results
            return results

    def fetch_and_store_current_rate(self, currency='USD'):
        """
        Fetch current CBSL exchange rate for a specific currency and store in database.

        Args:
            currency: Currency code ('USD' or 'GBP')

        Returns:
            dict: Saved exchange rate data or None if failed
        """
        try:
            # Fetch rates for this currency
            rates = self.fetch_cbsl_rates_multi(currencies=[currency])

            if not rates or currency.upper() not in rates:
                logger.error(f"Failed to fetch {currency} rate from CBSL")
                return None

            rate_data = rates[currency.upper()]

            # Save to database
            success = self.save_exchange_rate(
                date=datetime.strptime(rate_data['date'], '%Y-%m-%d'),
                buy_rate=rate_data['buy_rate'],
                sell_rate=rate_data['sell_rate'],
                source='CBSL',
                currency=currency.upper()
            )

            if success:
                logger.info(f"Successfully stored CBSL {currency} rate for {rate_data['date']}")
                return rate_data
            else:
                logger.error(f"Failed to store CBSL {currency} rate in database")
                return None

        except Exception as e:
            logger.error(f"Error in fetch_and_store_current_rate for {currency}: {str(e)}", exc_info=True)
            return None

# Singleton instance
_exchange_rate_service = None

def get_exchange_rate_service() -> ExchangeRateService:
    """Get or create the singleton exchange rate service instance"""
    global _exchange_rate_service
    if _exchange_rate_service is None:
        _exchange_rate_service = ExchangeRateService()
    return _exchange_rate_service
