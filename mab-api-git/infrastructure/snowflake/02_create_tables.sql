-- ============================================
-- Multi-Armed Bandit API
-- 02: Create Tables
-- ============================================

USE DATABASE activeview_mab;
USE SCHEMA experiments;

-- ============================================
-- Experiments
-- ============================================
CREATE TABLE IF NOT EXISTS experiments (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    status VARCHAR(20) DEFAULT 'active',
    optimization_target VARCHAR(20) DEFAULT 'ctr',
    created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    updated_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- ============================================
-- Variants
-- ============================================
CREATE TABLE IF NOT EXISTS variants (
    id VARCHAR(36) PRIMARY KEY,
    experiment_id VARCHAR(36) NOT NULL REFERENCES experiments(id),
    name VARCHAR(100) NOT NULL,
    is_control BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    UNIQUE (experiment_id, name)
);

-- ============================================
-- Raw Metrics (append-only, auditoria)
-- ============================================
CREATE TABLE IF NOT EXISTS raw_metrics (
    id VARCHAR(36) PRIMARY KEY,
    variant_id VARCHAR(36) NOT NULL REFERENCES variants(id),
    metric_date DATE NOT NULL,
    sessions BIGINT NOT NULL DEFAULT 0,
    impressions BIGINT NOT NULL,
    clicks BIGINT NOT NULL,
    revenue DECIMAL(18,6) NOT NULL DEFAULT 0,
    received_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    source VARCHAR(50) DEFAULT 'api',
    batch_id VARCHAR(36)
) CLUSTER BY (metric_date);

-- ============================================
-- Daily Metrics (dados limpos para cálculo)
-- ============================================
CREATE TABLE IF NOT EXISTS daily_metrics (
    id VARCHAR(36) PRIMARY KEY,
    variant_id VARCHAR(36) NOT NULL REFERENCES variants(id),
    metric_date DATE NOT NULL,
    sessions BIGINT NOT NULL DEFAULT 0,
    impressions BIGINT NOT NULL DEFAULT 0,
    clicks BIGINT NOT NULL DEFAULT 0,
    revenue DECIMAL(18,6) NOT NULL DEFAULT 0,
    created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    updated_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    UNIQUE (variant_id, metric_date)
) CLUSTER BY (variant_id, metric_date);

-- ============================================
-- Allocation History (auditoria de decisões)
-- ============================================
CREATE TABLE IF NOT EXISTS allocation_history (
    id VARCHAR(36) PRIMARY KEY,
    experiment_id VARCHAR(36) NOT NULL REFERENCES experiments(id),
    computed_at TIMESTAMP_NTZ NOT NULL,
    window_days INTEGER NOT NULL,
    algorithm VARCHAR(50) NOT NULL,
    algorithm_version VARCHAR(20) NOT NULL,
    seed BIGINT NOT NULL,
    used_fallback BOOLEAN DEFAULT FALSE,
    total_impressions BIGINT NOT NULL,
    total_clicks BIGINT NOT NULL,
    allocations VARIANT NOT NULL,
    created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
) CLUSTER BY (experiment_id, computed_at);

-- ============================================
-- Verify
-- ============================================
SHOW TABLES;
