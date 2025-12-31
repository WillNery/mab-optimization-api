-- ============================================
-- Migration: Add allocation_history table
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
    allocations VARIANT NOT NULL,
    created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT fk_allocation_history_experiment 
        FOREIGN KEY (experiment_id) REFERENCES experiments(id)
);

-- Index for fast history queries
CREATE INDEX IF NOT EXISTS idx_allocation_history_experiment_date 
    ON allocation_history(experiment_id, computed_at DESC);

-- Verify table was created
SHOW TABLES LIKE 'allocation_history';
