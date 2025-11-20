# Tax Calculator API Endpoints Documentation

This document describes the revamped backend API endpoints for the Tax Calculator, which now support assessment year-wise data organization.

## Overview

The Tax Calculator API has been enhanced to support better organization of tax calculations by assessment year. Key improvements include:

- **Active Calculation Tracking**: Each user can have one "active" calculation per assessment year
- **Year-wise Filtering**: Backend filtering for efficient data retrieval
- **New Endpoints**: Dedicated endpoints for year-based operations

## Database Schema Changes

### New Column: `is_active`

The `tax_calculations` table now includes:
- `is_active` (BOOLEAN, default: FALSE) - Indicates if this is the active calculation for the assessment year
- New index: `idx_user_assessment_active` on `(user_id, assessment_year, is_active)`

### Migration

Run the migration script to add the new column:
```sql
-- See: migrations/add_tax_is_active_column.sql
ALTER TABLE tax_calculations ADD COLUMN is_active BOOLEAN DEFAULT FALSE;
CREATE INDEX idx_user_assessment_active ON tax_calculations(user_id, assessment_year, is_active);
```

## API Endpoints

### 1. Save Tax Calculation

**Endpoint:** `POST /api/tax-calculations`

**Description:** Save a new tax calculation. Optionally mark it as active for its assessment year.

**Request Body:**
```json
{
  "calculation_name": "My Tax Plan 2024/2025",
  "assessment_year": "2024/2025",
  "monthly_salary_usd": 6000,
  "tax_rate": 15,
  "tax_free_threshold": 360000,
  "start_month": 0,
  "monthly_data": [...],
  "total_annual_income": 21528000,
  "total_tax_liability": 3229200,
  "effective_tax_rate": 15,
  "is_active": true  // NEW: Mark as active (optional, default: false)
}
```

**Response:** `201 Created`
```json
{
  "message": "Tax calculation saved successfully",
  "id": 123
}
```

**Behavior:**
- If `is_active` is `true`, all other calculations for the same user and assessment year will be set to `is_active = false`
- Only one calculation can be active per user per assessment year

---

### 2. Get All Tax Calculations (with optional year filter)

**Endpoint:** `GET /api/tax-calculations?year={assessment_year}`

**Description:** Get all tax calculations for the current user, optionally filtered by assessment year.

**Query Parameters:**
- `year` (optional) - Filter by assessment year (e.g., "2024/2025")

**Examples:**
```
GET /api/tax-calculations              # Get all calculations
GET /api/tax-calculations?year=2024/2025  # Get only 2024/2025 calculations
```

**Response:** `200 OK`
```json
[
  {
    "id": 123,
    "calculation_name": "My Tax Plan",
    "assessment_year": "2024/2025",
    "monthly_salary_usd": 6000,
    "tax_rate": 15,
    "tax_free_threshold": 360000,
    "total_annual_income": 21528000,
    "total_tax_liability": 3229200,
    "effective_tax_rate": 15,
    "is_active": true,  // NEW: Active status
    "created_at": "2025-11-15T10:30:00Z",
    "updated_at": "2025-11-15T10:30:00Z"
  }
]
```

**Sorting:**
- Without year filter: Sorted by `assessment_year DESC, is_active DESC, created_at DESC`
- With year filter: Sorted by `is_active DESC, created_at DESC` (active calculations appear first)

---

### 3. Get Specific Tax Calculation

**Endpoint:** `GET /api/tax-calculations/{calculation_id}`

**Description:** Get a specific tax calculation with all monthly details.

**Response:** `200 OK`
```json
{
  "id": 123,
  "calculation_name": "My Tax Plan",
  "assessment_year": "2024/2025",
  "is_active": true,  // NEW: Active status included
  "monthly_data": [...],
  "details": [...],
  ...
}
```

---

### 4. Delete Tax Calculation

**Endpoint:** `DELETE /api/tax-calculations/{calculation_id}`

**Description:** Delete a tax calculation (unchanged).

**Response:** `200 OK`

---

### 5. Get Assessment Years (NEW)

**Endpoint:** `GET /api/tax-calculations/years`

**Description:** Get a list of all assessment years with calculation counts for the current user.

**Response:** `200 OK`
```json
[
  {
    "assessment_year": "2025/2026",
    "calculation_count": 3,
    "has_active": 1,  // 1 if there's an active calculation, 0 otherwise
    "last_updated": "2025-11-20T15:45:00Z"
  },
  {
    "assessment_year": "2024/2025",
    "calculation_count": 5,
    "has_active": 1,
    "last_updated": "2025-11-15T10:30:00Z"
  }
]
```

**Use Cases:**
- Display a summary of years with saved calculations
- Check which years have active calculations
- Show last update time for each year

---

### 6. Get Calculations by Year (NEW)

**Endpoint:** `GET /api/tax-calculations/by-year/{year}`

**Description:** Get all tax calculations for a specific assessment year.

**Example:**
```
GET /api/tax-calculations/by-year/2024/2025
```

**Response:** `200 OK` (same format as endpoint #2)

**Sorting:** Active calculations appear first

**Note:** This is equivalent to `GET /api/tax-calculations?year={year}` but provides a cleaner URL structure.

---

### 7. Get Active Calculation by Year (NEW)

**Endpoint:** `GET /api/tax-calculations/by-year/{year}/active`

**Description:** Get the active tax calculation for a specific assessment year.

**Example:**
```
GET /api/tax-calculations/by-year/2024/2025/active
```

**Response:** `200 OK`
```json
{
  "id": 123,
  "calculation_name": "My Tax Plan",
  "assessment_year": "2024/2025",
  "is_active": true,
  "monthly_data": [...],
  "details": [...]
}
```

**Error Response:** `404 Not Found`
```json
{
  "error": "No active tax calculation found for this year"
}
```

**Use Cases:**
- Quickly load the current active calculation for a year
- Display the "default" calculation for an assessment year
- Auto-load calculation when user selects a year

---

### 8. Set Active Calculation (NEW)

**Endpoint:** `PUT /api/tax-calculations/{calculation_id}/set-active`

**Description:** Set a tax calculation as active for its assessment year. This will deactivate all other calculations for the same user and year.

**Example:**
```
PUT /api/tax-calculations/123/set-active
```

**Response:** `200 OK`
```json
{
  "message": "Tax calculation set as active successfully",
  "id": 123,
  "assessment_year": "2024/2025"
}
```

**Error Response:** `404 Not Found`
```json
{
  "error": "Tax calculation not found"
}
```

**Behavior:**
1. Verifies the calculation exists and belongs to the current user
2. Sets `is_active = false` for all calculations with the same user and assessment year
3. Sets `is_active = true` for the specified calculation
4. Updates the `updated_at` timestamp

---

## Frontend Integration

### New JavaScript Functions

1. **`filterCalculationsByYear()`** - Updated to use backend filtering
   - Calls: `GET /api/tax-calculations?year={year}`
   - No longer filters client-side

2. **`setActiveCalculation(calculationId)`** - New function
   - Calls: `PUT /api/tax-calculations/{calculationId}/set-active`
   - Shows confirmation dialog before setting
   - Reloads calculations list on success

3. **`saveTaxCalculation()`** - Updated to include `is_active`
   - Reads the "Set as active" checkbox value
   - Sends `is_active` field in request body

### UI Changes

1. **Active Badge**: Calculations marked as active show a green "Active" badge
2. **Active Border**: Active calculations have a green border (`border-success`)
3. **Star Button**: Non-active calculations show a star button to set them as active
4. **Save Checkbox**: New checkbox "Set as active calculation for this year" (checked by default)

---

## Example Workflows

### Workflow 1: Save and Set Active

```javascript
// User calculates tax and saves with "Set as active" checked
POST /api/tax-calculations
{
  "calculation_name": "Q4 Tax Update",
  "assessment_year": "2024/2025",
  "is_active": true,
  ...
}

// Backend automatically deactivates other 2024/2025 calculations
// Response includes the new calculation ID
```

### Workflow 2: Switch Active Calculation

```javascript
// User clicks star button on a different calculation
PUT /api/tax-calculations/456/set-active

// Backend:
// 1. Sets calculation 123 to is_active = false
// 2. Sets calculation 456 to is_active = true
// 3. Returns success message with year info
```

### Workflow 3: Filter by Year

```javascript
// User selects "2024/2025" from dropdown and clicks "Load"
GET /api/tax-calculations?year=2024/2025

// Backend returns only 2024/2025 calculations
// Active calculation appears first in the list
```

### Workflow 4: Load Active Calculation

```javascript
// App wants to auto-load the active calculation for current year
GET /api/tax-calculations/by-year/2024/2025/active

// Backend returns the active calculation with full details
// Or 404 if no active calculation exists
```

---

## Migration Guide

### For Existing Installations

1. **Run the migration script:**
   ```bash
   mysql -u [user] -p [database] < migrations/add_tax_is_active_column.sql
   ```

2. **Verify the migration:**
   ```sql
   DESCRIBE tax_calculations;
   -- Should show is_active column

   SHOW INDEX FROM tax_calculations;
   -- Should show idx_user_assessment_active index
   ```

3. **Check active calculations:**
   ```sql
   SELECT user_id, assessment_year, COUNT(*) as active_count
   FROM tax_calculations
   WHERE is_active = TRUE
   GROUP BY user_id, assessment_year;
   -- Each user should have at most 1 active calculation per year
   ```

### For New Installations

The updated `schema.sql` already includes the `is_active` column and index. No migration needed.

---

## Security Considerations

1. **Authentication**: All endpoints require `@login_required`
2. **Authorization**: Users can only access their own calculations (filtered by `user_id` from session)
3. **Validation**:
   - Calculation name and assessment year are required
   - Calculation ID ownership is verified before set-active and delete operations
4. **Transactions**: Set-active operations use transactions to ensure atomicity

---

## Performance Considerations

1. **Indexing**: New index `idx_user_assessment_active` improves query performance for:
   - Finding active calculations by year
   - Filtering calculations by year with active-first sorting

2. **Backend Filtering**: Moving filtering from frontend to backend reduces:
   - Data transfer (only requested year's data is sent)
   - Client-side processing
   - Memory usage on the client

3. **Query Optimization**: All endpoints use indexed columns in WHERE clauses:
   - `user_id` (indexed via foreign key and `idx_user_id`)
   - `assessment_year` (indexed via `idx_assessment_year`)
   - `is_active` (indexed via `idx_user_assessment_active`)

---

## Error Handling

All endpoints follow consistent error response format:

```json
{
  "error": "Error message description"
}
```

Common HTTP status codes:
- `200 OK` - Success
- `201 Created` - Calculation saved successfully
- `400 Bad Request` - Validation error
- `404 Not Found` - Calculation not found or no active calculation
- `500 Internal Server Error` - Database or server error

---

## Testing

### Manual Testing Checklist

- [ ] Save a calculation without "Set as active" checkbox
- [ ] Save a calculation with "Set as active" checkbox
- [ ] Save multiple calculations for the same year
- [ ] Set an existing calculation as active using the star button
- [ ] Verify only one calculation is active per year
- [ ] Filter calculations by year
- [ ] Load all calculations (no filter)
- [ ] Load the active calculation for a specific year
- [ ] Try to load active calculation for a year with no calculations
- [ ] Delete an active calculation
- [ ] Check that the UI shows active badges correctly
- [ ] Verify backend filtering performance with multiple years

---

## Version History

- **v2.0** (2025-11-20): Assessment year-wise backend revamp
  - Added `is_active` column
  - Added year filtering endpoints
  - Added active calculation management
  - Improved query performance with new index

- **v1.0**: Initial tax calculator implementation
  - Basic CRUD operations
  - Frontend-based filtering
