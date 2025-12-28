# Dicionário de Dados

## Visão Geral

Este documento descreve as tabelas do banco de dados do sistema Multi-Armed Bandit Optimization API.

**Database:** `activeview_mab`  
**Schema:** `experiments`

---

## Diagrama de Relacionamentos

```
experiments (1) ──────< variants (1) ──────< daily_metrics
                           │
                           └──────< raw_metrics
```

---

## Tabela: `experiments`

Armazena os experimentos A/B/N criados no sistema.

| Coluna | Tipo | Nullable | Default | Descrição |
|--------|------|----------|---------|-----------|
| `id` | VARCHAR(36) | NOT NULL | - | Identificador único do experimento (UUID) |
| `name` | VARCHAR(255) | NOT NULL | - | Nome do experimento (único) |
| `description` | TEXT | NULL | NULL | Descrição do experimento |
| `status` | VARCHAR(20) | NOT NULL | 'active' | Status: 'active', 'paused', 'completed' |
| `optimization_target` | VARCHAR(20) | NOT NULL | 'ctr' | Métrica a otimizar: 'ctr', 'rps', 'rpm' |
| `created_at` | TIMESTAMP_NTZ | NOT NULL | CURRENT_TIMESTAMP() | Data/hora de criação |
| `updated_at` | TIMESTAMP_NTZ | NOT NULL | CURRENT_TIMESTAMP() | Data/hora da última atualização |

**Constraints:**
- `PRIMARY KEY (id)`
- `UNIQUE (name)`

**Optimization Targets:**

| Valor | Métrica | Fórmula |
|-------|---------|---------|
| `ctr` | Click-Through Rate | clicks / impressions |
| `rps` | Revenue Per Session | revenue / sessions |
| `rpm` | Revenue Per Mille | (revenue / impressions) × 1000 |

---

## Tabela: `variants`

Armazena as variantes de cada experimento. Suporta N variantes (não apenas A/B).

| Coluna | Tipo | Nullable | Default | Descrição |
|--------|------|----------|---------|-----------|
| `id` | VARCHAR(36) | NOT NULL | - | Identificador único da variante (UUID) |
| `experiment_id` | VARCHAR(36) | NOT NULL | - | FK para experiments.id |
| `name` | VARCHAR(100) | NOT NULL | - | Nome da variante (ex: 'control', 'variant_a') |
| `is_control` | BOOLEAN | NOT NULL | FALSE | Indica se é a variante de controle |
| `created_at` | TIMESTAMP_NTZ | NOT NULL | CURRENT_TIMESTAMP() | Data/hora de criação |

**Constraints:**
- `PRIMARY KEY (id)`
- `FOREIGN KEY (experiment_id) REFERENCES experiments(id)`
- `UNIQUE (experiment_id, name)` — nomes únicos por experimento

---

## Tabela: `raw_metrics`

Armazena métricas brutas recebidas. **Append-only** para auditoria e recuperação de dados.

| Coluna | Tipo | Nullable | Default | Descrição |
|--------|------|----------|---------|-----------|
| `id` | VARCHAR(36) | NOT NULL | - | Identificador único do registro (UUID) |
| `variant_id` | VARCHAR(36) | NOT NULL | - | FK para variants.id |
| `metric_date` | DATE | NOT NULL | - | Data das métricas (YYYY-MM-DD) |
| `sessions` | BIGINT | NOT NULL | 0 | Número de sessões únicas |
| `impressions` | BIGINT | NOT NULL | - | Número de impressões |
| `clicks` | BIGINT | NOT NULL | - | Número de clicks |
| `revenue` | DECIMAL(18,6) | NOT NULL | 0 | Receita em USD |
| `received_at` | TIMESTAMP_NTZ | NOT NULL | CURRENT_TIMESTAMP() | Timestamp de recebimento |
| `source` | VARCHAR(50) | NOT NULL | 'api' | Origem dos dados: 'api', 'gam', 'cdp', 'manual' |
| `batch_id` | VARCHAR(36) | NULL | NULL | ID do batch de ingestão para rastreabilidade |

**Constraints:**
- `PRIMARY KEY (id)`
- `FOREIGN KEY (variant_id) REFERENCES variants(id)`

**Clustering:**
- `CLUSTER BY (metric_date)` — otimiza queries por período

**Uso:**
- Populado via `POST /experiments/{id}/metrics`
- Não é lido diretamente pela API (apenas para auditoria)
- Pode conter duplicatas (histórico completo)

---

## Tabela: `daily_metrics`

Armazena métricas limpas e deduplicadas. **Usada pelo algoritmo Thompson Sampling**.

| Coluna | Tipo | Nullable | Default | Descrição |
|--------|------|----------|---------|-----------|
| `id` | VARCHAR(36) | NOT NULL | - | Identificador único do registro (UUID) |
| `variant_id` | VARCHAR(36) | NOT NULL | - | FK para variants.id |
| `metric_date` | DATE | NOT NULL | - | Data das métricas (YYYY-MM-DD) |
| `sessions` | BIGINT | NOT NULL | 0 | Número de sessões únicas |
| `impressions` | BIGINT | NOT NULL | 0 | Número de impressões |
| `clicks` | BIGINT | NOT NULL | 0 | Número de clicks |
| `revenue` | DECIMAL(18,6) | NOT NULL | 0 | Receita em USD |
| `created_at` | TIMESTAMP_NTZ | NOT NULL | CURRENT_TIMESTAMP() | Data/hora de criação |
| `updated_at` | TIMESTAMP_NTZ | NOT NULL | CURRENT_TIMESTAMP() | Data/hora da última atualização |

**Constraints:**
- `PRIMARY KEY (id)`
- `FOREIGN KEY (variant_id) REFERENCES variants(id)`
- `UNIQUE (variant_id, metric_date)` — uma linha por variante/dia

**Clustering:**
- `CLUSTER BY (variant_id, metric_date)` — otimiza a query principal do Thompson Sampling

---

## View: `daily_metrics_calculated`

View que adiciona métricas calculadas aos dados diários.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| (todas de daily_metrics) | - | Colunas originais |
| `variant_name` | VARCHAR | Nome da variante |
| `is_control` | BOOLEAN | Se é controle |
| `experiment_name` | VARCHAR | Nome do experimento |
| `optimization_target` | VARCHAR | Métrica sendo otimizada |
| `ctr` | FLOAT | Click-Through Rate |
| `rps` | FLOAT | Revenue Per Session |
| `rpm` | FLOAT | Revenue Per Mille |

---

## View: `raw_metrics_recent`

View que filtra apenas métricas recentes (últimos 120 dias).

```sql
CREATE VIEW raw_metrics_recent AS
SELECT *
FROM raw_metrics
WHERE received_at >= DATEADD(day, -120, CURRENT_DATE());
```

---

## Fluxo de Dados

```
                    POST /experiments
                          │
                          ▼
                   ┌─────────────┐
                   │ experiments │
                   │             │
                   │ + optimization_target
                   └──────┬──────┘
                          │
                          ▼
                   ┌─────────────┐
                   │  variants   │
                   └──────┬──────┘
                          │
        POST /metrics     │
              │           │
              ▼           │
       ┌─────────────┐    │
       │ raw_metrics │    │  (auditoria)
       │             │    │
       │ + sessions  │    │
       │ + revenue   │    │
       └─────────────┘    │
              │           │
              ▼           │
       ┌─────────────┐    │
       │daily_metrics│◄───┘  (upsert)
       │             │
       │ + sessions  │
       │ + revenue   │
       └──────┬──────┘
              │
              │  GET /allocation
              ▼
       ┌─────────────┐
       │  Thompson   │
       │  Sampling   │
       │             │
       │ CTR ou RPS  │
       │ ou RPM      │
       └─────────────┘
```

---

## Tipos de Dados

| Tipo | Uso | Capacidade |
|------|-----|------------|
| VARCHAR(36) | UUIDs | 36 caracteres |
| VARCHAR(50) | source | 50 caracteres |
| VARCHAR(100) | variant name | 100 caracteres |
| VARCHAR(255) | experiment name | 255 caracteres |
| TEXT | description | Ilimitado |
| BIGINT | sessions, impressions, clicks | -9.2×10¹⁸ a 9.2×10¹⁸ |
| DECIMAL(18,6) | revenue | 18 dígitos, 6 decimais |
| BOOLEAN | is_control | true/false |
| DATE | metric_date | YYYY-MM-DD |
| TIMESTAMP_NTZ | timestamps | Sem timezone |

---

## Métricas Calculadas

| Métrica | Fórmula | Descrição |
|---------|---------|-----------|
| **CTR** | clicks / impressions | Taxa de cliques por impressão |
| **RPS** | revenue / sessions | Receita média por sessão |
| **RPM** | (revenue / impressions) × 1000 | Receita por mil impressões |

---

## Clustering e Performance

O Snowflake não usa índices tradicionais. Em vez disso, usa:

**Clustering Keys:**
- `raw_metrics`: `CLUSTER BY (metric_date)`
- `daily_metrics`: `CLUSTER BY (variant_id, metric_date)`

Isso otimiza:
- Queries por período em `raw_metrics`
- A query principal do Thompson Sampling em `daily_metrics`

---

## Diferença entre raw_metrics e daily_metrics

| Aspecto | raw_metrics | daily_metrics |
|---------|-------------|---------------|
| Propósito | Auditoria | Cálculo |
| Operação | INSERT (append) | UPSERT (merge) |
| Duplicatas | Permitidas | Não permitidas |
| Leitura | Rara (debug) | Frequente (API) |
| Retenção | 120 dias hot | Permanente |
| Observabilidade | source, batch_id | Não tem |

Se `daily_metrics` corromper, pode ser reconstruída a partir de `raw_metrics`.

---

## Exemplo de Dados

### experiments
| id | name | optimization_target | status |
|----|------|---------------------|--------|
| abc-123 | teste_botao | rpm | active |

### variants
| id | experiment_id | name | is_control |
|----|---------------|------|------------|
| v1 | abc-123 | azul | true |
| v2 | abc-123 | verde | false |

### daily_metrics
| variant_id | metric_date | sessions | impressions | clicks | revenue |
|------------|-------------|----------|-------------|--------|---------|
| v1 | 2025-01-15 | 5000 | 10000 | 320 | 150.50 |
| v2 | 2025-01-15 | 5200 | 10000 | 380 | 185.75 |

### Métricas calculadas
| variant | CTR | RPS | RPM |
|---------|-----|-----|-----|
| azul | 3.2% | $0.0301 | $15.05 |
| verde | 3.8% | $0.0357 | $18.58 |
