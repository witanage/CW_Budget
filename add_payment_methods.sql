-- Create payment_methods table to store cash and credit cards
CREATE TABLE IF NOT EXISTS payment_methods (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    name VARCHAR(100) NOT NULL,
    type ENUM('cash', 'credit_card') NOT NULL DEFAULT 'cash',
    color VARCHAR(7) DEFAULT '#28a745',  -- Default green for cash
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY unique_user_payment_method (user_id, name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Add columns to transactions table
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS is_done BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS payment_method_id INT NULL,
ADD COLUMN IF NOT EXISTS marked_done_at TIMESTAMP NULL,
ADD FOREIGN KEY (payment_method_id) REFERENCES payment_methods(id) ON DELETE SET NULL;

-- Insert default Cash payment method for existing users
INSERT INTO payment_methods (user_id, name, type, color)
SELECT DISTINCT id, 'Cash', 'cash', '#28a745'
FROM users
WHERE id NOT IN (SELECT DISTINCT user_id FROM payment_methods WHERE name = 'Cash')
ON DUPLICATE KEY UPDATE updated_at = CURRENT_TIMESTAMP;
