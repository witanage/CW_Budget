#!/usr/bin/env python3
"""
Helper script to import CBSL exchange rate CSV data into the database

Usage:
1. Download CSV from: https://www.cbsl.gov.lk/cbsl_custom/exratestt/exrates_resultstt.php
   - Select date range (e.g., "1 Year")
   - Click "CSV" button to download

2. Run this script:
   python import_cbsl_csv.py path/to/downloaded.csv

Example:
   python import_cbsl_csv.py exchange_rates.csv
"""
import sys
import os
from datetime import datetime

# Add parent directory to path to import from services and utils
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.exchange_rate_service import get_exchange_rate_service
from utils.exchange_rate_parser import ExchangeRateParser

def import_csv_file(file_path: str):
    """Import CSV file into the database"""

    if not os.path.exists(file_path):
        print(f"Error: File '{file_path}' not found")
        return False

    print(f"Importing exchange rates from: {file_path}")
    print("-" * 60)

    # Read CSV file
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            csv_content = f.read()
    except Exception as e:
        print(f"Error reading file: {str(e)}")
        return False

    # Parse CSV
    print("Parsing CSV data...")
    parser = ExchangeRateParser()
    rates_dict = parser.parse_csv_content(csv_content)

    if not rates_dict:
        print("Error: No valid exchange rates found in CSV file")
        return False

    print(f"Found {len(rates_dict)} exchange rates in CSV")

    # Get date range
    dates = sorted(rates_dict.keys())
    print(f"Date range: {dates[0]} to {dates[-1]}")
    print()

    # Confirm import
    response = input(f"Import {len(rates_dict)} exchange rates? (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        print("Import cancelled")
        return False

    # Import to database
    print("\nImporting to database...")
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
                if success_count % 50 == 0:  # Progress indicator
                    print(f"  Imported {success_count} rates...")
            else:
                error_count += 1
        except Exception as e:
            print(f"  Error importing rate for {date_str}: {str(e)}")
            error_count += 1

    print()
    print("-" * 60)
    print(f"Import complete!")
    print(f"  Successfully imported: {success_count}")
    print(f"  Errors: {error_count}")
    print(f"  Total processed: {len(rates_dict)}")

    return success_count > 0

def main():
    """Main function"""

    print("=" * 60)
    print("CBSL Exchange Rate CSV Importer")
    print("=" * 60)
    print()

    if len(sys.argv) < 2:
        print("Usage: python import_cbsl_csv.py <csv_file_path>")
        print()
        print("Example:")
        print("  python import_cbsl_csv.py exchange_rates.csv")
        print()
        print("Instructions:")
        print("1. Visit: https://www.cbsl.gov.lk/cbsl_custom/exratestt/exrates_resultstt.php")
        print("2. Select date range (e.g., '1 Year')")
        print("3. Click 'CSV' button to download")
        print("4. Run this script with the downloaded CSV file")
        sys.exit(1)

    csv_file = sys.argv[1]
    success = import_csv_file(csv_file)

    if success:
        print()
        print("✓ Import successful!")
        print()
        print("You can now use the date picker in the tax section to automatically")
        print("fetch exchange rates from the imported data.")
    else:
        print()
        print("✗ Import failed. Please check the error messages above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
