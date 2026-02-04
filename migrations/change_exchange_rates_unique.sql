-- Migration: allow one row per (date, source) instead of one row per date
-- This lets CBSL and HNB rates coexist for the same date.
--
-- Run once against the existing database:
--   mysql -h <host> -P <port> -u <user> -p <db> < migrations/change_exchange_rates_unique.sql

ALTER TABLE exchange_rates DROP INDEX `date`;
ALTER TABLE exchange_rates ADD UNIQUE KEY unique_date_source (date, source);
