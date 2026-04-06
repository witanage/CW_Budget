"""
Exchange Rate Routes Service
Handles all Flask routes and business logic for exchange rate functionality
"""

import calendar
import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from decimal import Decimal

from flask import request, jsonify, session
from mysql.connector import Error

from db import get_db_connection
from services.exchange_rate_service import get_exchange_rate_service
from services.hnb_exchange_rate_service import get_hnb_exchange_rate_service
from services.pb_exchange_rate_service import get_pb_exchange_rate_service
from services.sampath_exchange_rate_service import get_sampath_exchange_rate_service
from services.gemini_exchange_analyzer import get_gemini_exchange_analyzer

logger = logging.getLogger(__name__)


# ==================================================
# HELPER FUNCTIONS
# ==================================================

def refresh_all_exchange_rates(force=False):
    """Fetch today's exchange rates from all banks and cache in the database.

    Called by external cron job via the /api/exchange-rate/refresh-all endpoint.
    Fetches from all banks in parallel to minimize total execution time.
    """
    logger.info("Starting parallel exchange rate refresh (force=%s)...", force)

    # Generate a unique run key for this refresh batch
    run_key = str(uuid.uuid4())
    logger.info(f"Scheduler: Exchange rate refresh run_key: {run_key}")

    results = {}

    # Define fetch functions for each bank
    def fetch_hnb():
        hnb_start = time.time()
        try:
            hnb_service = get_hnb_exchange_rate_service()
            hnb_rate = hnb_service.fetch_and_store_current_rate()
            hnb_ms = int((time.time() - hnb_start) * 1000)
            if hnb_rate:
                logger.info(f"Scheduler: HNB rate updated: Buy={hnb_rate['buy_rate']}, Sell={hnb_rate['sell_rate']}")
                log_exchange_rate_refresh('HNB', 'success',
                                          buy_rate=hnb_rate['buy_rate'],
                                          sell_rate=hnb_rate['sell_rate'],
                                          duration_ms=hnb_ms,
                                          run_key=run_key)
                return ('HNB',
                        {'status': 'success', 'buy_rate': hnb_rate['buy_rate'], 'sell_rate': hnb_rate['sell_rate']})
            else:
                logger.warning("Scheduler: Failed to fetch HNB rate")
                log_exchange_rate_refresh('HNB', 'failure',
                                          error_message='No rate returned by HNB API',
                                          duration_ms=hnb_ms,
                                          run_key=run_key)
                return ('HNB', {'status': 'failure', 'error': 'No rate returned by HNB API'})
        except Exception as e:
            logger.error(f"Scheduler: Error fetching HNB rate: {str(e)}")
            log_exchange_rate_refresh('HNB', 'failure',
                                      error_message=str(e),
                                      duration_ms=int((time.time() - hnb_start) * 1000),
                                      run_key=run_key)
            return ('HNB', {'status': 'failure', 'error': str(e)})

    def fetch_pb():
        pb_start = time.time()
        try:
            pb_service = get_pb_exchange_rate_service()
            pb_rate = pb_service.fetch_and_store_current_rate()
            pb_ms = int((time.time() - pb_start) * 1000)
            if pb_rate:
                logger.info(f"Scheduler: PB rate updated: Buy={pb_rate['buy_rate']}, Sell={pb_rate['sell_rate']}")
                log_exchange_rate_refresh('PB', 'success',
                                          buy_rate=pb_rate['buy_rate'],
                                          sell_rate=pb_rate['sell_rate'],
                                          duration_ms=pb_ms,
                                          run_key=run_key)
                return ('PB', {'status': 'success', 'buy_rate': pb_rate['buy_rate'], 'sell_rate': pb_rate['sell_rate']})
            else:
                logger.warning("Scheduler: Failed to fetch PB rate")
                log_exchange_rate_refresh('PB', 'failure',
                                          error_message='No rate returned by PB scraper',
                                          duration_ms=pb_ms,
                                          run_key=run_key)
                return ('PB', {'status': 'failure', 'error': 'No rate returned by PB scraper'})
        except Exception as e:
            logger.error(f"Scheduler: Error fetching PB rate: {str(e)}")
            log_exchange_rate_refresh('PB', 'failure',
                                      error_message=str(e),
                                      duration_ms=int((time.time() - pb_start) * 1000),
                                      run_key=run_key)
            return ('PB', {'status': 'failure', 'error': str(e)})

    def fetch_sampath():
        sampath_start = time.time()
        try:
            sampath_service = get_sampath_exchange_rate_service()
            sampath_rate = sampath_service.fetch_and_store_current_rate()
            sampath_ms = int((time.time() - sampath_start) * 1000)
            if sampath_rate:
                logger.info(
                    f"Scheduler: Sampath rate updated: Buy={sampath_rate['buy_rate']}, Sell={sampath_rate['sell_rate']}")
                log_exchange_rate_refresh('SAMPATH', 'success',
                                          buy_rate=sampath_rate['buy_rate'],
                                          sell_rate=sampath_rate['sell_rate'],
                                          duration_ms=sampath_ms,
                                          run_key=run_key)
                return ('SAMPATH', {'status': 'success', 'buy_rate': sampath_rate['buy_rate'],
                                    'sell_rate': sampath_rate['sell_rate']})
            else:
                logger.warning("Scheduler: Failed to fetch Sampath rate")
                log_exchange_rate_refresh('SAMPATH', 'failure',
                                          error_message='No rate returned by Sampath API',
                                          duration_ms=sampath_ms,
                                          run_key=run_key)
                return ('SAMPATH', {'status': 'failure', 'error': 'No rate returned by Sampath API'})
        except Exception as e:
            logger.error(f"Scheduler: Error fetching Sampath rate: {str(e)}")
            log_exchange_rate_refresh('SAMPATH', 'failure',
                                      error_message=str(e),
                                      duration_ms=int((time.time() - sampath_start) * 1000),
                                      run_key=run_key)
            return ('SAMPATH', {'status': 'failure', 'error': str(e)})

    def fetch_cbsl():
        cbsl_start = time.time()
        try:
            cbsl_service = get_exchange_rate_service()
            cbsl_rate = cbsl_service.get_exchange_rate(datetime.now())
            cbsl_ms = int((time.time() - cbsl_start) * 1000)
            if cbsl_rate:
                logger.info(
                    f"Scheduler: CBSL rate for today: Buy={cbsl_rate['buy_rate']}, Sell={cbsl_rate['sell_rate']}")
                log_exchange_rate_refresh('CBSL', 'success',
                                          buy_rate=cbsl_rate['buy_rate'],
                                          sell_rate=cbsl_rate['sell_rate'],
                                          duration_ms=cbsl_ms,
                                          run_key=run_key)
                return ('CBSL', {'status': 'success', 'buy_rate': cbsl_rate['buy_rate'],
                                 'sell_rate': cbsl_rate['sell_rate']})
            else:
                logger.warning("Scheduler: No CBSL rate available for today")
                log_exchange_rate_refresh('CBSL', 'failure',
                                          error_message='No CBSL rate available for today',
                                          duration_ms=cbsl_ms,
                                          run_key=run_key)
                return ('CBSL', {'status': 'failure', 'error': 'No CBSL rate available for today'})
        except Exception as e:
            logger.error(f"Scheduler: Error fetching CBSL rate: {str(e)}")
            log_exchange_rate_refresh('CBSL', 'failure',
                                      error_message=str(e),
                                      duration_ms=int((time.time() - cbsl_start) * 1000),
                                      run_key=run_key)
            return ('CBSL', {'status': 'failure', 'error': str(e)})

    # Execute all fetches in parallel using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as executor:
        # Submit all tasks
        futures = {
            executor.submit(fetch_hnb): 'HNB',
            executor.submit(fetch_pb): 'PB',
            executor.submit(fetch_sampath): 'SAMPATH',
            executor.submit(fetch_cbsl): 'CBSL'
        }

        # Collect results as they complete
        for future in as_completed(futures):
            try:
                bank_name, result = future.result()
                results[bank_name] = result
            except Exception as e:
                bank = futures[future]
                logger.error(f"Unexpected error in {bank} fetch thread: {str(e)}")
                results[bank] = {'status': 'failure', 'error': f'Thread error: {str(e)}'}

    logger.info("Exchange rate refresh completed — results: %s", results)
    return results


def _resolve_rate(service, date):
    """Return the cached rate from *service* for *date*.

    This function simply reads from the database cache.
    To refresh exchange rates, use the /api/exchange-rate/refresh-all endpoint.
    """
    return service.get_exchange_rate(date)


def _serialise_rows(rows):
    """Convert date/Decimal objects in a list of dicts to JSON-safe types."""
    for row in rows:
        for key, val in row.items():
            if hasattr(val, 'isoformat'):
                row[key] = val.isoformat()
            elif isinstance(val, Decimal):
                row[key] = float(val)
    return rows


def log_exchange_rate_refresh(source, status, buy_rate=None, sell_rate=None, error_message=None, duration_ms=None,
                              run_key=None):
    """Write one row to exchange_rate_refresh_logs for a single source attempt."""
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor()
        try:
            cursor.execute("""
                INSERT INTO exchange_rate_refresh_logs
                    (run_key, source, status, buy_rate, sell_rate, error_message, duration_ms)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (run_key, source, status, buy_rate, sell_rate, error_message, duration_ms))
            connection.commit()
        except Error as e:
            logger.error(f"Error writing exchange_rate_refresh_logs: {str(e)}")
        finally:
            cursor.close()
            connection.close()


# ==================================================
# ROUTE HANDLER FUNCTIONS
# ==================================================

def get_exchange_rate_api():
    """
    Get USD to LKR exchange rate for a specific date

    This endpoint:
    1. First checks the exchange_rates table in the database (cache)
    2. If not found, fetches from CBSL and stores in DB for future use
    3. If CBSL fails, returns nearest previous date from DB

    Query Parameters:
        date: Date in YYYY-MM-DD format (required)

    Returns:
        JSON with buy_rate, sell_rate, source, and date
    """
    try:
        date_str = request.args.get('date')
        if not date_str:
            return jsonify({'error': 'Date parameter is required (format: YYYY-MM-DD)'}), 400

        try:
            date = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

        # Check if date is not in the future
        if date > datetime.now():
            return jsonify({'error': 'Cannot fetch exchange rates for future dates'}), 400

        # Fetch exchange rate
        service = get_exchange_rate_service()
        rate = service.get_exchange_rate(date)

        if rate:
            logger.info(f"Exchange rate fetched for {date_str}: {rate}")
            return jsonify(rate), 200
        else:
            return jsonify({'error': 'Exchange rate not available for this date'}), 404

    except Exception as e:
        logger.error(f"Error fetching exchange rate: {str(e)}")
        return jsonify({'error': 'Failed to fetch exchange rate', 'details': str(e)}), 500


def get_month_exchange_rates():
    """
    Fetch USD to LKR exchange rates for an entire month

    Query Parameters:
        year: Year (required)
        month: Month 1-12 (required)

    Returns:
        JSON with rates for each day in the month
    """
    try:
        year_str = request.args.get('year')
        month_str = request.args.get('month')

        if not year_str or not month_str:
            return jsonify({'error': 'Year and month parameters are required'}), 400

        try:
            year = int(year_str)
            month = int(month_str)

            if month < 1 or month > 12:
                return jsonify({'error': 'Month must be between 1 and 12'}), 400

            if year < 2000 or year > datetime.now().year:
                return jsonify({'error': f'Year must be between 2000 and {datetime.now().year}'}), 400

        except ValueError:
            return jsonify({'error': 'Invalid year or month format'}), 400

        # Fetch exchange rates for the month
        service = get_exchange_rate_service()
        rates = service.get_rates_for_month(year, month)

        if rates:
            logger.info(f"Exchange rates fetched for {year}-{month:02d}: {len(rates)} days")
            return jsonify(rates), 200
        else:
            return jsonify({'error': 'No exchange rates available for this month'}), 404

    except Exception as e:
        logger.error(f"Error fetching monthly exchange rates: {str(e)}")
        return jsonify({'error': 'Failed to fetch exchange rates', 'details': str(e)}), 500


def import_exchange_rates_csv():
    """
    Import exchange rates from CSV file

    Expects:
        csv_content: CSV content as string in request body

    Returns:
        JSON with import results
    """
    try:
        from utils.exchange_rate_parser import ExchangeRateParser

        data = request.get_json()
        if not data or 'csv_content' not in data:
            return jsonify({'error': 'CSV content is required in request body'}), 400

        csv_content = data['csv_content']

        # Parse CSV
        parser = ExchangeRateParser()
        rates_dict = parser.parse_csv_content(csv_content)

        if not rates_dict:
            return jsonify({'error': 'No valid exchange rates found in CSV'}), 400

        # Save to database
        service = get_exchange_rate_service()
        success_count = 0
        error_count = 0

        for date_str, rate_data in rates_dict.items():
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                if service.save_exchange_rate(
                        date_obj,
                        rate_data['buy_rate'],
                        rate_data['sell_rate'],
                        source='CSV'
                ):
                    success_count += 1
                else:
                    error_count += 1
            except Exception as e:
                logger.error(f"Error saving rate for {date_str}: {str(e)}")
                error_count += 1

        logger.info(f"CSV import completed: {success_count} successful, {error_count} errors")

        return jsonify({
            'message': f'Successfully imported {success_count} exchange rates',
            'success_count': success_count,
            'error_count': error_count,
            'total_parsed': len(rates_dict)
        }), 200

    except Exception as e:
        logger.error(f"Error importing CSV exchange rates: {str(e)}")
        return jsonify({'error': 'Failed to import exchange rates', 'details': str(e)}), 500


def bulk_cache_exchange_rates():
    """
    Pre-populate exchange rates cache in database for a date range.

    This endpoint efficiently:
    1. Checks which dates in the range are missing from the database
    2. Fetches only missing dates from CBSL and stores them in the DB
    3. Returns summary of caching operation

    Request Body (JSON):
        start_date: Start date (YYYY-MM-DD). Required.
        end_date: End date (YYYY-MM-DD). Required.

    Returns:
        JSON with:
        - already_cached: Number of dates already in DB
        - newly_cached: Number of dates fetched and stored
        - failed: Number of dates that couldn't be fetched
        - message: Summary message
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body is required'}), 400

        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')

        if not start_date_str or not end_date_str:
            return jsonify({'error': 'Both start_date and end_date are required'}), 400

        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError as e:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

        if start_date > end_date:
            return jsonify({'error': 'start_date must be before or equal to end_date'}), 400

        # Don't fetch dates too far in the future
        today = datetime.now().date()
        if start_date > today:
            return jsonify({'error': 'start_date cannot be in the future'}), 400
        if end_date > today:
            end_date = today

        service = get_exchange_rate_service()

        # Step 1: Get all dates that are already in the database (single query)
        connection = get_db_connection()
        cursor = connection.cursor()
        try:
            cursor.execute("""
                           SELECT date
                           FROM exchange_rates
                           WHERE date BETWEEN %s
                             AND %s
                           """, (start_date, end_date))
            existing_dates = {row[0] for row in cursor.fetchall()}
        finally:
            cursor.close()
            connection.close()

        # Step 2: Determine which dates need to be fetched
        current_date = start_date
        dates_to_fetch = []
        while current_date <= end_date:
            if current_date not in existing_dates:
                dates_to_fetch.append(current_date)
            current_date += timedelta(days=1)

        already_cached = len(existing_dates)
        newly_cached = 0
        failed = 0

        logger.info(f"Bulk cache: {already_cached} already in DB, {len(dates_to_fetch)} dates to fetch")

        # Step 3: Fetch and store missing dates
        for date in dates_to_fetch:
            try:
                # This will fetch from CBSL and automatically save to DB
                rate_data = service.get_exchange_rate(date)
                if rate_data and rate_data.get('buy_rate'):
                    newly_cached += 1
                    logger.debug(f"Cached rate for {date}: {rate_data['buy_rate']} LKR")
                else:
                    failed += 1
                    logger.debug(f"Failed to fetch rate for {date}")
            except Exception as e:
                logger.error(f"Error fetching rate for {date}: {str(e)}")
                failed += 1

        total_dates = (end_date - start_date).days + 1
        logger.info(f"Bulk cache completed: {already_cached} existing, {newly_cached} new, {failed} failed")

        return jsonify({
            'already_cached': already_cached,
            'newly_cached': newly_cached,
            'failed': failed,
            'total_dates': total_dates,
            'message': f'Successfully cached {newly_cached} new exchange rates. {already_cached} were already cached.'
        }), 200

    except Exception as e:
        logger.error(f"Error in bulk cache exchange rates: {str(e)}")
        return jsonify({'error': 'Failed to cache exchange rates', 'details': str(e)}), 500


def get_hnb_current_rate():
    """
    Get the latest cached USD to LKR exchange rate from HNB bank.

    To refresh all exchange rates, use GET /api/exchange-rate/refresh-all.

    Returns:
        JSON with buy_rate, sell_rate, date, source, and updated_at
    """
    try:
        service = get_hnb_exchange_rate_service()
        rate_data = _resolve_rate(service, datetime.now().date())

        if rate_data:
            logger.info(f"HNB current rate: {rate_data}")
            return jsonify(rate_data), 200
        else:
            return jsonify({'error': 'HNB rate not yet available.'}), 404

    except Exception as e:
        logger.error(f"Error fetching HNB current rate: {str(e)}")
        return jsonify({'error': 'Failed to fetch exchange rate', 'details': str(e)}), 500


def get_pb_current_rate():
    """
    Get the latest cached USD to LKR exchange rate from People's Bank.

    To refresh all exchange rates, use GET /api/exchange-rate/refresh-all.

    Returns:
        JSON with buy_rate, sell_rate, date, source, and updated_at
    """
    try:
        service = get_pb_exchange_rate_service()
        rate_data = _resolve_rate(service, datetime.now().date())

        if rate_data:
            logger.info(f"PB current rate: {rate_data}")
            return jsonify(rate_data), 200
        else:
            return jsonify({'error': "People's Bank rate not yet available."}), 404

    except Exception as e:
        logger.error(f"Error fetching PB current rate: {str(e)}")
        return jsonify({'error': 'Failed to fetch exchange rate', 'details': str(e)}), 500


def get_sampath_current_rate():
    """
    Get the latest cached USD to LKR exchange rate from Sampath Bank.

    To refresh all exchange rates, use GET /api/exchange-rate/refresh-all.

    Returns:
        JSON with buy_rate, sell_rate, date, source, and updated_at
    """
    try:
        service = get_sampath_exchange_rate_service()
        rate_data = _resolve_rate(service, datetime.now().date())

        if rate_data:
            logger.info(f"Sampath current rate: {rate_data}")
            return jsonify(rate_data), 200
        else:
            return jsonify({'error': 'Sampath Bank rate not yet available.'}), 404

    except Exception as e:
        logger.error(f"Error fetching Sampath current rate: {str(e)}")
        return jsonify({'error': 'Failed to fetch exchange rate', 'details': str(e)}), 500


def refresh_all_rates_manually(log_audit_func):
    """Trigger an immediate refresh of all exchange-rate sources.
    This endpoint executes the refresh synchronously using parallel fetching for optimal performance.
    No authentication required - accessible from cron-job.org and local networks."""
    try:
        # Get allowed origins from environment variable
        backup_origins_env = os.environ.get('BACKUP_ALLOWED_ORIGINS', '')
        allowed_origins = [origin.strip() for origin in backup_origins_env.split(',') if origin.strip()]

        # Get local patterns from environment variable
        local_patterns_env = os.environ.get('BACKUP_LOCAL_PATTERNS', 'localhost,127.0.0.1')
        local_patterns = [pattern.strip() for pattern in local_patterns_env.split(',') if pattern.strip()]

        # Check Origin header (set by browsers and some tools)
        origin = request.headers.get('Origin', '')
        # Check Referer header (fallback for non-browser requests)
        referer = request.headers.get('Referer', '')
        # Check User-Agent to identify cron-job.org
        user_agent = request.headers.get('User-Agent', '')
        # Check remote address
        remote_addr = request.remote_addr or ''

        # Allow if Origin matches production domains
        origin_allowed = any(origin.startswith(allowed) for allowed in allowed_origins)
        # Allow if Referer matches production domains
        referer_allowed = any(referer.startswith(allowed) for allowed in allowed_origins)
        # Allow if User-Agent contains 'cron-job.org'
        user_agent_allowed = 'cron-job.org' in user_agent.lower()
        # Allow if Origin is from local network
        local_origin = any(pattern in origin for pattern in local_patterns) or origin.startswith(
            'http://localhost') or origin.startswith('http://127.0.0.1')
        # Allow if Referer is from local network
        local_referer = any(pattern in referer for pattern in local_patterns) or referer.startswith(
            'http://localhost') or referer.startswith('http://127.0.0.1')
        # Allow if remote address is local
        local_addr = any(remote_addr.startswith(pattern) for pattern in local_patterns)

        if not (origin_allowed or referer_allowed or user_agent_allowed or local_origin or local_referer or local_addr):
            logger.warning(
                f"Unauthorized refresh attempt - Origin: {origin}, Referer: {referer}, UA: {user_agent}, Remote: {remote_addr}")
            return jsonify({
                'error': 'Access denied',
                'message': 'This endpoint is only accessible from authorized sources'
            }), 403

        # Execute refresh synchronously to avoid DB connection issues
        logger.info("Exchange rate refresh started")
        results = refresh_all_exchange_rates(force=True)
        logger.info("Exchange rate refresh completed")

        # Log audit only if user is authenticated (manual refresh)
        if hasattr(request, 'current_user') and request.current_user:
            log_audit_func(request.current_user['user_id'], 'MANUAL_EXCHANGE_RATE_REFRESH')

        logger.info("Exchange rate refresh completed successfully")
        return jsonify({
            'message': 'Exchange rate refresh completed successfully',
            'status': 'completed',
            'results': results,
            'timestamp': datetime.now().isoformat()
        }), 200
    except Exception as e:
        logger.error(f"Error triggering exchange rate refresh: {str(e)}")
        return jsonify({
            'error': 'Exchange rate refresh failed',
            'details': str(e)
        }), 500


def get_all_bank_rates_for_date():
    """
    Get all bank exchange rates for a specific date.
    Returns HNB, People's Bank, Sampath Bank, and CBSL rates from database cache only.

    Query Parameters:
        date: Date in YYYY-MM-DD format (required)
    Returns:
        JSON list of rates for all banks on that date
    """
    try:
        date_str = request.args.get('date')
        if not date_str:
            return jsonify({'error': 'Date is required (YYYY-MM-DD)'}), 400
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD.'}), 400

        rates = []

        # Get HNB rate
        try:
            hnb_service = get_hnb_exchange_rate_service()
            hnb_rate = _resolve_rate(hnb_service, date)
            if hnb_rate:
                hnb_rate['bank'] = 'HNB'
                rates.append(hnb_rate)
        except Exception as e:
            logger.warning(f"Failed to get HNB rate for {date_str}: {str(e)}")

        # Get People's Bank rate
        try:
            pb_service = get_pb_exchange_rate_service()
            pb_rate = _resolve_rate(pb_service, date)
            if pb_rate:
                pb_rate['bank'] = 'PB'
                rates.append(pb_rate)
        except Exception as e:
            logger.warning(f"Failed to get PB rate for {date_str}: {str(e)}")

        # Get Sampath Bank rate
        try:
            sampath_service = get_sampath_exchange_rate_service()
            sampath_rate = _resolve_rate(sampath_service, date)
            if sampath_rate:
                sampath_rate['bank'] = 'SAMPATH'
                rates.append(sampath_rate)
        except Exception as e:
            logger.warning(f"Failed to get Sampath rate for {date_str}: {str(e)}")

        # Get CBSL rate from database only (no scraping)
        try:
            connection = get_db_connection()
            if connection:
                cursor = connection.cursor(dictionary=True)
                try:
                    cursor.execute("""
                        SELECT buy_rate, sell_rate, date, source, updated_at
                        FROM exchange_rates
                        WHERE date = %s AND source IN ('CBSL', 'CBSL_BULK')
                        ORDER BY updated_at DESC
                        LIMIT 1
                    """, (date,))
                    cbsl_row = cursor.fetchone()
                    if cbsl_row:
                        cbsl_rate = {
                            'bank': 'CBSL',
                            'buy_rate': float(cbsl_row['buy_rate']) if isinstance(cbsl_row['buy_rate'], Decimal) else
                            cbsl_row['buy_rate'],
                            'sell_rate': float(cbsl_row['sell_rate']) if isinstance(cbsl_row['sell_rate'], Decimal) else
                            cbsl_row['sell_rate'],
                            'date': cbsl_row['date'].isoformat() if hasattr(cbsl_row['date'], 'isoformat') else str(
                                cbsl_row['date']),
                            'source': cbsl_row['source'],
                            'updated_at': cbsl_row['updated_at'].isoformat() if cbsl_row['updated_at'] and hasattr(
                                cbsl_row['updated_at'], 'isoformat') else str(cbsl_row['updated_at']) if cbsl_row[
                                'updated_at'] else None
                        }
                        rates.append(cbsl_rate)
                finally:
                    cursor.close()
                    connection.close()
        except Exception as e:
            logger.warning(f"Failed to get CBSL rate for {date_str}: {str(e)}")

        if rates:
            return jsonify(rates), 200
        else:
            return jsonify({'error': 'No rates found for this date'}), 404
    except Exception as e:
        logger.error(f"Error fetching all bank rates: {str(e)}")
        return jsonify({'error': 'Failed to fetch bank rates', 'details': str(e)}), 500


def get_bank_rate_for_date(bank_code):
    """
    Get exchange rate for a specific bank and date.
    Query Parameters:
        date: Date in YYYY-MM-DD format (required)
    Returns:
        JSON with buy_rate, sell_rate, date, source, bank
    """
    try:
        date_str = request.args.get('date')
        if not date_str:
            return jsonify({'error': 'Date is required (YYYY-MM-DD)'}), 400
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD.'}), 400

        bank_code_lower = bank_code.lower()
        rate = None

        if bank_code_lower == 'hnb':
            try:
                service = get_hnb_exchange_rate_service()
                rate = _resolve_rate(service, date)
            except Exception as e:
                logger.error(f"Error fetching HNB rate for {date_str}: {str(e)}")
                return jsonify({'error': f'Failed to fetch HNB rate', 'details': str(e)}), 500
        elif bank_code_lower == 'pb':
            try:
                service = get_pb_exchange_rate_service()
                rate = _resolve_rate(service, date)
            except Exception as e:
                logger.error(f"Error fetching PB rate for {date_str}: {str(e)}")
                return jsonify({'error': f'Failed to fetch PB rate', 'details': str(e)}), 500
        elif bank_code_lower == 'sampath':
            try:
                service = get_sampath_exchange_rate_service()
                rate = _resolve_rate(service, date)
            except Exception as e:
                logger.error(f"Error fetching Sampath rate for {date_str}: {str(e)}")
                return jsonify({'error': f'Failed to fetch Sampath rate', 'details': str(e)}), 500
        elif bank_code_lower == 'cbsl':
            try:
                service = get_exchange_rate_service()
                rate = service.get_exchange_rate(date)
                # Guard: reject if the service returned another bank's row
                if rate and rate.get('source') in ('HNB', 'PB', 'SAMPATH'):
                    rate = None
            except Exception as e:
                logger.error(f"Error fetching CBSL rate for {date_str}: {str(e)}")
                return jsonify({'error': f'Failed to fetch CBSL rate', 'details': str(e)}), 500
        else:
            return jsonify({'error': f'Unknown bank code: {bank_code}. Supported: hnb, pb, sampath, cbsl'}), 400

        if rate and isinstance(rate, dict):
            rate['bank'] = bank_code_lower.upper()
            return jsonify(rate), 200
        else:
            return jsonify({'error': f'Exchange rate not available for {bank_code_lower.upper()} on {date_str}'}), 404
    except Exception as e:
        logger.error(f"Error fetching {bank_code} rate: {str(e)}")
        return jsonify({'error': 'Failed to fetch bank rate', 'details': str(e)}), 500


def get_pb_rate_for_date():
    """
    Get People's Bank exchange rate for a specific date from cache.

    Rates are refreshed by external cron job calling the /api/exchange-rate/refresh-all endpoint.

    Query Parameters:
        date: Date in ddmmyyyy format (optional, defaults to today)
              Example: 01022026 for February 1, 2026

    Returns:
        JSON with buy_rate, sell_rate, date, and source

    Example Usage:
        GET /api/exchange-rate/pb?date=01022026
        GET /api/exchange-rate/pb  (returns today's rate)
    """
    try:
        date_str = request.args.get('date')

        if date_str:
            try:
                if len(date_str) != 8:
                    return jsonify({
                        'error': 'Invalid date format. Use ddmmyyyy (e.g., 01022026 for Feb 1, 2026)'
                    }), 400

                date = datetime.strptime(date_str, '%d%m%Y').date()

            except ValueError:
                return jsonify({
                    'error': 'Invalid date format. Use ddmmyyyy (e.g., 01022026 for Feb 1, 2026)'
                }), 400
        else:
            date = datetime.now().date()

        service = get_pb_exchange_rate_service()
        rate = _resolve_rate(service, date)

        if rate:
            logger.info(f"PB rate retrieved for {date_str or 'today'}: {rate}")
            return jsonify(rate), 200
        else:
            return jsonify({
                'error': 'Exchange rate not available for this date'
            }), 404

    except Exception as e:
        logger.error(f"Error getting PB rate: {str(e)}")
        return jsonify({
            'error': 'Failed to get exchange rate',
            'details': str(e)
        }), 500


def get_exchange_rate_trends_all():
    """
    Single endpoint that returns ALL trend data in one response using
    one database connection.  The JS front-end calls this once on page
    load instead of hitting multiple endpoints.

    Query Parameters:
        period:           'daily' | 'weekly' | 'monthly' (default: 'daily')
        months:           history months for main chart  (default: 6, max: 36)
        forecast_days:    days to project forward        (default: 30, max: 90)
        forecast_history: months of data for regression  (default: 3, max: 12)
        comparison_months: months for source comparison  (default: 3, max: 12)

    Returns:
        JSON with keys: trend, forecast, source_comparison, monthly_volatility
    """
    try:
        period = request.args.get('period', 'daily')
        months = min(int(request.args.get('months', 6)), 36)
        forecast_days = min(int(request.args.get('forecast_days', 30)), 90)
        forecast_history = min(int(request.args.get('forecast_history', 3)), 12)
        comp_months = min(int(request.args.get('comparison_months', 3)), 12)

        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = connection.cursor(dictionary=True)
        result = {}

        try:
            # --- 1. Main trend data (daily / weekly / monthly) --------
            if period == 'monthly':
                cursor.execute("""
                    SELECT YEAR(date) AS year, MONTH(date) AS month,
                           MIN(date) AS month_start, MAX(date) AS month_end,
                           ROUND(AVG(buy_rate), 4)  AS buy_rate,
                           ROUND(MIN(buy_rate), 4)   AS min_buy_rate,
                           ROUND(MAX(buy_rate), 4)   AS max_buy_rate,
                           ROUND(STDDEV(buy_rate), 4) AS buy_rate_volatility,
                           COUNT(DISTINCT date) AS trading_days
                    FROM exchange_rates
                    WHERE date >= DATE_SUB(CURDATE(), INTERVAL %s MONTH)
                    GROUP BY YEAR(date), MONTH(date)
                    ORDER BY YEAR(date), MONTH(date)
                """, (months,))
            elif period == 'weekly':
                cursor.execute("""
                    SELECT MIN(date) AS week_start, MAX(date) AS week_end,
                           YEAR(date) AS year, WEEK(date, 1) AS week_number,
                           ROUND(AVG(buy_rate), 4) AS buy_rate,
                           ROUND(MIN(buy_rate), 4) AS min_buy_rate,
                           ROUND(MAX(buy_rate), 4) AS max_buy_rate,
                           COUNT(DISTINCT date) AS trading_days
                    FROM exchange_rates
                    WHERE date >= DATE_SUB(CURDATE(), INTERVAL %s MONTH)
                    GROUP BY YEAR(date), WEEK(date, 1)
                    ORDER BY YEAR(date), WEEK(date, 1)
                """, (months,))
            else:  # daily
                cursor.execute("""
                    SELECT date,
                           ROUND(AVG(buy_rate), 4) AS buy_rate,
                           COUNT(DISTINCT source) AS source_count
                    FROM exchange_rates
                    WHERE date >= DATE_SUB(CURDATE(), INTERVAL %s MONTH)
                    GROUP BY date
                    ORDER BY date
                """, (months,))

            result['trend'] = _serialise_rows(cursor.fetchall())
            result['period'] = period
            result['months'] = months

            # --- 2. Forecast (linear regression on daily avg buy_rate) -
            cursor.execute("""
                SELECT date,
                       ROUND(AVG(buy_rate), 4) AS buy_rate
                FROM exchange_rates
                WHERE date >= DATE_SUB(CURDATE(), INTERVAL %s MONTH)
                GROUP BY date
                ORDER BY date
            """, (forecast_history,))
            fc_history = _serialise_rows(cursor.fetchall())

            if len(fc_history) >= 7:
                base_date = datetime.strptime(fc_history[0]['date'], '%Y-%m-%d').date()
                xs = [(datetime.strptime(r['date'], '%Y-%m-%d').date() - base_date).days for r in fc_history]
                ys = [r['buy_rate'] for r in fc_history]
                n = len(xs)
                sum_x = sum(xs)
                sum_y = sum(ys)
                sum_xy = sum(x * y for x, y in zip(xs, ys))
                sum_xx = sum(x * x for x in xs)
                denom = n * sum_xx - sum_x * sum_x
                if denom == 0:
                    slope, intercept = 0.0, sum_y / n
                else:
                    slope = (n * sum_xy - sum_x * sum_y) / denom
                    intercept = (sum_y - slope * sum_x) / n

                y_mean = sum_y / n
                ss_tot = sum((y - y_mean) ** 2 for y in ys)
                ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
                r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
                res_std = (sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys)) / max(n - 2, 1)) ** 0.5

                last_date = datetime.strptime(fc_history[-1]['date'], '%Y-%m-%d').date()
                last_x = xs[-1]
                fc_points = []
                for i in range(1, forecast_days + 1):
                    fx = last_x + i
                    predicted = slope * fx + intercept
                    fc_points.append({
                        'date': (last_date + timedelta(days=i)).isoformat(),
                        'predicted_buy_rate': round(predicted, 4),
                        'upper_bound': round(predicted + 1.96 * res_std, 4),
                        'lower_bound': round(predicted - 1.96 * res_std, 4),
                    })

                result['forecast'] = {
                    'history': fc_history,
                    'points': fc_points,
                    'model': {
                        'slope_per_day': round(slope, 6),
                        'intercept': round(intercept, 4),
                        'r_squared': round(r_squared, 4),
                        'residual_std': round(res_std, 4),
                        'data_points': n,
                    }
                }
            else:
                result['forecast'] = None

            # --- 3. Source comparison (buy rate per bank) ---------------
            cursor.execute("""
                SELECT date, source, buy_rate
                FROM exchange_rates
                WHERE date >= DATE_SUB(CURDATE(), INTERVAL %s MONTH)
                ORDER BY date, source
            """, (comp_months,))
            comp_rows = cursor.fetchall()

            sources = {}
            for row in comp_rows:
                src = row['source']
                if src not in sources:
                    sources[src] = []
                sources[src].append({
                    'date': row['date'].isoformat() if hasattr(row['date'], 'isoformat') else row['date'],
                    'buy_rate': float(row['buy_rate']) if isinstance(row['buy_rate'], Decimal) else row['buy_rate'],
                })
            result['source_comparison'] = sources

            # --- 4. Monthly volatility (last 12 months, buy rate) ------
            cursor.execute("""
                SELECT YEAR(date) AS year, MONTH(date) AS month,
                       ROUND(STDDEV(buy_rate), 4) AS buy_rate_volatility,
                       ROUND(MAX(buy_rate) - MIN(buy_rate), 4) AS month_range,
                       COUNT(DISTINCT date) AS trading_days
                FROM exchange_rates
                WHERE date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                GROUP BY YEAR(date), MONTH(date)
                ORDER BY YEAR(date), MONTH(date)
            """)
            result['monthly_volatility'] = _serialise_rows(cursor.fetchall())

            return jsonify(result), 200

        finally:
            cursor.close()
            connection.close()

    except Exception as e:
        logger.error(f"Error fetching exchange rate trends: {str(e)}")
        return jsonify({'error': 'Failed to fetch trend data', 'details': str(e)}), 500


def get_exchange_rate_ai_insights():
    """
    Get AI-powered insights about the best time to exchange currency.
    Uses Gemini AI to analyze recent exchange rate trends and provide recommendations.

    Query Parameters:
        months: Number of months of history to analyze (default: 3, max: 12)
        currency_from: Source currency (default: USD)
        currency_to: Target currency (default: LKR)
        transaction_type: Type of transaction - 'salary_exchange', 'investment', 'general' (default: salary_exchange)

    Returns:
        JSON with AI analysis including:
        - recommendation: Best time to exchange
        - trend: Trend analysis
        - insights: Detailed insights
        - forecast: Short-term forecast
        - statistics: Key statistics
    """
    try:
        months = min(int(request.args.get('months', 3)), 12)
        currency_from = request.args.get('currency_from', 'USD')
        currency_to = request.args.get('currency_to', 'LKR')
        transaction_type = request.args.get('transaction_type', 'salary_exchange')

        # Get Gemini Exchange Analyzer instance
        analyzer = get_gemini_exchange_analyzer()
        if not analyzer:
            return jsonify({
                'error': 'AI service not available',
                'message': 'Gemini API is not configured. Please check your GEMINI_API_KEY.'
            }), 503

        # Fetch exchange rate data from database
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = connection.cursor(dictionary=True)

        try:
            # Get daily buy rates per bank (CBSL, PB, HNB) for the specified period
            cursor.execute("""
                SELECT date, source, buy_rate
                FROM exchange_rates
                WHERE date >= DATE_SUB(CURDATE(), INTERVAL %s MONTH)
                  AND source IN ('CBSL', 'PB', 'HNB')
                ORDER BY date, source
            """, (months,))

            all_data = cursor.fetchall()

            logger.info(f"✅ Fetched {len(all_data)} exchange rate records from YOUR database")

            if not all_data or len(all_data) < 6:
                return jsonify({
                    'error': 'Insufficient data',
                    'message': 'Not enough historical data available for analysis.'
                }), 400

            # Organize data by bank
            bank_data = {'CBSL': [], 'PB': [], 'HNB': []}
            for row in all_data:
                source = row['source']
                if source in bank_data:
                    bank_data[source].append({
                        'date': row['date'].isoformat() if hasattr(row['date'], 'isoformat') else str(row['date']),
                        'rate': float(row['buy_rate']) if isinstance(row['buy_rate'], Decimal) else row['buy_rate']
                    })

            # Get current rates for each bank (latest date)
            current_rates = {}
            for bank, data in bank_data.items():
                if data:
                    current_rates[bank] = data[-1]['rate']

            # Log data summary for verification
            logger.info(f"📊 Data organized by bank:")
            logger.info(
                f"  - HNB: {len(bank_data['HNB'])} data points, current rate: {current_rates.get('HNB', 'N/A')}")
            logger.info(
                f"  - CBSL: {len(bank_data['CBSL'])} data points, current rate: {current_rates.get('CBSL', 'N/A')}")
            logger.info(f"  - PB: {len(bank_data['PB'])} data points, current rate: {current_rates.get('PB', 'N/A')}")

            # Log sample of recent HNB data (your bank)
            if bank_data['HNB']:
                recent_hnb = bank_data['HNB'][-5:]
                logger.info(f"📈 Recent HNB rates (last 5 days): {recent_hnb}")

            # Call AI analysis with multi-bank data
            logger.info(f"🤖 Sending YOUR database data to AI for analysis...")
            logger.info(f"📋 Transaction type: {transaction_type}")
            analysis = analyzer.analyze_multi_bank_patterns(
                bank_data=bank_data,
                current_rates=current_rates,
                user_bank='HNB',
                currency_from=currency_from,
                currency_to=currency_to,
                transaction_type=transaction_type
            )

            # Add timestamp and transaction context
            analysis['generated_at'] = datetime.now().isoformat()
            analysis['data_period_months'] = months
            analysis['transaction_type'] = transaction_type
            analysis['user_context'] = {
                'bank': 'HNB',
                'transaction_type': transaction_type,
                'currency_direction': f'{currency_from} → {currency_to}'
            }

            return jsonify(analysis), 200

        finally:
            cursor.close()
            connection.close()

    except ValueError as e:
        logger.error(f"Invalid parameter in AI insights request: {str(e)}")
        return jsonify({'error': 'Invalid parameters', 'details': str(e)}), 400
    except Exception as e:
        logger.error(f"Error generating AI insights: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to generate AI insights', 'details': str(e)}), 500


def get_intraday_refresh_logs():
    """
    Fetch intraday exchange rate refresh logs from exchange_rate_refresh_logs table.
    Groups logs by run_key to show trends within the day from multiple refresh cycles.

    Query Parameters:
        date: YYYY-MM-DD format (default: today)
        limit_runs: Maximum number of runs to return (default: 20, max: 50)

    Returns:
        JSON with array of runs, each containing timestamp and bank rates
    """
    try:
        target_date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
        limit_runs = min(int(request.args.get('limit_runs', 20)), 50)

        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = connection.cursor(dictionary=True)

        try:
            # Fetch all logs for the target date, grouped by run_key
            cursor.execute("""
                SELECT 
                    run_key,
                    source,
                    status,
                    buy_rate,
                    sell_rate,
                    error_message,
                    created_at
                FROM exchange_rate_refresh_logs
                WHERE DATE(created_at) = %s
                  AND run_key IS NOT NULL
                ORDER BY created_at DESC, run_key, source
                LIMIT %s
            """, (target_date, limit_runs * 10))  # Fetch more rows to account for multiple sources per run

            rows = cursor.fetchall()

            if not rows:
                return jsonify({'date': target_date, 'runs': []}), 200

            # Group logs by run_key
            runs_dict = {}
            for row in rows:
                run_key = row['run_key']
                if run_key not in runs_dict:
                    # Database stores timestamps in UTC, append 'Z' to indicate UTC timezone
                    created_at = row['created_at']
                    if hasattr(created_at, 'isoformat'):
                        timestamp_str = created_at.isoformat()
                        # Append 'Z' if not already present to indicate UTC
                        if not timestamp_str.endswith('Z') and '+' not in timestamp_str:
                            timestamp_str += 'Z'
                    else:
                        timestamp_str = str(created_at)

                    runs_dict[run_key] = {
                        'run_key': run_key,
                        'timestamp': timestamp_str,
                        'banks': {}
                    }

                source = row['source']
                runs_dict[run_key]['banks'][source] = {
                    'status': row['status'],
                    'buy_rate': float(row['buy_rate']) if row['buy_rate'] else None,
                    'sell_rate': float(row['sell_rate']) if row['sell_rate'] else None,
                    'error_message': row['error_message']
                }

            # Convert to sorted list (most recent first) and limit
            runs_list = sorted(runs_dict.values(), key=lambda x: x['timestamp'], reverse=True)[:limit_runs]

            return jsonify({
                'date': target_date,
                'runs': runs_list,
                'total_runs': len(runs_list)
            }), 200

        finally:
            cursor.close()
            connection.close()

    except Exception as e:
        logger.error(f"Error fetching intraday refresh logs: {str(e)}")
        return jsonify({'error': 'Failed to fetch intraday logs', 'details': str(e)}), 500


# ==================================================
# ROUTE REGISTRATION FUNCTION
# ==================================================

def register_exchange_rate_routes(app, login_required, admin_required, token_required, log_audit):
    """
    Register all exchange rate routes with the Flask app

    Args:
        app: Flask application instance
        login_required: Login required decorator
        admin_required: Admin required decorator
        token_required: Token required decorator
        log_audit: Audit logging function
    """

    @app.route('/api/exchange-rate', methods=['GET'])
    @login_required
    def exchange_rate_api():
        return get_exchange_rate_api()

    @app.route('/api/exchange-rate/month', methods=['GET'])
    @login_required
    def month_exchange_rates():
        return get_month_exchange_rates()

    @app.route('/api/exchange-rate/import-csv', methods=['POST'])
    @login_required
    def exchange_rates_csv():
        return import_exchange_rates_csv()

    @app.route('/api/exchange-rate/bulk-cache', methods=['POST'])
    @login_required
    def bulk_cache_rates():
        return bulk_cache_exchange_rates()

    @app.route('/api/exchange-rate/hnb/current', methods=['GET'])
    @login_required
    def hnb_current_rate():
        return get_hnb_current_rate()

    @app.route('/api/exchange-rate/pb/current', methods=['GET'])
    @login_required
    def pb_current_rate():
        return get_pb_current_rate()

    @app.route('/api/exchange-rate/sampath/current', methods=['GET'])
    @login_required
    def sampath_current_rate():
        return get_sampath_current_rate()

    @app.route('/api/exchange-rate/refresh-all', methods=['GET'])
    def refresh_all_rates():
        return refresh_all_rates_manually(log_audit)

    @app.route('/api/exchange-rate/banks', methods=['GET'])
    @token_required
    def all_bank_rates_for_date():
        return get_all_bank_rates_for_date()

    @app.route('/api/exchange-rate/bank/<bank_code>', methods=['GET'])
    @token_required
    def bank_rate_for_date(bank_code):
        return get_bank_rate_for_date(bank_code)

    @app.route('/api/exchange-rate/pb', methods=['GET'])
    @token_required
    def pb_rate_for_date():
        return get_pb_rate_for_date()

    @app.route('/api/exchange-rate/trends/all', methods=['GET'])
    @login_required
    def exchange_rate_trends_all():
        return get_exchange_rate_trends_all()

    @app.route('/api/exchange-rate/ai-insights', methods=['GET'])
    @login_required
    def exchange_rate_ai_insights():
        return get_exchange_rate_ai_insights()

    @app.route('/api/exchange-rate/intraday-logs', methods=['GET'])
    @login_required
    def intraday_refresh_logs():
        return get_intraday_refresh_logs()

    logger.info("Exchange rate routes registered successfully")
