#!/usr/bin/env python3
"""
Database Migration Script
Apply the admin features migration
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
    """Apply the admin features migration."""
    print("=" * 60)
    print("Database Migration: Add Admin Features")
    print("=" * 60)
    print("\nThis migration will:")
    print("  - Add 'is_admin' column to users table")
    print("  - Add 'is_active' column to users table")
    print("  - Add 'last_login' column to users table")
    print("  - Add 'created_at' column to users table")
    print("  - Add 'updated_at' column to users table")
    print("  - Create 'audit_logs' table for admin actions")
    print("  - Set the first user as admin")
    print("\nThis is a non-destructive operation.")
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

        # Check if is_admin column already exists
        cursor.execute("""
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s
            AND TABLE_NAME = 'users'
            AND COLUMN_NAME = 'is_admin'
        """, (os.environ.get('DB_NAME'),))

        column_exists = cursor.fetchone()[0] > 0

        if column_exists:
            print("ℹ  Admin features already exist. Migration already applied.")
            return

        # Read and execute the SQL migration file
        migration_file = os.path.join(os.path.dirname(__file__), 'add_admin_features.sql')

        with open(migration_file, 'r') as f:
            sql_commands = f.read()

        # Split commands by semicolon and execute each
        for command in sql_commands.split(';'):
            command = command.strip()
            if command and not command.startswith('--'):
                try:
                    cursor.execute(command)
                    connection.commit()
                except Error as e:
                    # Ignore "already exists" errors for tables
                    if 'already exists' not in str(e).lower():
                        raise

        print("✓ is_admin column added")
        print("✓ is_active column added")
        print("✓ last_login column added")
        print("✓ created_at column added")
        print("✓ updated_at column added")
        print("✓ audit_logs table created")
        print("✓ First user set as admin")

        print("\n✅ Migration completed successfully!")
        print("\nAdmin features have been enabled.")
        print("The first user in the database has been granted admin privileges.")

    except Error as e:
        print(f"\n❌ Migration failed: {e}")
        connection.rollback()
    finally:
        cursor.close()
        connection.close()
        print("\nDatabase connection closed.")

if __name__ == '__main__':
    apply_migration()
