-- Parking QR notifier tables. Isolated from the budget app's tables.
-- Idempotent: safe to run more than once (flask --app app park-init-db).

CREATE TABLE IF NOT EXISTS park_users (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    full_name           VARCHAR(100)  NULL,
    country_code        CHAR(2)       NOT NULL DEFAULT 'LK',
    mobile_e164         VARCHAR(20)   NOT NULL,
    password_hash       VARCHAR(255)  NOT NULL,
    ntfy_topic          VARCHAR(64)   NOT NULL,
    is_admin            BOOLEAN       NOT NULL DEFAULT FALSE,
    is_active           BOOLEAN       NOT NULL DEFAULT TRUE,
    scan_window_minutes INT           NOT NULL DEFAULT 10,
    created_at          TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at       TIMESTAMP     NULL,
    password_changed_at TIMESTAMP     NULL,
    UNIQUE KEY uq_park_users_mobile (mobile_e164),
    UNIQUE KEY uq_park_users_topic (ntfy_topic)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS park_vehicles (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    user_id             INT           NOT NULL,
    country_code        CHAR(2)       NOT NULL DEFAULT 'LK',
    plate_normalized    VARCHAR(32)   NOT NULL,
    plate_display       VARCHAR(48)   NOT NULL,
    region_code         VARCHAR(8)    NULL,
    nickname            VARCHAR(50)   NULL,
    qr_nonce            CHAR(32)      NOT NULL,
    qr_token_hash       CHAR(64)      NOT NULL,
    qr_rotated_at       TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active           BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_park_vehicles_token (qr_token_hash),
    UNIQUE KEY uq_park_vehicles_user_plate (user_id, country_code, plate_normalized),
    CONSTRAINT fk_park_vehicles_user FOREIGN KEY (user_id)
        REFERENCES park_users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS park_scans (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    vehicle_id          INT           NOT NULL,
    scanned_at          TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ip_address          VARCHAR(45)   NOT NULL,
    user_agent          VARCHAR(255)  NULL,
    scanner_mobile      VARCHAR(20)   NULL,
    latitude            DECIMAL(9,6)  NULL,
    longitude           DECIMAL(9,6)  NULL,
    location_accuracy_m INT           NULL,
    reason              VARCHAR(32)   NOT NULL,
    message             VARCHAR(200)  NULL,
    notify_status       VARCHAR(16)   NOT NULL,
    KEY ix_park_scans_vehicle_time (vehicle_id, scanned_at),
    CONSTRAINT fk_park_scans_vehicle FOREIGN KEY (vehicle_id)
        REFERENCES park_vehicles (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Migration for databases created before scan_window_minutes existed
-- (error 1060 "duplicate column" is ignored by init_schema on re-runs).
ALTER TABLE park_users ADD COLUMN scan_window_minutes INT NOT NULL DEFAULT 10 AFTER is_active;

-- Two-factor authentication (TOTP, compatible with Authy / Google Authenticator).
-- totp_last_step blocks code replay; totp_recovery is a JSON list of SHA-256 hashes of unused recovery codes.
ALTER TABLE park_users ADD COLUMN totp_secret VARCHAR(64) NULL;
ALTER TABLE park_users ADD COLUMN totp_enabled BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE park_users ADD COLUMN totp_last_step BIGINT NOT NULL DEFAULT 0;
ALTER TABLE park_users ADD COLUMN totp_recovery TEXT NULL;
