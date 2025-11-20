# Tax Calculator Database Setup

The Tax Calculator feature requires two new database tables. Follow the instructions below to set them up.

## Database Tables Required

1. **tax_calculations** - Stores main tax calculation data
2. **tax_calculation_details** - Stores monthly breakdown details

## Setup Instructions

### Option 1: Using MySQL Command Line (Recommended)

If you have MySQL CLI access, run:

```bash
mysql -h ll206l.h.filess.io -P 3307 -u CWDB_typedozen -p CWDB_typedozen < tax_tables_schema.sql
```

When prompted, enter your password: `7fc07286a1e6279284511aff43f618f26dedff65`

### Option 2: Using phpMyAdmin or Database GUI Tool

1. Log into your database management tool
2. Select the database: `CWDB_typedozen`
3. Go to SQL query section
4. Copy and paste the contents of `tax_tables_schema.sql`
5. Execute the SQL

### Option 3: Using the Python Script (If connection works)

```bash
python3 add_tax_tables.py
```

## Verify Tables Were Created

Run this SQL query to verify:

```sql
SHOW TABLES LIKE 'tax_%';
```

You should see:
- tax_calculations
- tax_calculation_details

## Troubleshooting

### Error: "Unknown MySQL server host"

- Check your internet connection
- Verify the database host is accessible
- The database server might be down temporarily

### Error: "Access denied"

- Verify your database credentials in `.env` file
- Check username and password are correct

### Error: "Table already exists"

- Tables are already created! You're good to go.
- Just restart your application and use the Tax Calculator

## After Setup

1. **Restart your application** if it's running
2. Navigate to the **Tax** page in the sidebar
3. Start calculating and saving your tax data!

## Features Available After Setup

✓ Calculate monthly withholding tax
✓ Save unlimited calculations per assessment year
✓ Load previous calculations
✓ Filter by assessment year
✓ Track tax trends over multiple years
✓ Delete old calculations

---

For any issues, check the application logs or database error messages.
