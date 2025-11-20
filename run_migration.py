#!/usr/bin/env python3
"""
Run database migration to add is_active column to tax_calculations table
"""

import os
import sys
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def run_migration():
    """Apply the migration to add is_active column"""

    # Database connection parameters
    db_config = {
        'host': os.getenv('DB_HOST'),
        'port': int(os.getenv('DB_PORT', 3306)),
        'database': os.getenv('DB_NAME'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD')
    }

    print("Connecting to database...")
    print(f"Host: {db_config['host']}:{db_config['port']}")
    print(f"Database: {db_config['database']}")

    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()

        print("\n1. Checking if is_active column already exists...")
        cursor.execute("""
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s
            AND TABLE_NAME = 'tax_calculations'
            AND COLUMN_NAME = 'is_active'
        """, (db_config['database'],))

        column_exists = cursor.fetchone()[0] > 0

        if column_exists:
            print("   ✓ Column 'is_active' already exists. Skipping column creation.")
        else:
            print("   Adding is_active column...")
            cursor.execute("""
                ALTER TABLE tax_calculations
                ADD COLUMN is_active BOOLEAN DEFAULT FALSE
                COMMENT 'Indicates if this is the active calculation for the assessment year'
            """)
            connection.commit()
            print("   ✓ Column 'is_active' added successfully!")

        print("\n2. Checking if index exists...")
        cursor.execute("""
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA = %s
            AND TABLE_NAME = 'tax_calculations'
            AND INDEX_NAME = 'idx_user_assessment_active'
        """, (db_config['database'],))

        index_exists = cursor.fetchone()[0] > 0

        if index_exists:
            print("   ✓ Index 'idx_user_assessment_active' already exists. Skipping index creation.")
        else:
            print("   Creating index idx_user_assessment_active...")
            cursor.execute("""
                CREATE INDEX idx_user_assessment_active
                ON tax_calculations(user_id, assessment_year, is_active)
            """)
            connection.commit()
            print("   ✓ Index created successfully!")

        print("\n3. Setting most recent calculation per user/year as active...")
        cursor.execute("""
            UPDATE tax_calculations t1
            INNER JOIN (
                SELECT id,
                       ROW_NUMBER() OVER (PARTITION BY user_id, assessment_year ORDER BY created_at DESC) as rn
                FROM tax_calculations
            ) t2 ON t1.id = t2.id
            SET t1.is_active = CASE WHEN t2.rn = 1 THEN TRUE ELSE FALSE END
        """)
        rows_affected = cursor.rowcount
        connection.commit()
        print(f"   ✓ Updated {rows_affected} rows!")

        print("\n4. Verifying migration...")
        cursor.execute("""
            SELECT user_id, assessment_year, COUNT(*) as active_count
            FROM tax_calculations
            WHERE is_active = TRUE
            GROUP BY user_id, assessment_year
        """)
        active_calculations = cursor.fetchall()

        if active_calculations:
            print(f"   ✓ Found {len(active_calculations)} active calculation(s):")
            for user_id, year, count in active_calculations:
                print(f"     - User {user_id}, Year {year}: {count} active")
        else:
            print("   ℹ No active calculations found (this is OK if there's no data yet)")

        print("\n✅ Migration completed successfully!")
        return True

    except Error as e:
        print(f"\n❌ Error during migration: {e}")
        if connection:
            connection.rollback()
        return False

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
            print("\n✓ Database connection closed.")

if __name__ == '__main__':
    success = run_migration()
    sys.exit(0 if success else 1)
