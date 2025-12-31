-- ============================================
-- Migration: Add allocation_history tables
-- Run this if you already have the database
-- ============================================

USE DATABASE activeview_mab;
USE SCHEMA experiments;

-- ============================================
-- Add optimization_target to experiments (if not exists)
-- ============================================
ALTER TABLE experiments ADD COLUMN IF NOT EXISTS optimization_target VARCHAR(20) DEFAULT 'ctr';

-- ============================================
-- Allocation History table
-- Audit trail of all allocation decisions
-- ============================================
CREATE TABLE IF NOT EXISTS allocation_history (
    id VARCHAR(36) PRIMARY KEY,
    experiment_id VARCHAR(36) NOT NULL,
    computed_at TIMESTAMP_NTZ NOT NULL,
    window_days INTEGER NOT NULL,
    algorithm VARCHAR(50) NOT NULL,
    algorithm_version VARCHAR(20) NOT NULL,
    seed BIGINT NOT NULL,
    used_fallback BOOLEAN DEFAULT FALSE,
    total_impressions BIGINT NOT NULL,
    total_clicks BIGINT NOT NULL,
    created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT fk_allocation_history_experiment 
        FOREIGN KEY (experiment_id) REFERENCES experiments(id)
);

-- ============================================
-- Allocation History Details table
-- Per-variant allocation details
-- ============================================
CREATE TABLE IF NOT EXISTS allocation_history_details (
    id VARCHAR(36) PRIMARY KEY,
    allocation_history_id VARCHAR(36) NOT NULL,
    variant_id VARCHAR(36) NOT NULL,
    variant_name VARCHAR(100) NOT NULL,
    is_control BOOLEAN NOT NULL,
    allocation_percentage FLOAT NOT NULL,
    impressions BIGINT NOT NULL,
    clicks BIGINT NOT NULL,
    ctr FLOAT NOT NULL,
    beta_alpha FLOAT NOT NULL,
    beta_beta FLOAT NOT NULL,
    CONSTRAINT fk_allocation_detail_history 
        FOREIGN KEY (allocation_history_id) REFERENCES allocation_history(id),
    CONSTRAINT fk_allocation_detail_variant 
        FOREIGN KEY (variant_id) REFERENCES variants(id)
);

-- Index for fast history queries
CREATE INDEX IF NOT EXISTS idx_allocation_history_experiment_date 
    ON allocation_history(experiment_id, computed_at DESC);

-- Verify tables were created
SHOW TABLES LIKE 'allocation_history%';
