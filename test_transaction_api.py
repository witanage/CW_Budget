#!/usr/bin/env python3
"""
Test script for the Transaction API endpoint with token authentication.

This script demonstrates:
1. How to generate an authentication token
2. How to use the token to create a transaction

Prerequisites:
- The Flask application must be running on http://localhost:5003
- You need valid user credentials (username and password)
"""

import requests
import json
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:5003"
USERNAME = "your_username"  # Replace with your username or email
PASSWORD = "your_password"  # Replace with your password

def get_token(username, password):
    """
    Generate authentication token using username and password.

    Returns:
        str: JWT token if successful, None otherwise
    """
    print("Step 1: Generating authentication token...")

    token_url = f"{BASE_URL}/api/auth/token"
    payload = {
        "username": username,
        "password": password
    }

    try:
        response = requests.post(token_url, json=payload)

        if response.status_code == 200:
            data = response.json()
            token = data.get('token')
            print(f"✓ Token generated successfully!")
            print(f"  Token: {token[:50]}...")
            print(f"  Expires at: {data.get('expires_at')}")
            print(f"  User: {data.get('user', {}).get('username')}")
            return token
        else:
            print(f"✗ Failed to generate token: {response.status_code}")
            print(f"  Error: {response.json()}")
            return None

    except Exception as e:
        print(f"✗ Error generating token: {str(e)}")
        return None


def create_transaction(token, description, credit):
    """
    Create a new transaction using the authentication token.
    The transaction date is automatically set to today's date.

    Args:
        token (str): JWT authentication token
        description (str): Transaction description
        credit (float): Expense amount

    Returns:
        dict: Response data if successful, None otherwise
    """
    print(f"\nStep 2: Creating transaction...")
    print(f"  Description: {description}")
    print(f"  Credit (Expense): {credit}")
    print(f"  Date: Today (automatically set)")

    transaction_url = f"{BASE_URL}/api/transactions/create"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "description": description,
        "credit": credit
    }

    try:
        response = requests.post(transaction_url, headers=headers, json=payload)

        if response.status_code == 201:
            data = response.json()
            print(f"✓ Transaction created successfully!")
            print(f"  Transaction ID: {data.get('transaction_id')}")
            print(f"  Message: {data.get('message')}")
            return data
        else:
            print(f"✗ Failed to create transaction: {response.status_code}")
            print(f"  Error: {response.json()}")
            return None

    except Exception as e:
        print(f"✗ Error creating transaction: {str(e)}")
        return None


def main():
    """Main test function."""
    print("=" * 60)
    print("Transaction API Test")
    print("=" * 60)

    # Step 1: Get authentication token
    token = get_token(USERNAME, PASSWORD)

    if not token:
        print("\n✗ Cannot proceed without a valid token.")
        return

    # Step 2: Create a transaction (date will be today)
    result = create_transaction(
        token=token,
        description="API Test - Coffee",
        credit=5.50
    )

    if result:
        print("\n" + "=" * 60)
        print("✓ Test completed successfully!")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("✗ Test failed!")
        print("=" * 60)


if __name__ == "__main__":
    print("\nNOTE: Make sure to update USERNAME and PASSWORD in the script before running!")
    print("      Also ensure the Flask application is running on http://localhost:5003\n")

    # Uncomment the line below to run the test
    # main()

    print("To run the test, uncomment the main() call at the end of this script.")
