-- ============================================
-- Multi-Armed Bandit API - Tables (Production Ready)
-- ============================================
-- Melhorias implementadas:
-- 1. BIGINT para impressions/clicks (suporta bilhões)
-- 2. Clustering key para particionamento eficiente
-- 3. Colunas de observabilidade (source, batch_id)
-- 4. Política de retenção para raw_metrics
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
-- Melhorias:
--   - BIGINT para suportar volumes altos
--   - source: origem dos dados (gam, cdp, manual)
--   - batch_id: ID do job/ingestão para rastreamento
--   - Clustering por data para queries de auditoria
-- ============================================
CREATE OR REPLACE TABLE raw_metrics (
    id VARCHAR(36) PRIMARY KEY,
    variant_id VARCHAR(36) NOT NULL,
    metric_date DATE NOT NULL,
    impressions BIGINT NOT NULL,
    clicks BIGINT NOT NULL,
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
-- Melhorias:
--   - BIGINT para suportar volumes altos
--   - Clustering por variant_id e metric_date
--     (otimiza a query principal do Thompson Sampling)
-- ============================================
CREATE OR REPLACE TABLE daily_metrics (
    id VARCHAR(36) PRIMARY KEY,
    variant_id VARCHAR(36) NOT NULL,
    metric_date DATE NOT NULL,
    impressions BIGINT NOT NULL DEFAULT 0,
    clicks BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    updated_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT fk_daily_metrics_variant 
        FOREIGN KEY (variant_id) REFERENCES variants(id),
    CONSTRAINT uq_daily_metrics_variant_date 
        UNIQUE (variant_id, metric_date)
)
CLUSTER BY (variant_id, metric_date);

-- ============================================
-- Política de Retenção para raw_metrics
-- Move dados > 120 dias para cold storage
-- ============================================

-- Criar stage para cold storage (S3)
-- Nota: Ajuste a URL e credenciais conforme seu ambiente
/*
CREATE OR REPLACE STAGE raw_metrics_archive
    URL = 's3://activeview-data-archive/raw_metrics/'
    CREDENTIALS = (AWS_KEY_ID = '...' AWS_SECRET_KEY = '...')
    FILE_FORMAT = (TYPE = PARQUET);
*/

-- Task para arquivar dados antigos (roda diariamente)
/*
CREATE OR REPLACE TASK archive_old_raw_metrics
    WAREHOUSE = compute_wh
    SCHEDULE = 'USING CRON 0 2 * * * UTC'  -- 2 AM UTC diariamente
AS
BEGIN
    -- Copiar dados antigos para S3
    COPY INTO @raw_metrics_archive
    FROM (
        SELECT * FROM raw_metrics 
        WHERE received_at < DATEADD(day, -120, CURRENT_DATE())
    )
    PARTITION BY (TO_VARCHAR(metric_date, 'YYYY-MM'))
    FILE_FORMAT = (TYPE = PARQUET)
    OVERWRITE = FALSE;
    
    -- Deletar dados arquivados
    DELETE FROM raw_metrics 
    WHERE received_at < DATEADD(day, -120, CURRENT_DATE());
END;

-- Ativar a task
ALTER TASK archive_old_raw_metrics RESUME;
*/

-- ============================================
-- View para métricas com retenção (últimos 120 dias)
-- Útil para queries que não precisam de histórico completo
-- ============================================
CREATE OR REPLACE VIEW raw_metrics_recent AS
SELECT *
FROM raw_metrics
WHERE received_at >= DATEADD(day, -120, CURRENT_DATE());

-- ============================================
-- Grants (permissões de acessos as tabelas)
-- ============================================
/*
GRANT SELECT, INSERT ON experiments TO ROLE mab_api_role;
GRANT SELECT, INSERT ON variants TO ROLE mab_api_role;
GRANT SELECT, INSERT, DELETE ON raw_metrics TO ROLE mab_api_role;
GRANT SELECT, INSERT, UPDATE ON daily_metrics TO ROLE mab_api_role;
*/
