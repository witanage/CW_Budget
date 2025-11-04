-- Add is_paid column to track when description cell is clicked to mark as paid
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS is_paid BOOLEAN DEFAULT FALSE AFTER is_done,
ADD COLUMN IF NOT EXISTS paid_at TIMESTAMP NULL AFTER is_paid;
