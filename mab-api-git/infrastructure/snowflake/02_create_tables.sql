-- ============================================
-- Multi-Armed Bandit API - Tables (Production Ready)
-- ============================================
-- Melhorias implementadas:
-- 1. BIGINT para impressions/clicks/sessions (suporta bilhões)
-- 2. DECIMAL para revenue (precisão monetária)
-- 3. Clustering key para particionamento eficiente
-- 4. Colunas de observabilidade (source, batch_id)
-- 5. Política de retenção para raw_metrics
-- ============================================

USE DATABASE activeview_mab;
USE SCHEMA experiments;

-- ============================================
-- Experiments table
-- ============================================
CREATE OR REPLACE TABLE experiments (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(20) DEFAULT 'active',
    optimization_target VARCHAR(20) DEFAULT 'ctr',  -- 'ctr', 'rps', 'rpm'
    created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    updated_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT uq_experiment_name UNIQUE (name)
);

-- ============================================
-- Variants table
-- ============================================
CREATE OR REPLACE TABLE variants (
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
-- Raw Metrics table (append-only, auditoria)
-- ============================================
CREATE OR REPLACE TABLE raw_metrics (
    id VARCHAR(36) PRIMARY KEY,
    variant_id VARCHAR(36) NOT NULL,
    metric_date DATE NOT NULL,
    -- Métricas de volume
    sessions BIGINT NOT NULL DEFAULT 0,
    impressions BIGINT NOT NULL,
    clicks BIGINT NOT NULL,
    -- Métricas de receita
    revenue DECIMAL(18,6) NOT NULL DEFAULT 0,
    -- Timestamps
    received_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    -- Observabilidade
    source VARCHAR(50) DEFAULT 'api',
    batch_id VARCHAR(36),
    CONSTRAINT fk_raw_metrics_variant 
        FOREIGN KEY (variant_id) REFERENCES variants(id)
)
CLUSTER BY (metric_date);

-- ============================================
-- Daily Metrics table (dados limpos para algoritmo)
-- ============================================
CREATE OR REPLACE TABLE daily_metrics (
    id VARCHAR(36) PRIMARY KEY,
    variant_id VARCHAR(36) NOT NULL,
    metric_date DATE NOT NULL,
    -- Métricas de volume
    sessions BIGINT NOT NULL DEFAULT 0,
    impressions BIGINT NOT NULL DEFAULT 0,
    clicks BIGINT NOT NULL DEFAULT 0,
    -- Métricas de receita
    revenue DECIMAL(18,6) NOT NULL DEFAULT 0,
    -- Timestamps
    created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    updated_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT fk_daily_metrics_variant 
        FOREIGN KEY (variant_id) REFERENCES variants(id),
    CONSTRAINT uq_daily_metrics_variant_date 
        UNIQUE (variant_id, metric_date)
)
CLUSTER BY (variant_id, metric_date);

-- ============================================
-- View para métricas com retenção (últimos 120 dias)
-- ============================================
CREATE OR REPLACE VIEW raw_metrics_recent AS
SELECT *
FROM raw_metrics
WHERE received_at >= DATEADD(day, -120, CURRENT_DATE());

-- ============================================
-- View para métricas calculadas
-- Útil para dashboards e análises
-- ============================================
CREATE OR REPLACE VIEW daily_metrics_calculated AS
SELECT 
    m.*,
    v.name AS variant_name,
    v.is_control,
    e.name AS experiment_name,
    e.optimization_target,
    -- CTR (Click-Through Rate)
    CASE WHEN impressions > 0 THEN CAST(clicks AS FLOAT) / impressions ELSE 0 END AS ctr,
    -- RPS (Revenue Per Session)
    CASE WHEN sessions > 0 THEN revenue / sessions ELSE 0 END AS rps,
    -- RPM (Revenue Per Mille - receita por 1000 impressões)
    CASE WHEN impressions > 0 THEN (revenue / impressions) * 1000 ELSE 0 END AS rpm
FROM daily_metrics m
JOIN variants v ON v.id = m.variant_id
JOIN experiments e ON e.id = v.experiment_id;

-- ============================================
-- Política de Retenção para raw_metrics
-- Move dados > 120 dias para cold storage
-- ============================================

/*
CREATE OR REPLACE STAGE raw_metrics_archive
    URL = 's3://activeview-data-archive/raw_metrics/'
    CREDENTIALS = (AWS_KEY_ID = '...' AWS_SECRET_KEY = '...')
    FILE_FORMAT = (TYPE = PARQUET);

CREATE OR REPLACE TASK archive_old_raw_metrics
    WAREHOUSE = compute_wh
    SCHEDULE = 'USING CRON 0 2 * * * UTC'
AS
BEGIN
    COPY INTO @raw_metrics_archive
    FROM (
        SELECT * FROM raw_metrics 
        WHERE received_at < DATEADD(day, -120, CURRENT_DATE())
    )
    PARTITION BY (TO_VARCHAR(metric_date, 'YYYY-MM'))
    FILE_FORMAT = (TYPE = PARQUET)
    OVERWRITE = FALSE;
    
    DELETE FROM raw_metrics 
    WHERE received_at < DATEADD(day, -120, CURRENT_DATE());
END;

ALTER TASK archive_old_raw_metrics RESUME;
*/

-- ============================================
-- Grants (ajuste conforme sua estrutura de roles)
-- ============================================
/*
GRANT SELECT, INSERT ON experiments TO ROLE mab_api_role;
GRANT SELECT, INSERT ON variants TO ROLE mab_api_role;
GRANT SELECT, INSERT, DELETE ON raw_metrics TO ROLE mab_api_role;
GRANT SELECT, INSERT, UPDATE ON daily_metrics TO ROLE mab_api_role;
GRANT SELECT ON daily_metrics_calculated TO ROLE mab_api_role;
*/
