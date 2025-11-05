#!/usr/bin/env python3
"""
Database Migration Script
Apply the balance column removal migration
"""

import os
import sys
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

# Add parent directory to path to import from main app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
load_dotenv()

def get_db_connection():
    """Create a database connection."""
    try:
        connection = mysql.connector.connect(
            host=os.environ.get('DB_HOST'),
            port=int(os.environ.get('DB_PORT', 3306)),
            database=os.environ.get('DB_NAME'),
            user=os.environ.get('DB_USER'),
            password=os.environ.get('DB_PASSWORD'),
            charset='utf8mb4',
            use_unicode=True
        )
        return connection
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

def apply_migration():
    """Apply the migration to remove balance column."""
    print("=" * 60)
    print("Database Migration: Remove Balance Column")
    print("=" * 60)
    print("\nThis migration will:")
    print("  - Remove the 'balance' column from the transactions table")
    print("  - Balance will be calculated on frontend in real-time")
    print("\nWARNING: This is a destructive operation!")
    print("Make sure you have a database backup before proceeding.")
    print("=" * 60)

    response = input("\nDo you want to continue? (yes/no): ").strip().lower()
    if response != 'yes':
        print("Migration cancelled.")
        return

    print("\nConnecting to database...")
    connection = get_db_connection()

    if not connection:
        print("❌ Failed to connect to database. Check your .env configuration.")
        return

    try:
        cursor = connection.cursor()

        print("✓ Connected to database")
        print("\nApplying migration...")

        # Check if balance column exists
        cursor.execute("""
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s
            AND TABLE_NAME = 'transactions'
            AND COLUMN_NAME = 'balance'
        """, (os.environ.get('DB_NAME'),))

        column_exists = cursor.fetchone()[0] > 0

        if not column_exists:
            print("ℹ  Balance column does not exist. Migration already applied or not needed.")
            return

        # Drop the balance column
        cursor.execute("ALTER TABLE transactions DROP COLUMN balance")
        connection.commit()

        print("✓ Balance column removed successfully")
        print("\n✅ Migration completed successfully!")
        print("\nBalance will now be calculated on frontend in real-time.")

    except Error as e:
        print(f"\n❌ Migration failed: {e}")
        connection.rollback()
    finally:
        cursor.close()
        connection.close()
        print("\nDatabase connection closed.")

if __name__ == '__main__':
    apply_migration()
