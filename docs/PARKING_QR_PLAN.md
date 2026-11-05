# Parking QR Notifier — Implementation Plan

Lets a vehicle owner leave a QR code on the dashboard. Anyone who scans it
can tell the owner (through an ntfy push notification) that they need to move
the car, without either side seeing the other's phone number unless the
scanner chooses to share theirs.

## 1. Scope

| # | Requirement | Where |
|---|-------------|-------|
| 1 | QR on dashboard → scanner sees a "notification sent" animation, owner gets an ntfy push | `GET/POST /park/s/<token>` |
| 2 | Scanner can optionally give a mobile number (and location) | Scan form, `park_scans` |
| 3 | Scanner must pass Google reCAPTCHA before submitting | Server-side `siteverify` |
| 4 | QR holds no PII: only an opaque, keyed hash token | `services/parking/security.py` |
| 5 | Back office with login, password change, "change QR" | `/park/login`, `/park/` |
| 6 | Scan log table: IP, mobile, geo (optional), timestamp | `park_scans`, dashboard |
| 7 | Add new users (admin), one user → many vehicles | `/park/api/admin/users`, `park_vehicles` |
| 8 | Self-registration with mobile + plate, Sri Lankan plate rules, reCAPTCHA | `/park/register` |
| 9 | Ready for other countries later | Country registry in `validators.py` |

## 2. Architecture: inside the existing app, isolated

The feature runs inside the existing Flask app (`app.py`) as a separate
**Blueprint mounted at `/park`**, in its own package `services/parking/`.

What it shares with the budget app:
- the Flask process, `db.get_db_connection()`, the Flask-Limiter instance
- ntfy server settings in `app_settings` (`ntfy_server_url`, `ntfy_username`, `ntfy_password`)

What is isolated, for security:
- **Separate tables** (`park_users`, `park_vehicles`, `park_scans`). Parking
  accounts are not rows in `users`, so a parking login can never open budget
  data, and the budget app's open `/register` can't be used to get into parking.
- **Separate session keys** (`park_user_id`, `park_is_admin`, `park_csrf`). The
  budget decorators check `user_id`, the parking decorators check `park_user_id`.
- **Separate templates** (`templates/park/`), a standalone layout that loads
  none of the budget JS.
- **Separate admin role** (`park_users.is_admin`), created through a CLI command.

```
services/parking/
  __init__.py      register_parking_routes(app, limiter) + CLI commands
  routes.py        Blueprint: public scan, auth, back office, admin APIs
  repository.py    all SQL (parameterised), nothing else touches park_* tables
  security.py      QR token derivation, reCAPTCHA verify, CSRF, session guard
  validators.py    country registry: plate + mobile normalisation (LK first)
  notifier.py      ntfy JSON publish
  schema.sql       DDL for park_* tables
templates/park/
  base.html, login.html, register.html, dashboard.html,
  scan.html, scan_invalid.html, print_qr.html
tests/test_parking.py
```

## 3. Data model (`services/parking/schema.sql`)

**park_users**: `id, full_name, country_code, mobile_e164 (UNIQUE), password_hash,
ntfy_topic (UNIQUE, random), is_admin, is_active, created_at, last_login_at,
password_changed_at`

**park_vehicles**: `id, user_id → park_users (CASCADE), country_code,
plate_normalized, plate_display, region_code, nickname, qr_nonce,
qr_token_hash (UNIQUE), qr_rotated_at, is_active, created_at`
- `UNIQUE(user_id, country_code, plate_normalized)`. Plates are *not* globally
  unique, so nobody can block the real owner from registering by claiming
  their plate first. The QR, not the plate, decides who gets notified.

**park_scans**: `id, vehicle_id → park_vehicles (CASCADE), scanned_at (UTC),
ip_address, user_agent, scanner_mobile, latitude, longitude, location_accuracy_m,
reason, message, notify_status ('sent' | 'failed' | 'throttled')`
- Index `(vehicle_id, scanned_at)`.

## 4. QR token design (no PII)

```
token          = base64url( HMAC-SHA256(PARK_QR_SECRET, "v1:{vehicle_id}:{qr_nonce}") )[:32]
qr_token_hash  = SHA-256(token)          -- stored, UNIQUE, used for lookup
QR content     = {PARK_PUBLIC_BASE_URL}/park/s/{token}
```

- The token contains no plate, phone or user id, and can't be reversed into them.
- The DB never stores the token itself. A DB leak without `PARK_QR_SECRET`
  can't be used to forge valid QR URLs.
- The back office can redraw the QR at any time by recomputing it from the nonce.
- **Change QR** = new random `qr_nonce` → new token → the old sticker stops
  working immediately.
- `PARK_QR_SECRET` falls back to a key derived from `SECRET_KEY`. Set it
  explicitly so that rotating `SECRET_KEY` doesn't invalidate every printed QR.

## 5. Public scan flow

1. `GET /park/s/<token>` (rate limit 30/min/IP). Token format is checked, then
   looked up by hash. Unknown or inactive token → neutral "invalid code" page
   (404); the page doesn't reveal whether the vehicle exists.
2. The page shows a reason picker (blocking / lights on / window open / alarm /
   towing risk / other), an optional message (≤200 chars), an optional mobile
   number, an optional "share my location" button (browser Geolocation, which
   needs HTTPS), and the **reCAPTCHA v2 checkbox**.
3. `POST /park/s/<token>/notify` (rate limit 5 per 10 min per IP, plus CSRF token):
   - verify reCAPTCHA server-side (`siteverify`, with `remoteip`); fail closed
     if keys aren't set
   - validate and normalise mobile/geo/reason/message
   - **per-vehicle cooldown** (`PARK_NOTIFY_COOLDOWN_SECONDS`, default 60). If
     the owner was notified recently, record `throttled` and don't push again
   - publish to the owner's ntfy topic and record a scan row with the result
4. The browser plays the "notification sent" animation. It never sees the
   owner's details.

Only captcha-verified submissions are written to `park_scans`. Plain page views
aren't logged, so bots hitting the GET URL can't flood the table.

## 6. ntfy notification

Published as JSON to `{ntfy_server_url}`, so emoji and Sinhala/Tamil text
need no header encoding:

```
title:    "🚗 Parking alert: CAB-1234"
message:  "Someone needs you to move your vehicle.
           Note: <optional message>
           Contact: +94771234567          (if given)
           Location: https://maps.google.com/?q=lat,lng (if given)"
priority: 4 (high); 5 for towing risk
tags:     ["car", "warning"]
actions:  [ view "Call" tel:+94… ] (if a mobile number was given)
```

- Each user gets a random, unguessable topic (`park-<24 random chars>`). On
  public ntfy.sh, an unguessable topic name is what keeps it private. Users can
  regenerate it from the back office.
- The ntfy server and credentials come from the existing `app_settings` keys.
  If unset, the default is `https://ntfy.sh`.

## 7. Back office (`/park/`)

| Feature | Endpoint |
|---|---|
| Login (mobile + password), logout | `GET/POST /park/login`, `POST /park/logout` |
| Register (name, mobile, plate, password, reCAPTCHA) | `GET/POST /park/register` |
| Vehicles: list / add / delete / enable-disable | `/park/api/vehicles…` |
| **Change QR** (rotate) | `POST /park/api/vehicles/<id>/rotate-qr` |
| QR PNG / printable card | `GET /park/vehicles/<id>/qr.png`, `/print` |
| Scan history table (IP, mobile, lat/lng → map link, time, status) | `GET /park/api/scans?vehicle_id=` |
| **Change password** | `POST /park/api/account/password` |
| ntfy topic view / regenerate | `POST /park/api/account/ntfy-topic` |
| **Admin: list / add users / activate–deactivate** | `/park/api/admin/users…` |

All state-changing requests need the session CSRF token (`X-CSRF-Token` header
or form field). Every vehicle and scan query is scoped by `user_id`, so one
user can't read or rotate another user's QR (IDOR protection).

## 8. Validation (multi-country ready)

`validators.py` keeps a registry: `COUNTRIES = {"LK": CountryRules(...)}`. To
add a country, add one entry with `normalize_plate()` and `normalize_mobile()`.
`country_code` is already stored on users and vehicles.

**Sri Lanka plates** (spaces, hyphens and case are ignored on input):

| Series | Example input | Stored (normalized) | Display |
|---|---|---|---|
| Modern, 2 letters | `KA 1234`, `ka-1234` | `KA1234` | `KA-1234` |
| Modern, 3 letters | `CAB 1234` | `CAB1234` | `CAB-1234` |
| With province prefix | `WP CAB-1234` | `CAB1234` (+ region `WP`) | `WP CAB-1234` |
| Old numeric | `250-1234`, `65 1234` | `250-1234` | `250-1234` |
| "Sri" series | `19 ශ්‍රී 1234`, `19 SRI 1234` | `19SRI1234` | `19 ශ්‍රී 1234` |

Province codes: `WP CP SP NW NC UP SG NP EP`. The province prefix isn't part of
the unique number, so it's stored in `region_code`.

**Sri Lanka mobile**: `07XXXXXXXX`, `7XXXXXXXX`, `+947XXXXXXXX`, `00947…` →
stored as E.164 `+947XXXXXXXX`.

## 9. Security checklist

- reCAPTCHA v2 on scan-submit and on registration, verified server-side and
  failing closed
- Flask-Limiter on login (5/15 min), register, scan page, notify and admin APIs
- CSRF token on every POST; session cookie HttpOnly + SameSite=Lax (already
  set), Secure when `HTTPS_ENABLED=true`
- Passwords hashed with Werkzeug (scrypt/pbkdf2), minimum 8 characters; login
  errors are generic
- Parking session expires after `PARK_SESSION_HOURS` (default 12), separate
  from the budget app's 1-year cookie
- `session.clear()`-style fixation protection: parking keys are reset on login
- Parameterised SQL only; Jinja auto-escaping; user text is length-capped and
  control characters are stripped before it goes to ntfy
- The QR base URL comes from `PARK_PUBLIC_BASE_URL`, not the Host header, so a
  spoofed Host can't produce phishing QR links
- Security headers on `/park/*`: `X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`
  (keeps the token out of Referer)

## 10. Configuration (`.env`)

```
PARK_QR_SECRET=<python -c "import secrets;print(secrets.token_hex(32))">
PARK_PUBLIC_BASE_URL=https://your-domain.example
RECAPTCHA_SITE_KEY=...
RECAPTCHA_SECRET_KEY=...
PARK_NOTIFY_COOLDOWN_SECONDS=60
PARK_SESSION_HOURS=12
RATE_LIMIT_PARK_NOTIFY=5 per 10 minutes
RATE_LIMIT_PARK_SCAN_PAGE=30 per minute
```

## 11. Rollout steps

1. Add the env vars above (Google's test keys work for local development).
2. `flask --app app park-init-db` runs `schema.sql` (idempotent, `CREATE TABLE IF NOT EXISTS`).
3. `flask --app app park-create-admin` creates the first back-office admin.
4. Log in at `/park/login`, add a vehicle, print the QR card, subscribe to the
   ntfy topic in the ntfy app.
5. Scan the QR with a phone and confirm the push arrives and the scan row appears.

## 12. Future work

- OTP verification of the owner's mobile number at registration (SMS gateway)
- More countries: add entries to the `validators.py` registry
- Redis storage for Flask-Limiter when running more than one worker
- ProxyFix / trusted-proxy setting so the real client IP is recorded behind a reverse proxy
- Scan log retention policy (for example, purge after 180 days) for data minimisation
