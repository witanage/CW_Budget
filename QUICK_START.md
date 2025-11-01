# Quick Start Guide

## Fastest Way to Get Started (5 minutes)

### Step 1: Setup Database (2 minutes)

```bash
# Login to MySQL
mysql -u root -p

# Run this in MySQL prompt:
source /full/path/to/CW_Budget/database_setup.sql;

# Or on Windows, you might need:
# In MySQL prompt: source C:/path/to/CW_Budget/database_setup.sql;

# Verify setup:
USE personal_finance;
SHOW TABLES;
# You should see 6 tables

EXIT;
```

### Step 2: Configure Application (1 minute)

Create a file named `.env` in the CW_Budget folder:

```env
DB_HOST=localhost
DB_NAME=personal_finance
DB_USER=root
DB_PASSWORD=your_mysql_password_here
SECRET_KEY=change_this_to_something_random_and_secure
```

**Important:** Change `your_mysql_password_here` to your actual MySQL password!

### Step 3: Install Dependencies (1 minute)

```bash
cd /path/to/CW_Budget

# Install required Python packages
pip3 install -r requirements.txt
```

### Step 4: Run the Application (1 minute)

```bash
python3 app.py
```

You should see:
```
* Running on http://0.0.0.0:5003
Press CTRL+C to quit
```

### Step 5: Open in Browser

Go to: **http://localhost:5003**

## First Login

### Option A: Register New User
1. Click **"Register"** button
2. Fill in username, email, password
3. Click **"Register"**
4. Login with your credentials

### Option B: Use Demo Account (Optional)

If you want sample data:

1. Open `database_setup.sql` in a text editor
2. Find line ~175: `/* -- Get demo user ID`
3. Remove the `/*` at the beginning and `*/` at the end (uncomment the block)
4. Run the SQL script again:
   ```bash
   mysql -u root -p personal_finance < database_setup.sql
   ```
5. Login with:
   - **Username:** demo_user
   - **Password:** demo123

## Using the Application

### Add Your First Transaction

1. Click **"Transactions"** in the sidebar
2. Click **"+ Add Transaction"** button
3. Fill in:
   - Description: "Salary Payment"
   - Category: Salary (income)
   - Debit: 150000 (income goes in debit)
   - Date: Today's date
4. Click **"Save Transaction"**

### Add an Expense

1. Click **"+ Add Transaction"**
2. Fill in:
   - Description: "Grocery Shopping"
   - Category: Groceries (expense)
   - Credit: 5000 (expenses go in credit)
   - Date: Today's date
3. Click **"Save Transaction"**

### View Dashboard

Click **"Overview"** to see:
- Your current balance
- Total income and expenses
- Charts and graphs

## Common First-Time Issues

### ❌ "Can't connect to database"

**Fix:**
- Check if MySQL is running: `sudo service mysql start` (Linux) or start from Services (Windows)
- Verify `.env` file has correct password
- Make sure database was created: `mysql -u root -p -e "SHOW DATABASES;"`

### ❌ "Module 'flask' not found"

**Fix:**
```bash
pip3 install Flask Flask-CORS mysql-connector-python Werkzeug python-dotenv
```

### ❌ "Page not loading" or "Navigation not working"

**Fix:**
- Clear browser cache (Ctrl + Shift + Delete)
- Try a different browser
- Check browser console (F12) for errors
- Make sure app.py is still running in terminal

### ❌ "Transaction not saving"

**Fix:**
- Make sure you filled in the Description field
- Enter amount in either Debit OR Credit (not both)
- Select a category from dropdown
- Check if you're logged in

## Key Concepts

### Debit vs Credit (Double-Entry Bookkeeping)

- **Debit (Income)**: Money coming IN
  - Salary: Debit
  - Freelance payment: Debit
  - Gift received: Debit

- **Credit (Expense)**: Money going OUT
  - Rent payment: Credit
  - Grocery shopping: Credit
  - Utility bills: Credit

### Balance Calculation

```
Current Balance = Previous Balance + Debit - Credit
```

Example:
- Starting balance: LKR 0
- Add salary (debit): +LKR 150,000 = LKR 150,000
- Pay rent (credit): -LKR 30,000 = LKR 120,000
- Final balance: LKR 120,000

## Next Steps

1. ✅ Add your recurring transactions (monthly salary, rent, etc.)
2. ✅ Set up budget plans for different categories
3. ✅ Enter your monthly transactions
4. ✅ View reports to analyze spending patterns

## Need Help?

1. Check `SETUP_INSTRUCTIONS.md` for detailed information
2. Review `database_setup.sql` comments
3. Look at browser console (F12) for JavaScript errors
4. Check terminal/console where app.py is running for Python errors

## Stopping the Application

Press `Ctrl+C` in the terminal where app.py is running.

---

**Ready to manage your finances!** 🎉

Start by adding a few transactions and explore the dashboard.
