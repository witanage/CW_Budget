"""
Exchange Rate Parser - Parse CSV data from CBSL
"""
import csv
import io
from datetime import datetime
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)

class ExchangeRateParser:
    """Parse exchange rate data from CSV format"""

    @staticmethod
    def parse_csv_content(csv_content: str) -> Dict[str, Dict[str, float]]:
        """
        Parse CSV content from CBSL

        Expected CSV format:
        Date,Buy Rate (LKR),Sell Rate (LKR)
        2025-11-21,304.2758,311.8332
        ...

        Args:
            csv_content: CSV content as string

        Returns:
            Dictionary mapping date strings to rate dictionaries
        """
        rates = {}

        try:
            # Parse CSV content
            csv_reader = csv.DictReader(io.StringIO(csv_content))

            for row in csv_reader:
                try:
                    # Handle different possible column names
                    date_str = None
                    buy_rate = None
                    sell_rate = None

                    # Find date column
                    for key in row.keys():
                        key_lower = key.lower().strip()
                        if 'date' in key_lower:
                            date_str = row[key].strip()
                        elif 'buy' in key_lower and 'rate' in key_lower:
                            buy_rate = float(row[key].strip())
                        elif 'sell' in key_lower and 'rate' in key_lower:
                            sell_rate = float(row[key].strip())

                    if date_str and buy_rate and sell_rate:
                        # Validate and normalize date format
                        try:
                            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                            normalized_date = date_obj.strftime('%Y-%m-%d')

                            rates[normalized_date] = {
                                'buy_rate': buy_rate,
                                'sell_rate': sell_rate,
                                'date': normalized_date
                            }
                        except ValueError:
                            logger.warning(f"Invalid date format: {date_str}")
                            continue

                except (ValueError, KeyError) as e:
                    logger.warning(f"Error parsing CSV row: {e}")
                    continue

            logger.info(f"Successfully parsed {len(rates)} exchange rates from CSV")
            return rates

        except Exception as e:
            logger.error(f"Error parsing CSV content: {str(e)}")
            return {}

    @staticmethod
    def get_rate_for_date(rates_dict: Dict[str, Dict[str, float]],
                         target_date: datetime) -> Dict[str, float]:
        """
        Get exchange rate for a specific date from parsed rates

        If exact date not found, returns the nearest previous date

        Args:
            rates_dict: Dictionary of rates returned by parse_csv_content
            target_date: Target date to find rate for

        Returns:
            Rate dictionary or None if not found
        """
        target_date_str = target_date.strftime('%Y-%m-%d')

        # Check for exact match
        if target_date_str in rates_dict:
            return rates_dict[target_date_str]

        # Find nearest previous date
        available_dates = sorted(rates_dict.keys(), reverse=True)
        for date_str in available_dates:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            if date_obj <= target_date:
                rate = rates_dict[date_str].copy()
                rate['note'] = f'Rate from {date_str} (nearest available date)'
                return rate

        return None
