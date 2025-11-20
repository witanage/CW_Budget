#!/usr/bin/env python3
"""
Script to add tax calculation tables to the database.
Run this script once to create the necessary tables for the Tax Calculator feature.
"""

import os
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def get_db_config():
    """Get database configuration from environment variables."""
    return {
        'host': os.environ.get('DB_HOST'),
        'port': int(os.environ.get('DB_PORT', '3306')),
        'database': os.environ.get('DB_NAME'),
        'user': os.environ.get('DB_USER'),
        'password': os.environ.get('DB_PASSWORD'),
        'charset': 'utf8mb4',
        'use_unicode': True
    }

def create_tax_tables():
    """Create tax calculation tables in the database."""

    # SQL statements to create the tables
    create_tax_calculations_table = """
    CREATE TABLE IF NOT EXISTS tax_calculations (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        calculation_name VARCHAR(255) NOT NULL,
        assessment_year VARCHAR(20) NOT NULL,
        monthly_salary_usd DECIMAL(15, 2) NOT NULL,
        tax_rate DECIMAL(5, 2) NOT NULL,
        tax_free_threshold DECIMAL(15, 2) NOT NULL,
        start_month INT NOT NULL COMMENT '0=April, 11=March',
        monthly_data JSON NOT NULL COMMENT 'Array of 12 months with exchange rates and bonuses',
        total_annual_income DECIMAL(15, 2) NOT NULL,
        total_tax_liability DECIMAL(15, 2) NOT NULL,
        effective_tax_rate DECIMAL(5, 2) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        INDEX idx_user_id (user_id),
        INDEX idx_assessment_year (assessment_year),
        INDEX idx_created_at (created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """

    create_tax_details_table = """
    CREATE TABLE IF NOT EXISTS tax_calculation_details (
        id INT AUTO_INCREMENT PRIMARY KEY,
        tax_calculation_id INT NOT NULL,
        month_index INT NOT NULL COMMENT '0-11 representing the month order',
        month_name VARCHAR(20) NOT NULL,
        exchange_rate DECIMAL(10, 2) NOT NULL,
        bonus_usd DECIMAL(15, 2) DEFAULT 0,
        fc_receipts_usd DECIMAL(15, 2) NOT NULL,
        fc_receipts_lkr DECIMAL(15, 2) NOT NULL,
        cumulative_income DECIMAL(15, 2) NOT NULL,
        total_tax_liability DECIMAL(15, 2) NOT NULL,
        monthly_payment DECIMAL(15, 2) NOT NULL,
        FOREIGN KEY (tax_calculation_id) REFERENCES tax_calculations(id) ON DELETE CASCADE,
        INDEX idx_tax_calculation (tax_calculation_id),
        INDEX idx_month_index (month_index)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """

    try:
        # Connect to database
        print("Connecting to database...")
        connection = mysql.connector.connect(**get_db_config())
        cursor = connection.cursor()

        # Create tax_calculations table
        print("\nCreating tax_calculations table...")
        cursor.execute(create_tax_calculations_table)
        print("✓ tax_calculations table created successfully")

        # Create tax_calculation_details table
        print("\nCreating tax_calculation_details table...")
        cursor.execute(create_tax_details_table)
        print("✓ tax_calculation_details table created successfully")

        connection.commit()

        # Verify tables were created
        cursor.execute("SHOW TABLES LIKE 'tax_%'")
        tables = cursor.fetchall()

        print("\n" + "="*60)
        print("Database tables created successfully!")
        print("="*60)
        print("\nTax Calculator tables in database:")
        for table in tables:
            print(f"  ✓ {table[0]}")

        print("\n" + "="*60)
        print("You can now use the Tax Calculator feature!")
        print("="*60)

    except Error as e:
        print(f"\n✗ Error: {e}")
        return False

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
            print("\nDatabase connection closed.")

    return True

if __name__ == '__main__':
    print("="*60)
    print("Tax Calculator Database Setup")
    print("="*60)

    success = create_tax_tables()

    if success:
        print("\n✓ Setup completed successfully!")
        print("\nNext steps:")
        print("  1. Restart your application if it's running")
        print("  2. Navigate to the Tax page in your app")
        print("  3. Start calculating and saving your tax data")
    else:
        print("\n✗ Setup failed. Please check the error messages above.")
