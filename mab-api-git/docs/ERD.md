```mermaid
erDiagram
    experiments ||--o{ variants : "has"
    variants ||--o{ raw_metrics : "has"
    variants ||--o{ daily_metrics : "has"

    experiments {
        varchar(36) id PK
        varchar(255) name UK
        text description
        varchar(20) status
        timestamp created_at
        timestamp updated_at
    }

    variants {
        varchar(36) id PK
        varchar(36) experiment_id FK
        varchar(100) name
        boolean is_control
        timestamp created_at
    }

    raw_metrics {
        varchar(36) id PK
        varchar(36) variant_id FK
        date metric_date
        integer impressions
        integer clicks
        timestamp received_at
    }

    daily_metrics {
        varchar(36) id PK
        varchar(36) variant_id FK
        date metric_date
        integer impressions
        integer clicks
        timestamp created_at
        timestamp updated_at
    }
```

## Relacionamentos

| Relação | Cardinalidade | Descrição |
|---------|---------------|-----------|
| experiments → variants | 1:N | Um experimento tem N variantes |
| variants → raw_metrics | 1:N | Uma variante tem N registros de métricas brutas |
| variants → daily_metrics | 1:N | Uma variante tem N registros de métricas diárias |

## Constraints

| Tabela | Constraint | Tipo |
|--------|------------|------|
| experiments | name | UNIQUE |
| variants | (experiment_id, name) | UNIQUE |
| daily_metrics | (variant_id, metric_date) | UNIQUE |

## Propósito de cada tabela

| Tabela | Escrita | Leitura | Propósito |
|--------|---------|---------|-----------|
| experiments | POST /experiments | GET /allocation | Cadastro do experimento |
| variants | POST /experiments | GET /allocation | Cadastro das variantes |
| raw_metrics | POST /metrics | Auditoria | Backup, append-only |
| daily_metrics | POST /metrics | GET /allocation | Dados limpos para cálculo |
