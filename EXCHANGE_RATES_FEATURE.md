# Exchange Rates Automation Feature

## Overview

This feature automates the retrieval and management of USD to LKR exchange rates from the Central Bank of Sri Lanka (CBSL) for use in the tax calculation section of the budget application.

## Features

1. **Date-based Exchange Rate Retrieval**: Select a date and automatically fetch the exchange rate
2. **Database Storage**: Exchange rates are cached in the database for fast access
3. **CSV Import**: Import exchange rates from CBSL CSV exports
4. **Smart Fallback**: If the exact date isn't available, the system uses the nearest previous date
5. **Manual Entry**: The existing manual entry functionality is preserved as a backup

## How to Use

### Method 1: Using Date Picker (In the Tax Section)

1. Navigate to the Tax Calculator section in your dashboard
2. For each month's salary or bonus, you'll see:
   - A manual exchange rate input field (existing functionality)
   - A date picker field below it
   - A download button (📥) next to the date picker

3. **To auto-fetch a rate:**
   - Select a date using the date picker
   - Click the download button (📥)
   - The exchange rate will be automatically fetched and populated

### Method 2: CSV Import (Recommended for Bulk Updates)

Since the CBSL website may block automated requests, the CSV import method is recommended:

1. **Download CSV from CBSL:**
   - Visit: https://www.cbsl.gov.lk/cbsl_custom/exratestt/exrates_resultstt.php
   - Select your date range (e.g., past 1 year)
   - Click the "CSV" button to download the rates

2. **Import to the Application:**
   - Use the API endpoint `/api/exchange-rate/import-csv`
   - Send a POST request with the CSV content

   Example using curl:
   ```bash
   curl -X POST http://localhost:5000/api/exchange-rate/import-csv \
     -H "Content-Type: application/json" \
     -d '{"csv_content": "Date,Buy Rate (LKR),Sell Rate (LKR)\n2025-11-21,304.2758,311.8332\n..."}'
   ```

3. **Verify Import:**
   - The API will return the number of rates successfully imported
   - Now you can use the date picker to fetch these rates instantly

### Method 3: Manual Entry (Fallback)

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

### 3. Import Initial Data (Optional)

Download a year's worth of exchange rates from CBSL and import them:

1. Visit the CBSL website
2. Select "1 Year" timeframe
3. Click "CSV" to download
4. Use the import API or create a script to import the CSV

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

### Issue: "Failed to fetch exchange rate"

**Possible causes:**
1. The CBSL website is blocking requests (403 Forbidden)
2. No data available for the selected date
3. Network connectivity issues

**Solutions:**
1. Use the CSV import method instead
2. Select a different date (weekdays are more likely to have data)
3. Check your internet connection
4. Manually enter the rate as a fallback

### Issue: "No exchange rate found for this date"

**Cause:** The selected date doesn't have data in the database

**Solution:**
1. Import CSV data from CBSL for a wider date range
2. The system will automatically use the nearest previous date if available
3. Manually enter the rate if needed

### Issue: Date picker shows but rates aren't fetching

**Solution:**
1. Check browser console for errors (F12)
2. Verify you're logged in
3. Ensure the database table was created successfully
4. Check application logs for detailed error messages

## Best Practices

1. **Import Historical Data:** Import at least 1 year of historical rates when setting up
2. **Periodic Updates:** Import new rates monthly or quarterly from CBSL
3. **Verify Rates:** Always verify critical calculations with manual rate entry
4. **Keep CSV Backups:** Save downloaded CSV files for records

## Future Enhancements

Potential improvements for the future:
- Automatic scheduled imports from CBSL
- Alternative data sources (e.g., other financial APIs)
- Rate comparison and validation
- Historical rate charts and analysis
- Email notifications for rate updates

## Support

If you encounter issues:
1. Check the application logs for detailed error messages
2. Verify database connection and table creation
3. Test with the provided test script: `python test_exchange_rate.py`
4. Review the API responses for specific error details

---

**Last Updated:** 2025-11-21
**Version:** 1.0
