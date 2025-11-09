-- Migration: Add admin features to users table
-- Description: Adds is_admin, is_active, and last_login columns to support user management
-- Date: 2025-11-09

-- Add is_admin column (default to FALSE, existing users won't be admin)
ALTER TABLE users
ADD COLUMN is_admin BOOLEAN DEFAULT FALSE AFTER password_hash;

-- Add is_active column (default to TRUE, existing users remain active)
ALTER TABLE users
ADD COLUMN is_active BOOLEAN DEFAULT TRUE AFTER is_admin;

-- Add last_login timestamp
ALTER TABLE users
ADD COLUMN last_login TIMESTAMP NULL AFTER is_active;

-- Add created_at timestamp
ALTER TABLE users
ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP AFTER last_login;

-- Add updated_at timestamp
ALTER TABLE users
ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP AFTER created_at;

-- Create audit_logs table for tracking admin actions
CREATE TABLE IF NOT EXISTS audit_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    admin_user_id INT NOT NULL,
    action VARCHAR(100) NOT NULL,
    target_user_id INT,
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (admin_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (target_user_id) REFERENCES users(id) ON DELETE SET NULL,
    INDEX idx_admin_user (admin_user_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Set the first user as admin (if exists)
UPDATE users SET is_admin = TRUE ORDER BY id LIMIT 1;
