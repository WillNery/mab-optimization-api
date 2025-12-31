-- ============================================
-- Multi-Armed Bandit API
-- 03: Migration - Add sessions, revenue, allocation_history
-- 
-- USE ESTE ARQUIVO APENAS SE:
-- - Você já tem o banco criado
-- - Você já tem dados nas tabelas
-- - Precisa adicionar as novas colunas sem perder dados
-- ============================================

USE DATABASE activeview_mab;
USE SCHEMA experiments;

-- ============================================
-- 1. Add optimization_target to experiments
-- ============================================
ALTER TABLE experiments 
ADD COLUMN IF NOT EXISTS optimization_target VARCHAR(20) DEFAULT 'ctr';

-- ============================================
-- 2. Add sessions and revenue to raw_metrics
-- ============================================
ALTER TABLE raw_metrics 
ADD COLUMN IF NOT EXISTS sessions BIGINT DEFAULT 0;

ALTER TABLE raw_metrics 
ADD COLUMN IF NOT EXISTS revenue DECIMAL(18,6) DEFAULT 0;

ALTER TABLE raw_metrics 
ADD COLUMN IF NOT EXISTS source VARCHAR(50) DEFAULT 'api';

ALTER TABLE raw_metrics 
ADD COLUMN IF NOT EXISTS batch_id VARCHAR(36);

-- Change impressions/clicks from INTEGER to BIGINT
ALTER TABLE raw_metrics 
MODIFY COLUMN impressions BIGINT;

ALTER TABLE raw_metrics 
MODIFY COLUMN clicks BIGINT;

-- ============================================
-- 3. Add sessions and revenue to daily_metrics
-- ============================================
ALTER TABLE daily_metrics 
ADD COLUMN IF NOT EXISTS sessions BIGINT DEFAULT 0;

ALTER TABLE daily_metrics 
ADD COLUMN IF NOT EXISTS revenue DECIMAL(18,6) DEFAULT 0;

-- Change impressions/clicks from INTEGER to BIGINT
ALTER TABLE daily_metrics 
MODIFY COLUMN impressions BIGINT;

ALTER TABLE daily_metrics 
MODIFY COLUMN clicks BIGINT;

-- ============================================
-- 4. Create allocation_history table
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
-- 5. Verify changes
-- ============================================
DESCRIBE TABLE experiments;
DESCRIBE TABLE raw_metrics;
DESCRIBE TABLE daily_metrics;
DESCRIBE TABLE allocation_history;
