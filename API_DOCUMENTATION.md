# Transaction API Documentation

This document provides details on how to use the Transaction API endpoint with token authentication.

## Overview

The Transaction API allows you to create financial transactions (expenses) programmatically using token-based authentication. This is useful for integrating with external applications, mobile apps, or automation scripts.

## Authentication

All API requests require a valid JWT (JSON Web Token) authentication token. The token must be included in the `Authorization` header using the `Bearer` scheme.

### Step 1: Generate Authentication Token

**Endpoint:** `POST /api/auth/token`

**Request Body:**
```json
{
  "username": "your_username_or_email",
  "password": "your_password"
}
```

**Example using curl:**
```bash
curl -X POST http://localhost:5003/api/auth/token \
  -H "Content-Type: application/json" \
  -d '{
    "username": "your_username",
    "password": "your_password"
  }'
```

**Response (Success - 200 OK):**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "expires_at": "2026-02-16T12:00:00",
  "user": {
    "id": 1,
    "username": "your_username",
    "email": "user@example.com",
    "is_admin": false
  }
}
```

**Response (Error - 401 Unauthorized):**
```json
{
  "error": "Invalid credentials"
}
```

**Token Expiration:**
- Tokens are valid for 24 hours from generation
- After expiration, you must generate a new token

---

## Creating a Transaction

### Step 2: Create Transaction with Token

**Endpoint:** `POST /api/transactions/create`

**Headers:**
- `Authorization: Bearer <your_token_here>`
- `Content-Type: application/json`

**Request Body:**
```json
{
  "description": "Transaction description",
  "credit": 150.50
}
```

**Required Fields:**
- `description` (string): Description of the transaction (e.g., "Grocery shopping", "Coffee")
- `credit` (number): Expense amount (must be greater than 0)

**Note:** The transaction date is automatically set to today's date (current date)

**Example using curl:**
```bash
# First, save your token to a variable
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

# Create a transaction (date will be set to today)
curl -X POST http://localhost:5003/api/transactions/create \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Grocery shopping",
    "credit": 150.50
  }'
```

**Response (Success - 201 Created):**
```json
{
  "message": "Transaction created successfully",
  "transaction_id": 123,
  "description": "Grocery shopping",
  "credit": 150.50,
  "transaction_date": "2026-02-15",
  "year": 2026,
  "month": 2
}
```

**Response (Error - 400 Bad Request):**
```json
{
  "error": "Description is required"
}
```

**Response (Error - 401 Unauthorized):**
```json
{
  "error": "Token is missing. Please provide token in Authorization header."
}
```

---

## Complete Example Workflow

Here's a complete example showing how to authenticate and create a transaction:

```bash
# Step 1: Generate token
TOKEN_RESPONSE=$(curl -X POST http://localhost:5003/api/auth/token \
  -H "Content-Type: application/json" \
  -d '{
    "username": "your_username",
    "password": "your_password"
  }')

# Extract token from response (requires jq)
TOKEN=$(echo $TOKEN_RESPONSE | jq -r '.token')

echo "Token: $TOKEN"

# Step 2: Create transaction (date will be today)
curl -X POST http://localhost:5003/api/transactions/create \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Coffee at Starbucks",
    "credit": 5.50
  }'
```

---

## Using Python

A complete Python example is available in `test_transaction_api.py`:

```python
import requests

# Get token
response = requests.post(
    "http://localhost:5003/api/auth/token",
    json={"username": "your_username", "password": "your_password"}
)
token = response.json()['token']

# Create transaction (date will be today)
response = requests.post(
    "http://localhost:5003/api/transactions/create",
    headers={"Authorization": f"Bearer {token}"},
    json={
        "description": "Coffee",
        "credit": 5.50
    }
)
print(response.json())
```

---

## Error Codes

| Code | Description |
|------|-------------|
| 200 | OK - Token generated successfully |
| 201 | Created - Transaction created successfully |
| 400 | Bad Request - Missing or invalid parameters |
| 401 | Unauthorized - Invalid or expired token |
| 403 | Forbidden - Account deactivated |
| 500 | Internal Server Error - Database or server error |

---

## Security Notes

1. **Keep your token secure**: Never share your authentication token or commit it to version control
2. **Use HTTPS in production**: Always use HTTPS when transmitting credentials or tokens
3. **Token expiration**: Tokens expire after 24 hours. Implement token refresh logic in your application
4. **Revoke tokens**: Use the `/api/auth/token/revoke` endpoint to invalidate a token when no longer needed

---

## Additional API Endpoints

### Revoke Token

**Endpoint:** `POST /api/auth/token/revoke`

**Headers:**
- `Authorization: Bearer <your_token_here>`

**Example:**
```bash
curl -X POST http://localhost:5003/api/auth/token/revoke \
  -H "Authorization: Bearer $TOKEN"
```

**Response (Success - 200 OK):**
```json
{
  "message": "Token revoked successfully"
}
```

---

## Support

For issues or questions about the API, please contact your system administrator or refer to the application documentation.
