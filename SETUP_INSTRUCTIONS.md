# Personal Finance Manager - Setup Instructions

## Prerequisites

- Python 3.7 or higher
- MySQL 5.7 or higher / MariaDB 10.2 or higher
- pip (Python package manager)

## Installation Steps

### 1. Database Setup

**Step 1.1: Start MySQL/MariaDB service**
```bash
# On Ubuntu/Debian
sudo service mysql start

# On macOS (with Homebrew)
brew services start mysql

# On Windows
# Start MySQL from Services or XAMPP/WAMP control panel
```

**Step 1.2: Login to MySQL**
```bash
mysql -u root -p
# Enter your MySQL root password when prompted
```

**Step 1.3: Run the database setup script**
```sql
source /path/to/CW_Budget/database_setup.sql;
-- OR copy and paste the contents of database_setup.sql
```

**Step 1.4: Verify database creation**
```sql
USE personal_finance;
SHOW TABLES;
SELECT * FROM categories;
EXIT;
```

### 2. Application Setup

**Step 2.1: Navigate to project directory**
```bash
cd /path/to/CW_Budget
```

**Step 2.2: Create virtual environment (recommended)**
```bash
python3 -m venv venv

# Activate virtual environment
# On Linux/macOS:
source venv/bin/activate

# On Windows:
venv\Scripts\activate
```

**Step 2.3: Install Python dependencies**
```bash
pip install -r requirements.txt
```

**Step 2.4: Configure environment variables**

Create a `.env` file in the project root:

```bash
# Database Configuration
DB_HOST=localhost
DB_NAME=personal_finance
DB_USER=root
DB_PASSWORD=your_mysql_password

# Application Security
SECRET_KEY=your_random_secret_key_here_change_this_in_production

# Optional: Server Configuration
FLASK_ENV=development
FLASK_DEBUG=True
```

**Generate a secure secret key:**
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Copy the output and use it as your SECRET_KEY in .env

### 3. Run the Application

**Step 3.1: Start the Flask application**
```bash
python3 app.py
```

You should see output like:
```
* Running on http://0.0.0.0:5003
* Debug mode: on
```

**Step 3.2: Access the application**

Open your web browser and go to:
```
http://localhost:5003
```

## First Time Usage

### Option 1: Register a New User

1. Click "Register" in the navigation bar
2. Fill in:
   - Username (unique)
   - Email address (unique)
   - Password
3. Click "Register"
4. Login with your credentials

### Option 2: Use Demo Account (if sample data enabled)

**Username:** demo_user
**Password:** demo123

(Only available if you uncommented the sample data section in database_setup.sql)

## Features Overview

### 1. Dashboard (Overview)
- View current month statistics
- Monthly income, expenses, balance
- Interactive charts showing trends
- Recent transactions list

### 2. Transactions
- Add new transactions manually
- View transactions by month/year
- Delete transactions
- Categorize income and expenses

### 3. Budget Planning
- Set budget limits for categories
- Track actual spending vs planned
- Visual progress indicators

### 4. Recurring Transactions
- Set up monthly recurring income/expenses
- Automatically apply to new months
- Manage (add/delete) recurring items

### 5. Reports
- Monthly summary reports
- Category breakdown analysis
- Yearly overview charts

## Currency

The application is configured to use **Sri Lankan Rupees (LKR)**.

All amounts are displayed as: `LKR 1,000.00`

## Common Issues & Solutions

### Issue 1: Can't connect to database
**Error:** `Database connection failed`

**Solution:**
- Check if MySQL service is running
- Verify database credentials in `.env` file
- Ensure `personal_finance` database exists
- Check if user has proper permissions

```sql
-- Grant permissions if needed
GRANT ALL PRIVILEGES ON personal_finance.* TO 'root'@'localhost';
FLUSH PRIVILEGES;
```

### Issue 2: Module not found errors
**Error:** `ModuleNotFoundError: No module named 'flask'`

**Solution:**
- Ensure virtual environment is activated
- Re-install requirements: `pip install -r requirements.txt`

### Issue 3: Port already in use
**Error:** `Address already in use`

**Solution:**
- Change port in `app.py` (line 799):
  ```python
  app.run(debug=True, host='0.0.0.0', port=5004)  # Changed to 5004
  ```
- Or kill process using port 5003:
  ```bash
  # Linux/macOS
  lsof -ti:5003 | xargs kill -9

  # Windows
  netstat -ano | findstr :5003
  taskkill /PID <PID> /F
  ```

### Issue 4: Navigation not working
**Solution:**
- Clear browser cache (Ctrl+Shift+Delete)
- Hard refresh the page (Ctrl+F5)
- Check browser console for JavaScript errors (F12)
- Ensure Bootstrap and jQuery are loading (check network tab)

### Issue 5: Transactions not saving
**Solution:**
- Check if category is selected
- Ensure either debit OR credit has a value (not both)
- Check browser console for errors
- Verify database connection

## Database Maintenance

### Backup Database
```bash
mysqldump -u root -p personal_finance > backup_$(date +%Y%m%d).sql
```

### Restore Database
```bash
mysql -u root -p personal_finance < backup_20240101.sql
```

### Reset Database (CAUTION: Deletes all data!)
```bash
mysql -u root -p
DROP DATABASE personal_finance;
source /path/to/database_setup.sql;
```

## Development

### Project Structure
```
CW_Budget/
├── app.py                      # Main Flask application
├── requirements.txt            # Python dependencies
├── database_setup.sql          # Database schema and setup
├── .env                        # Environment variables (create this)
├── .gitignore                  # Git ignore rules
├── templates/
│   ├── base.html              # Base template with utilities
│   ├── index.html             # Landing page
│   ├── login.html             # Login page
│   ├── register.html          # Registration page
│   └── dashboard.html         # Main dashboard
└── static/
    └── js/
        └── dashboard.js        # Dashboard JavaScript
```

### Adding New Categories

```sql
USE personal_finance;

-- Add new income category
INSERT INTO categories (name, type, description)
VALUES ('Commission', 'income', 'Sales commission');

-- Add new expense category
INSERT INTO categories (name, type, description)
VALUES ('Gym Membership', 'expense', 'Monthly gym fees');
```

### Checking Logs

The Flask application prints logs to console. To save logs to a file:

```bash
python3 app.py > app.log 2>&1
```

## Production Deployment

For production deployment:

1. Set `FLASK_ENV=production` in .env
2. Use a production WSGI server (Gunicorn, uWSGI)
3. Set up a reverse proxy (Nginx, Apache)
4. Use environment variables for sensitive data
5. Enable HTTPS
6. Set strong SECRET_KEY
7. Configure database backups

Example with Gunicorn:
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5003 app:app
```

## Support

For issues and questions:
1. Check this README
2. Review database_setup.sql comments
3. Check application logs
4. Verify browser console for errors

## License

This project is for personal/educational use.

---

**Version:** 1.0
**Last Updated:** 2025-11-01
