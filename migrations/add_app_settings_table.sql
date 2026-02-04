-- Migration: add app_settings table for runtime-configurable application settings.
-- Run once against the existing database:
--   mysql -h <host> -P <port> -u <user> -p <db> < migrations/add_app_settings_table.sql

CREATE TABLE IF NOT EXISTS app_settings (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Runtime application settings (key-value store)';

-- Seed default settings (INSERT IGNORE keeps any value you have already customised)
INSERT IGNORE INTO app_settings (key, value, description) VALUES
('exchange_rate_refresh_interval_minutes', '60',
 'How often (in minutes) the background scheduler fetches fresh exchange rates from all banks');
