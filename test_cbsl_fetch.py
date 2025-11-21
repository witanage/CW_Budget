#!/usr/bin/env python3
"""
Test script for CBSL exchange rate fetching (without database)
"""
from datetime import datetime
from exchange_rate_service import ExchangeRateService

def test_cbsl_fetch():
    """Test the CBSL fetching directly without database"""
    service = ExchangeRateService()

    print("Testing CBSL exchange rate fetching...")
    print("-" * 50)

    # Test 1: Get rate for today
    today = datetime.now()
    print(f"\nTest 1: Fetching rate directly from CBSL for today ({today.strftime('%Y-%m-%d')})")
    try:
        rate = service._fetch_from_cbsl(today)
        if rate:
            print(f"✓ Success!")
            print(f"  Buy Rate: {rate['buy_rate']} LKR")
            print(f"  Sell Rate: {rate['sell_rate']} LKR")
            print(f"  Date: {rate['date']}")
            if 'note' in rate:
                print(f"  Note: {rate['note']}")
        else:
            print("✗ Failed to fetch rate (this may be a weekend/holiday)")
    except Exception as e:
        print(f"✗ Error: {str(e)}")

    # Test 2: Get rate for a specific recent weekday
    test_date = datetime(2025, 11, 20)  # Thursday
    print(f"\nTest 2: Fetching rate directly from CBSL for {test_date.strftime('%Y-%m-%d')}")
    try:
        rate = service._fetch_from_cbsl(test_date)
        if rate:
            print(f"✓ Success!")
            print(f"  Buy Rate: {rate['buy_rate']} LKR")
            print(f"  Sell Rate: {rate['sell_rate']} LKR")
            print(f"  Date: {rate['date']}")
            if 'note' in rate:
                print(f"  Note: {rate['note']}")
        else:
            print("✗ Failed to fetch rate")
    except Exception as e:
        print(f"✗ Error: {str(e)}")

    # Test 3: Get rate for a specific date
    test_date = datetime(2025, 11, 15)  # Friday
    print(f"\nTest 3: Fetching rate directly from CBSL for {test_date.strftime('%Y-%m-%d')}")
    try:
        rate = service._fetch_from_cbsl(test_date)
        if rate:
            print(f"✓ Success!")
            print(f"  Buy Rate: {rate['buy_rate']} LKR")
            print(f"  Sell Rate: {rate['sell_rate']} LKR")
            print(f"  Date: {rate['date']}")
            if 'note' in rate:
                print(f"  Note: {rate['note']}")
        else:
            print("✗ Failed to fetch rate")
    except Exception as e:
        print(f"✗ Error: {str(e)}")

    print("\n" + "-" * 50)
    print("Testing complete!")

if __name__ == "__main__":
    test_cbsl_fetch()
