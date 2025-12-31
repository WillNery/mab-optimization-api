# Entity Relationship Diagram (ERD)

## Diagrama

```mermaid
erDiagram
    experiments ||--o{ variants : "has"
    experiments ||--o{ allocation_history : "has"
    variants ||--o{ raw_metrics : "has"
    variants ||--o{ daily_metrics : "has"

    experiments {
        varchar_36 id PK
        varchar_255 name UK
        text description
        varchar_20 status
        timestamp_ntz created_at
        timestamp_ntz updated_at
    }

    variants {
        varchar_36 id PK
        varchar_36 experiment_id FK
        varchar_100 name
        boolean is_control
        timestamp_ntz created_at
    }

    raw_metrics {
        varchar_36 id PK
        varchar_36 variant_id FK
        date metric_date
        bigint sessions
        bigint impressions
        bigint clicks
        decimal_18_6 revenue
        timestamp_ntz received_at
        varchar_50 source
        varchar_36 batch_id
    }

    daily_metrics {
        varchar_36 id PK
        varchar_36 variant_id FK
        date metric_date
        bigint sessions
        bigint impressions
        bigint clicks
        decimal_18_6 revenue
        timestamp_ntz created_at
        timestamp_ntz updated_at
    }

    allocation_history {
        varchar_36 id PK
        varchar_36 experiment_id FK
        timestamp_ntz computed_at
        integer window_days
        varchar_50 algorithm
        varchar_20 algorithm_version
        bigint seed
        boolean used_fallback
        bigint total_impressions
        bigint total_clicks
        variant allocations
        timestamp_ntz created_at
    }
```

---

## Relacionamentos

| De | Para | Cardinalidade | Descrição |
|----|------|---------------|-----------|
| experiments | variants | 1:N | Um experimento tem N variantes |
| experiments | allocation_history | 1:N | Um experimento tem N registros de alocação |
| variants | raw_metrics | 1:N | Uma variante tem N registros de métricas brutas |
| variants | daily_metrics | 1:N | Uma variante tem N registros de métricas diárias |

---

## Constraints

| Tabela | Constraint | Tipo | Colunas |
|--------|------------|------|---------|
| experiments | PK | PRIMARY KEY | id |
| experiments | uq_experiment_name | UNIQUE | name |
| variants | PK | PRIMARY KEY | id |
| variants | fk_variant_experiment | FOREIGN KEY | experiment_id → experiments.id |
| variants | uq_variant_name_per_experiment | UNIQUE | (experiment_id, name) |
| raw_metrics | PK | PRIMARY KEY | id |
| raw_metrics | fk_raw_metrics_variant | FOREIGN KEY | variant_id → variants.id |
| daily_metrics | PK | PRIMARY KEY | id |
| daily_metrics | fk_daily_metrics_variant | FOREIGN KEY | variant_id → variants.id |
| daily_metrics | uq_daily_metrics_variant_date | UNIQUE | (variant_id, metric_date) |
| allocation_history | PK | PRIMARY KEY | id |
| allocation_history | fk_allocation_history_experiment | FOREIGN KEY | experiment_id → experiments.id |

---

## Clustering Keys (Snowflake)

| Tabela | Clustering Key | Propósito |
|--------|----------------|-----------|
| raw_metrics | metric_date | Otimiza queries de auditoria por período |
| daily_metrics | (variant_id, metric_date) | Otimiza query do Thompson Sampling |
| allocation_history | (experiment_id, computed_at) | Otimiza queries de auditoria por experimento/data |

---

## Fluxo de Dados

```
┌─────────────────────────────────────────────────────────────────┐
│                        POST /experiments                         │
└─────────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
                    ┌───────────────────┐
                    │    experiments    │
                    │                   │
                    │  id (PK)          │
                    │  name (UK)        │
                    │  description      │
                    │  status           │
                    │  created_at       │
                    │  updated_at       │
                    └─────────┬─────────┘
                              │ 1:N
                              ▼
                    ┌───────────────────┐
                    │     variants      │
                    │                   │
                    │  id (PK)          │
                    │  experiment_id(FK)│
                    │  name             │
                    │  is_control       │
                    │  created_at       │
                    └─────────┬─────────┘
                              │
              ┌───────────────┴───────────────┐
              │ 1:N                           │ 1:N
              ▼                               ▼
┌───────────────────────┐       ┌───────────────────────┐
│     raw_metrics       │       │    daily_metrics      │
│     (auditoria)       │       │     (cálculo)         │
│                       │       │                       │
│  id (PK)              │       │  id (PK)              │
│  variant_id (FK)      │       │  variant_id (FK)      │
│  metric_date          │       │  metric_date          │
│  sessions             │       │  sessions             │
│  impressions (BIGINT) │       │  impressions (BIGINT) │
│  clicks (BIGINT)      │       │  clicks (BIGINT)      │
│  revenue              │       │  revenue              │
│  received_at          │       │  created_at           │
│  source               │       │  updated_at           │
│  batch_id             │       │                       │
└───────────────────────┘       └───────────────────────┘
        │                                   │
        │ INSERT (append-only)              │ UPSERT (merge)
        │                                   │
        └───────────────┬───────────────────┘
                        │
                        ▼
              ┌───────────────────┐
              │ GET /allocation   │
              │                   │
              │ Thompson Sampling │
              │                   │
              │ Otimiza CTR       │
              │ (clicks/imp)      │
              └─────────┬─────────┘
                        │
                        │ Salva automaticamente
                        ▼
              ┌───────────────────┐
              │allocation_history │
              │                   │
              │  experiment_id    │
              │  computed_at      │
              │  algorithm        │
              │  algorithm_version│
              │  seed             │
              │  used_fallback    │
              │  allocations (JSON)
              └───────────────────┘
```

---

## Propósito de Cada Tabela

| Tabela | Escrita | Leitura | Propósito |
|--------|---------|---------|-----------|
| **experiments** | POST /experiments | GET /allocation | Cadastro do experimento |
| **variants** | POST /experiments | GET /allocation | Cadastro das variantes |
| **raw_metrics** | POST /metrics | Auditoria/Debug | Backup append-only, rastreabilidade |
| **daily_metrics** | POST /metrics | GET /allocation | Dados limpos para cálculo do algoritmo |
| **allocation_history** | GET /allocation | SQL direto | Auditoria de decisões de alocação |

---

## Colunas de Observabilidade (raw_metrics)

| Coluna | Valores | Propósito |
|--------|---------|-----------|
| `source` | 'api', 'gam', 'cdp', 'manual' | Identifica origem dos dados |
| `batch_id` | UUID ou identificador | Rastreia qual job/ingestão enviou os dados |

---

## Colunas de Auditoria (allocation_history)

| Coluna | Propósito |
|--------|-----------|
| `seed` | Permite reproduzir exatamente o mesmo resultado |
| `algorithm_version` | Identifica qual versão do algoritmo foi usada |
| `used_fallback` | Indica se usou prior por falta de dados |
| `window_days` | Janela temporal usada no cálculo |
| `allocations` | JSON com detalhes de cada variante |

---

## Estrutura do JSON `allocations`

```json
[
  {
    "variant_id": "v1",
    "variant_name": "control",
    "is_control": true,
    "allocation_percentage": 15.2,
    "impressions": 50000,
    "clicks": 1600,
    "ctr": 0.032,
    "beta_alpha": 1601,
    "beta_beta": 48499
  },
  {
    "variant_id": "v2",
    "variant_name": "variant_a",
    "is_control": false,
    "allocation_percentage": 84.8,
    "impressions": 50000,
    "clicks": 1900,
    "ctr": 0.038,
    "beta_alpha": 1901,
    "beta_beta": 48199
  }
]
```

---

## Métricas

| Coluna | Usado para |
|--------|------------|
| `impressions` | CTR (otimização) |
| `clicks` | CTR (otimização) |
| `sessions` | Armazenado para auditoria |
| `revenue` | Armazenado para auditoria |

> **Nota:** A API otimiza apenas CTR (clicks/impressions). Sessions e revenue são armazenados mas não usados no algoritmo.
