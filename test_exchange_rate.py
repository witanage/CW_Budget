#!/usr/bin/env python3
"""
Test script for exchange rate service
"""
from datetime import datetime
from exchange_rate_service import get_exchange_rate_service

def test_exchange_rate_service():
    """Test the exchange rate service"""
    service = get_exchange_rate_service()

    # Test with today's date
    print("Testing exchange rate service...")
    print("-" * 50)

    # Test 1: Get rate for today
    today = datetime.now()
    print(f"\nTest 1: Fetching rate for today ({today.strftime('%Y-%m-%d')})")
    rate = service.get_exchange_rate(today)
    if rate:
        print(f"✓ Success!")
        print(f"  Buy Rate: {rate['buy_rate']} LKR")
        print(f"  Sell Rate: {rate['sell_rate']} LKR")
        print(f"  Date: {rate['date']}")
        if 'note' in rate:
            print(f"  Note: {rate['note']}")
    else:
        print("✗ Failed to fetch rate")

    # Test 2: Get rate for a specific date
    test_date = datetime(2025, 11, 15)
    print(f"\nTest 2: Fetching rate for {test_date.strftime('%Y-%m-%d')}")
    rate = service.get_exchange_rate(test_date)
    if rate:
        print(f"✓ Success!")
        print(f"  Buy Rate: {rate['buy_rate']} LKR")
        print(f"  Sell Rate: {rate['sell_rate']} LKR")
        print(f"  Date: {rate['date']}")
        if 'note' in rate:
            print(f"  Note: {rate['note']}")
    else:
        print("✗ Failed to fetch rate")

    # Test 3: Get rate for a weekend (should return nearest previous date)
    weekend_date = datetime(2025, 11, 16)  # This might be a weekend
    print(f"\nTest 3: Fetching rate for {weekend_date.strftime('%Y-%m-%d')} (testing nearest date fallback)")
    rate = service.get_exchange_rate(weekend_date)
    if rate:
        print(f"✓ Success!")
        print(f"  Buy Rate: {rate['buy_rate']} LKR")
        print(f"  Sell Rate: {rate['sell_rate']} LKR")
        print(f"  Date: {rate['date']}")
        if 'note' in rate:
            print(f"  Note: {rate['note']}")
    else:
        print("✗ Failed to fetch rate")

    print("\n" + "-" * 50)
    print("Testing complete!")

if __name__ == "__main__":
    test_exchange_rate_service()
