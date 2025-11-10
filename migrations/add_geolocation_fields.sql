-- ============================================================
-- Migration: Add Geolocation Fields to Transactions Table
-- ============================================================
-- This migration adds latitude, longitude, and accuracy fields
-- to track the location where transactions are marked as done/paid
-- Date: 2025-11-10
-- ============================================================

-- Add geolocation fields for "mark as done" action
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS done_latitude DECIMAL(10, 8) NULL COMMENT 'Latitude when marked as done' AFTER paid_at,
ADD COLUMN IF NOT EXISTS done_longitude DECIMAL(11, 8) NULL COMMENT 'Longitude when marked as done' AFTER done_latitude,
ADD COLUMN IF NOT EXISTS done_location_accuracy DECIMAL(10, 2) NULL COMMENT 'Location accuracy in meters when marked as done' AFTER done_longitude;

-- Add geolocation fields for "mark as paid" action
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS paid_latitude DECIMAL(10, 8) NULL COMMENT 'Latitude when marked as paid' AFTER done_location_accuracy,
ADD COLUMN IF NOT EXISTS paid_longitude DECIMAL(11, 8) NULL COMMENT 'Longitude when marked as paid' AFTER paid_latitude,
ADD COLUMN IF NOT EXISTS paid_location_accuracy DECIMAL(10, 2) NULL COMMENT 'Location accuracy in meters when marked as paid' AFTER paid_longitude;

-- ============================================================
-- Usage Notes:
-- ============================================================
-- Run this migration after updating the application code:
-- mysql -u [username] -p [database_name] < migrations/add_geolocation_fields.sql
--
-- Geolocation is captured using the browser's Geolocation API
-- If the user denies permission, the fields will remain NULL
-- ============================================================
