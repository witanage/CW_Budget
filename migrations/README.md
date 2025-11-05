# Database Migrations

This directory contains database migration scripts for the CW Budget application.

## Running Migrations

To run a migration, connect to your MySQL database and execute the SQL file:

```bash
mysql -u your_user -p your_database < migrations/remove_balance_column.sql
```

Or use the Python migration script:

```bash
python migrations/apply_migration.py
```

## Available Migrations

- `remove_balance_column.sql`: Removes the balance column from transactions table. Balance is now calculated on frontend in real-time.

## Important Notes

- Always backup your database before running migrations
- Migrations are applied manually and should be run in order
- Each migration is a one-way operation unless explicitly stated
