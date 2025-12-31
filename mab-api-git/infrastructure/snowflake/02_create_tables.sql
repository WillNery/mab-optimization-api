-- ============================================
-- Multi-Armed Bandit API - Tables
-- ============================================

USE DATABASE activeview_mab;
USE SCHEMA experiments;

-- ============================================
-- Experiments table
-- ============================================
CREATE TABLE IF NOT EXISTS experiments (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(20) DEFAULT 'active',
    optimization_target VARCHAR(20) DEFAULT 'ctr',
    created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    updated_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT uq_experiment_name UNIQUE (name)
);

-- ============================================
-- Variants table
-- Supports N variants (not just A/B)
-- ============================================
CREATE TABLE IF NOT EXISTS variants (
    id VARCHAR(36) PRIMARY KEY,
    experiment_id VARCHAR(36) NOT NULL,
    name VARCHAR(100) NOT NULL,
    is_control BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT fk_variant_experiment 
        FOREIGN KEY (experiment_id) REFERENCES experiments(id),
    CONSTRAINT uq_variant_name_per_experiment 
        UNIQUE (experiment_id, name)
);

-- ============================================
-- Raw Metrics table
-- Append-only, for audit and recovery
-- ============================================
CREATE TABLE IF NOT EXISTS raw_metrics (
    id VARCHAR(36) PRIMARY KEY,
    variant_id VARCHAR(36) NOT NULL,
    metric_date DATE NOT NULL,
    impressions INTEGER NOT NULL,
    clicks INTEGER NOT NULL,
    received_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT fk_raw_metrics_variant 
        FOREIGN KEY (variant_id) REFERENCES variants(id)
);

-- ============================================
-- Daily Metrics table
-- Clean, deduplicated data for API queries
-- ============================================
CREATE TABLE IF NOT EXISTS daily_metrics (
    id VARCHAR(36) PRIMARY KEY,
    variant_id VARCHAR(36) NOT NULL,
    metric_date DATE NOT NULL,
    impressions INTEGER NOT NULL DEFAULT 0,
    clicks INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    updated_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT fk_daily_metrics_variant 
        FOREIGN KEY (variant_id) REFERENCES variants(id),
    CONSTRAINT uq_daily_metrics_variant_date 
        UNIQUE (variant_id, metric_date)
);

-- ============================================
-- Indexes for performance
-- ============================================

-- Fast lookup of variants by experiment
CREATE INDEX IF NOT EXISTS idx_variants_experiment 
    ON variants(experiment_id);

-- Fast temporal queries on raw metrics
CREATE INDEX IF NOT EXISTS idx_raw_metrics_variant_date 
    ON raw_metrics(variant_id, metric_date);

-- Fast temporal queries on daily metrics (most common query)
CREATE INDEX IF NOT EXISTS idx_daily_metrics_variant_date 
    ON daily_metrics(variant_id, metric_date DESC);

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
