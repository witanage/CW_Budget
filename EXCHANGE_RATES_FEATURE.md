# Exchange Rates Automation Feature

## Overview

This feature automates the retrieval and management of USD to LKR exchange rates from the Central Bank of Sri Lanka (CBSL) for use in the tax calculation section of the budget application.

## Features

1. **CSV Import from CBSL**: Bulk import exchange rates from CBSL's CSV export (PRIMARY METHOD)
2. **Database Storage**: Exchange rates stored in database for fast, reliable access
3. **Date-based Rate Retrieval**: Select a date and automatically populate the exchange rate from database
4. **Smart Fallback**: If exact date isn't available, uses the nearest previous date
5. **Manual Entry**: Existing manual entry functionality preserved as backup
6. **Helper Script**: Easy-to-use command-line tool for CSV imports

## How to Use

### Method 1: CSV Import (RECOMMENDED)

**Important:** The CBSL website has bot protection that blocks automated requests. The CSV import method is the most reliable way to populate exchange rates.

#### Using the Import Script:

1. **Download CSV from CBSL:**
   - Visit: https://www.cbsl.gov.lk/cbsl_custom/exratestt/exrates_resultstt.php
   - Select your date range (recommended: "1 Year" for comprehensive coverage)
   - Click the "CSV" button to download the rates file

2. **Import Using the Helper Script:**
   ```bash
   python import_cbsl_csv.py path/to/downloaded.csv
   ```

   The script will:
   - Parse the CSV file
   - Show you how many rates were found
   - Ask for confirmation before importing
   - Import all rates to the database with progress updates
   - Report success/error statistics

   Example output:
   ```
   Importing exchange rates from: exchange_rates.csv
   Found 365 exchange rates in CSV
   Date range: 2024-11-21 to 2025-11-21

   Import 365 exchange rates? (yes/no): yes

   Importing to database...
     Imported 50 rates...
     Imported 100 rates...
     ...

   Import complete!
     Successfully imported: 365
     Errors: 0
   ```

#### Using the API Endpoint Directly:

If you prefer to use the API:

```bash
curl -X POST http://localhost:5000/api/exchange-rate/import-csv \
  -H "Content-Type: application/json" \
  -H "Cookie: session=<your-session-cookie>" \
  -d '{"csv_content": "Date,Buy Rate (LKR),Sell Rate (LKR)\n2025-11-21,304.2758,311.8332\n..."}'
```

### Method 2: Using Date Picker (After Importing Data)

Once you've imported exchange rates into the database:

1. Navigate to the Tax Calculator section in your dashboard
2. For each month's salary or bonus, you'll see:
   - A manual exchange rate input field (existing functionality)
   - A date picker field below it
   - A download button (📥) next to the date picker

3. **To auto-fetch a rate:**
   - Select a date using the date picker
   - Click the download button (📥)
   - The exchange rate will be automatically fetched from the database and populated

**Note:** The date picker fetches from your database, not directly from CBSL. Make sure you've imported data first using Method 1.

### Method 3: Manual Entry (Always Available)

If automatic fetching isn't working or for custom rates:
- Simply enter the exchange rate manually in the rate input field
- This works exactly as before

## Technical Details

### Database Schema

A new table `exchange_rates` has been added:
```sql
CREATE TABLE exchange_rates (
    id INT AUTO_INCREMENT PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    buy_rate DECIMAL(10, 4) NOT NULL,
    sell_rate DECIMAL(10, 4) NOT NULL,
    source VARCHAR(50) DEFAULT 'CBSL',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

### API Endpoints

#### 1. Get Exchange Rate for a Date
```
GET /api/exchange-rate?date=YYYY-MM-DD
```

**Response:**
```json
{
    "buy_rate": 304.2758,
    "sell_rate": 311.8332,
    "date": "2025-11-21",
    "source": "CBSL"
}
```

#### 2. Get Exchange Rates for a Month
```
GET /api/exchange-rate/month?year=2025&month=11
```

**Response:**
```json
{
    "2025-11-01": {"buy_rate": 300.12, "sell_rate": 308.45, ...},
    "2025-11-02": {"buy_rate": 300.34, "sell_rate": 308.67, ...},
    ...
}
```

#### 3. Import Exchange Rates from CSV
```
POST /api/exchange-rate/import-csv
Content-Type: application/json

{
    "csv_content": "Date,Buy Rate (LKR),Sell Rate (LKR)\n2025-11-21,304.2758,311.8332\n..."
}
```

**Response:**
```json
{
    "message": "Successfully imported 180 exchange rates",
    "success_count": 180,
    "error_count": 0,
    "total_parsed": 180
}
```

## Setup Instructions

### 1. Install Dependencies

```bash
pip install beautifulsoup4==4.12.2
```

### 2. Update Database Schema

Run the updated schema to create the `exchange_rates` table:

```bash
mysql -u your_user -p your_database < schema.sql
```

Or manually create the table using the SQL from the schema file.

### 3. Import Initial Data (REQUIRED for date picker functionality)

Download and import exchange rates from CBSL:

1. Visit: https://www.cbsl.gov.lk/cbsl_custom/exratestt/exrates_resultstt.php
2. Select "1 Year" timeframe (or your preferred range)
3. Click "CSV" button to download
4. Run the import script:
   ```bash
   python import_cbsl_csv.py path/to/downloaded.csv
   ```

This step is essential for the date picker feature to work.

### 4. Restart the Application

```bash
python app.py
```

## Files Added/Modified

### New Files:
- `exchange_rate_service.py` - Main service for fetching and managing exchange rates
- `exchange_rate_parser.py` - CSV parsing utility
- `test_exchange_rate.py` - Test script for the service
- `EXCHANGE_RATES_FEATURE.md` - This documentation

### Modified Files:
- `requirements.txt` - Added beautifulsoup4 dependency
- `schema.sql` - Added exchange_rates table
- `app.py` - Added API endpoints for exchange rates
- `static/js/dashboard.js` - Added UI for date selection and rate fetching

## Troubleshooting

### Issue: "Failed to fetch exchange rate" or "No exchange rate found for this date"

**Cause:** No data in the database for the selected date

**Solutions:**
1. **Import exchange rates first** - The date picker fetches from the database, not directly from CBSL
   ```bash
   python import_cbsl_csv.py path/to/cbsl_rates.csv
   ```
2. Import a wider date range from CBSL (use "1 Year" option)
3. The system will automatically use the nearest previous date if available
4. Manually enter the rate as a fallback

### Issue: CSV import fails or shows errors

**Solutions:**
1. Verify the CSV file format matches CBSL's format:
   - Header: `Date,Buy Rate (LKR),Sell Rate (LKR)`
   - Data rows: `2025-11-21,304.2758,311.8332`
2. Check database connection settings in `.env` file
3. Ensure the `exchange_rates` table exists in the database
4. Check import script logs for specific error messages

### Issue: Date picker shows but button doesn't work

**Solutions:**
1. Check browser console for JavaScript errors (F12)
2. Verify you're logged in
3. Ensure you've imported data into the database
4. Check application logs for API errors
5. Clear browser cache and reload the page

### Issue: Import script shows "Database error"

**Solutions:**
1. Verify database is running: `mysql -u your_user -p`
2. Check database connection settings in `.env` file
3. Ensure the `exchange_rates` table was created
4. Verify database user has INSERT/UPDATE permissions

## Best Practices

1. **Import Historical Data:** Import at least 1 year of historical rates when setting up
2. **Periodic Updates:** Import new rates monthly or quarterly from CBSL
3. **Verify Rates:** Always verify critical calculations with manual rate entry
4. **Keep CSV Backups:** Save downloaded CSV files for records

## Future Enhancements

Potential improvements for the future:
- **Direct CBSL API integration** (when/if CBSL provides an official API)
- **Automated scraping with proxy rotation** (to work around bot protection)
- **Alternative data sources** (e.g., other financial APIs like exchangerate-api.com)
- **Bulk date range import via UI** (upload CSV through web interface)
- **Rate comparison and validation** (compare rates from multiple sources)
- **Historical rate charts** (visualize exchange rate trends)
- **Email notifications** (alert when rates haven't been updated in X days)
- **Scheduled CSV imports** (automatic download and import on schedule)

## Support

If you encounter issues:
1. Check the application logs for detailed error messages
2. Verify database connection and table creation
3. Test with the provided test script: `python test_exchange_rate.py`
4. Review the API responses for specific error details

---

**Last Updated:** 2025-11-21
**Version:** 1.0
