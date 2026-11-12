-- ============================================================================
-- CW Budget: schema additions
--
-- Everything here is created automatically by the app on first use, so running
-- this file is optional. Use it when the database user cannot run CREATE TABLE
-- at runtime, or to set up an environment by hand.
--
-- Safe to run more than once. No existing table is altered.
-- (The parking module keeps its own file: services/parking/schema.sql)
-- ============================================================================


-- ----------------------------------------------------------------------------
-- Scraper health (services/scraper_health_service.py)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS scraper_alert_state (
    source      VARCHAR(64) NOT NULL PRIMARY KEY,
    alerted_at  DATETIME    NOT NULL,
    last_error  TEXT        NULL
);

INSERT INTO app_settings (setting_key, value, description)
SELECT 'scraper_stale_minutes', '360',
       'Minutes without a successful exchange-rate fetch before a source is flagged stale'
WHERE NOT EXISTS (SELECT 1 FROM app_settings WHERE setting_key = 'scraper_stale_minutes');

INSERT INTO app_settings (setting_key, value, description)
SELECT 'ntfy_topic_admin', '',
       'ntfy topic for admin alerts (e.g. stale exchange-rate scrapers). Empty = log only'
WHERE NOT EXISTS (SELECT 1 FROM app_settings WHERE setting_key = 'ntfy_topic_admin');


-- ----------------------------------------------------------------------------
-- Offline sync (services/offline_sync.py)
-- Idempotency keys so a retried offline transaction is never created twice.
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS transaction_client_keys (
    user_id         INT         NOT NULL,
    client_id       VARCHAR(64) NOT NULL,
    transaction_id  INT         NOT NULL,
    created_at      TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, client_id)
);


-- ----------------------------------------------------------------------------
-- Planner (services/planner_service.py)
-- No foreign keys: kept independent of the users/categories/transactions
-- column types.
-- ----------------------------------------------------------------------------

-- Monthly spending limit per expense category
CREATE TABLE IF NOT EXISTS category_budgets (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    user_id       INT NOT NULL,
    category_id   INT NOT NULL,
    monthly_limit DECIMAL(14,2) NOT NULL,
    alert_percent TINYINT UNSIGNED NOT NULL DEFAULT 80,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_budget_user_cat (user_id, category_id)
);

-- Total-expenses budget: all spending (categorised + uncategorised),
-- limited to the month's total debit; only the warning % is stored
CREATE TABLE IF NOT EXISTS combined_budgets (
    user_id       INT NOT NULL PRIMARY KEY,
    alert_percent TINYINT UNSIGNED NOT NULL DEFAULT 80,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Which budget alerts were already pushed (one per level per month)
CREATE TABLE IF NOT EXISTS budget_alerts_sent (
    user_id     INT NOT NULL,
    category_id INT NOT NULL,
    year        SMALLINT NOT NULL,
    month       TINYINT NOT NULL,
    level       SMALLINT NOT NULL,
    sent_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, category_id, year, month, level)
);

-- Recurring transaction schedules
CREATE TABLE IF NOT EXISTS recurring_rules (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    user_id           INT NOT NULL,
    description       VARCHAR(255) NOT NULL,
    category_id       INT NULL,
    payment_method_id INT NULL,
    kind              VARCHAR(7) NOT NULL DEFAULT 'expense',   -- 'expense' | 'income'
    amount            DECIMAL(14,2) NOT NULL,
    notes             TEXT NULL,
    frequency         VARCHAR(8) NOT NULL DEFAULT 'monthly',   -- 'weekly' | 'monthly' | 'yearly'
    interval_count    SMALLINT UNSIGNED NOT NULL DEFAULT 1,
    anchor_day        TINYINT UNSIGNED NOT NULL,               -- day of month of the first date
    start_date        DATE NOT NULL,
    end_date          DATE NULL,
    next_run          DATE NOT NULL,
    last_run          DATE NULL,
    due_offset_days   SMALLINT NULL,                           -- bill due date = occurrence + N days
    remind_days       TINYINT UNSIGNED NOT NULL DEFAULT 3,
    is_active         TINYINT(1) NOT NULL DEFAULT 1,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_rec_user (user_id),
    KEY idx_rec_due (is_active, next_run)
);

-- One row per generated occurrence; the primary key prevents duplicates
CREATE TABLE IF NOT EXISTS recurring_runs (
    rule_id         INT NOT NULL,
    occurrence_date DATE NOT NULL,
    transaction_id  INT NULL,
    PRIMARY KEY (rule_id, occurrence_date)
);

-- Bill reminders: due date for a transaction
-- last_stage records the most urgent reminder already sent (0 = none)
CREATE TABLE IF NOT EXISTS transaction_due_dates (
    transaction_id INT NOT NULL PRIMARY KEY,
    user_id        INT NOT NULL,
    due_date       DATE NOT NULL,
    remind_days    TINYINT UNSIGNED NOT NULL DEFAULT 3,
    last_stage     TINYINT UNSIGNED NOT NULL DEFAULT 0,
    KEY idx_due_user (user_id, due_date)
);

-- Per-user ntfy topic for budget / bill / goal notifications
CREATE TABLE IF NOT EXISTS planner_settings (
    user_id    INT NOT NULL PRIMARY KEY,
    ntfy_topic VARCHAR(64) NULL
);

-- Savings goals and their contributions (a negative amount is a withdrawal)
CREATE TABLE IF NOT EXISTS savings_goals (
    id                 INT AUTO_INCREMENT PRIMARY KEY,
    user_id            INT NOT NULL,
    name               VARCHAR(120) NOT NULL,
    target_amount      DECIMAL(14,2) NOT NULL,
    target_date        DATE NULL,
    archived           TINYINT(1) NOT NULL DEFAULT 0,
    completed_notified TINYINT(1) NOT NULL DEFAULT 0,
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_goal_user (user_id)
);

CREATE TABLE IF NOT EXISTS savings_contributions (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    goal_id        INT NOT NULL,
    user_id        INT NOT NULL,
    amount         DECIMAL(14,2) NOT NULL,
    contributed_on DATE NOT NULL,
    note           VARCHAR(255) NULL,
    KEY idx_contrib_goal (goal_id)
);


-- ----------------------------------------------------------------------------
-- Optional (not created by the app): speeds up the scraper-health queries if
-- exchange_rate_refresh_logs is large and has no equivalent index.
-- ----------------------------------------------------------------------------
CREATE INDEX idx_refresh_logs_source_created ON exchange_rate_refresh_logs (source, created_at);
