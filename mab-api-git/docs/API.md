# API Documentation

## Visão Geral

API REST para otimização de tráfego em testes A/B usando Multi-Armed Bandit (Thompson Sampling).

**Base URL:** `http://localhost:8000`

**Documentação Interativa:** 
- Swagger UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI JSON: `/openapi.json`

---

## Autenticação

Atualmente a API não requer autenticação. Para produção, recomenda-se implementar API Key ou OAuth2.

---

## Endpoints

### Sumário

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/health` | Verifica status da API |
| POST | `/experiments` | Cria novo experimento |
| GET | `/experiments/{id}` | Busca experimento por ID |
| POST | `/experiments/{id}/metrics` | Registra métricas diárias |
| GET | `/experiments/{id}/allocation` | Retorna alocação otimizada |
| GET | `/experiments/{id}/history` | Retorna histórico de métricas |

---

## Health Check

### `GET /health`

Verifica se a API está funcionando.

**Response 200:**
```json
{
  "status": "healthy",
  "timestamp": "2025-01-15T10:30:00Z"
}
```

---

## Experimentos

### `POST /experiments`

Cria um novo experimento com suas variantes.

**Request Body:**
```json
{
  "name": "homepage_cta_test",
  "description": "Teste de cores do botão CTA na homepage",
  "optimization_target": "rpm",
  "variants": [
    {
      "name": "control",
      "is_control": true
    },
    {
      "name": "variant_a",
      "is_control": false
    },
    {
      "name": "variant_b",
      "is_control": false
    }
  ]
}
```

**Parâmetros:**

| Campo | Tipo | Obrigatório | Default | Descrição |
|-------|------|-------------|---------|-----------|
| `name` | string | Sim | - | Nome único do experimento |
| `description` | string | Não | null | Descrição do experimento |
| `optimization_target` | string | Não | "ctr" | Métrica a otimizar: `ctr`, `rps`, `rpm` |
| `variants` | array | Sim | - | Lista de variantes (mínimo 2) |
| `variants[].name` | string | Sim | - | Nome da variante |
| `variants[].is_control` | boolean | Sim | - | Se é a variante de controle |

**Optimization Targets:**

| Target | Métrica | Fórmula | Uso |
|--------|---------|---------|-----|
| `ctr` | Click-Through Rate | clicks / impressions | Maximizar engajamento |
| `rps` | Revenue Per Session | revenue / sessions | Maximizar receita por usuário |
| `rpm` | Revenue Per Mille | (revenue / impressions) × 1000 | Maximizar receita por inventário |

**Validações:**
- Deve ter pelo menos 1 variante com `is_control: true`
- Deve ter pelo menos 2 variantes
- Nomes de variantes devem ser únicos no experimento
- Nome do experimento deve ser único

**Response 201 (Created):**
```json
{
  "id": "5d7e7894-f937-4b43-93a7-140adf619b32",
  "name": "homepage_cta_test",
  "description": "Teste de cores do botão CTA na homepage",
  "status": "active",
  "optimization_target": "rpm",
  "variants": [
    {
      "id": "194890c6-7b14-4431-8ed9-3d4dbd44262c",
      "name": "control",
      "is_control": true,
      "created_at": "2025-01-15T10:30:00Z"
    },
    {
      "id": "5c730ac2-64a1-4820-b80c-92b52b20c823",
      "name": "variant_a",
      "is_control": false,
      "created_at": "2025-01-15T10:30:00Z"
    },
    {
      "id": "8a9b0c1d-2e3f-4a5b-6c7d-8e9f0a1b2c3d",
      "name": "variant_b",
      "is_control": false,
      "created_at": "2025-01-15T10:30:00Z"
    }
  ],
  "created_at": "2025-01-15T10:30:00Z",
  "updated_at": "2025-01-15T10:30:00Z"
}
```

**Response 409 (Conflict):**
```json
{
  "detail": "Experiment with name 'homepage_cta_test' already exists"
}
```

**Response 422 (Validation Error):**
```json
{
  "detail": [
    {
      "loc": ["body", "variants"],
      "msg": "At least one variant must be marked as control",
      "type": "value_error"
    }
  ]
}
```

---

### `GET /experiments/{experiment_id}`

Busca detalhes de um experimento.

**Path Parameters:**

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `experiment_id` | string (UUID) | ID do experimento |

**Response 200:**
```json
{
  "id": "5d7e7894-f937-4b43-93a7-140adf619b32",
  "name": "homepage_cta_test",
  "description": "Teste de cores do botão CTA na homepage",
  "status": "active",
  "optimization_target": "rpm",
  "variants": [
    {
      "id": "194890c6-7b14-4431-8ed9-3d4dbd44262c",
      "name": "control",
      "is_control": true,
      "created_at": "2025-01-15T10:30:00Z"
    },
    {
      "id": "5c730ac2-64a1-4820-b80c-92b52b20c823",
      "name": "variant_a",
      "is_control": false,
      "created_at": "2025-01-15T10:30:00Z"
    }
  ],
  "created_at": "2025-01-15T10:30:00Z",
  "updated_at": "2025-01-15T10:30:00Z"
}
```

**Response 404 (Not Found):**
```json
{
  "detail": "Experiment not found"
}
```

---

## Métricas

### `POST /experiments/{experiment_id}/metrics`

Registra métricas diárias de sessões, impressões, clicks e receita por variante.

**Path Parameters:**

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `experiment_id` | string (UUID) | ID do experimento |

**Request Body:**
```json
{
  "date": "2025-01-15",
  "metrics": [
    {
      "variant_name": "control",
      "sessions": 5000,
      "impressions": 10000,
      "clicks": 320,
      "revenue": 150.50
    },
    {
      "variant_name": "variant_a",
      "sessions": 5200,
      "impressions": 10000,
      "clicks": 420,
      "revenue": 185.75
    },
    {
      "variant_name": "variant_b",
      "sessions": 4800,
      "impressions": 10000,
      "clicks": 380,
      "revenue": 165.25
    }
  ],
  "source": "gam",
  "batch_id": "batch_20250115_001"
}
```

**Parâmetros:**

| Campo | Tipo | Obrigatório | Default | Descrição |
|-------|------|-------------|---------|-----------|
| `date` | string (YYYY-MM-DD) | Sim | - | Data das métricas |
| `metrics` | array | Sim | - | Lista de métricas por variante |
| `metrics[].variant_name` | string | Sim | - | Nome da variante |
| `metrics[].sessions` | integer | Não | 0 | Número de sessões únicas |
| `metrics[].impressions` | integer | Sim | - | Número de impressões (≥ 0) |
| `metrics[].clicks` | integer | Sim | - | Número de clicks (≥ 0) |
| `metrics[].revenue` | decimal | Não | 0 | Receita em USD |
| `source` | string | Não | "api" | Origem: `api`, `gam`, `cdp`, `manual` |
| `batch_id` | string | Não | null | ID do batch para rastreabilidade |

**Validações:**
- `clicks` não pode ser maior que `impressions`
- `variant_name` deve existir no experimento
- `impressions` e `clicks` devem ser ≥ 0
- `revenue` deve ser ≥ 0

**Response 201 (Created):**
```json
{
  "message": "Metrics recorded successfully",
  "date": "2025-01-15",
  "variants_updated": 3,
  "batch_id": "batch_20250115_001"
}
```

**Response 404 (Not Found):**
```json
{
  "detail": "Experiment 'abc123' not found"
}
```

**Response 422 (Validation Error):**
```json
{
  "detail": [
    {
      "loc": ["body", "metrics", 0],
      "msg": "Clicks (500) cannot exceed impressions (100)",
      "type": "value_error"
    }
  ]
}
```

---

## Alocação

### `GET /experiments/{experiment_id}/allocation`

Retorna a alocação de tráfego otimizada usando Thompson Sampling.

**Path Parameters:**

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `experiment_id` | string (UUID) | ID do experimento |

**Query Parameters:**

| Parâmetro | Tipo | Default | Descrição |
|-----------|------|---------|-----------|
| `window_days` | integer | 14 | Janela de análise em dias |

**Algoritmo:**

1. Busca métricas dos últimos `window_days` dias
2. Se alguma variante tem < 200 impressões, expande para 30 dias
3. Se ainda insuficiente, usa fallback (prior only)
4. Calcula alocação baseado no `optimization_target` do experimento:
   - **CTR**: Beta(α₀ + clicks, β₀ + impressions - clicks)
   - **RPS/RPM**: Normal distribution com média e variância empíricas
5. Roda 10.000 simulações Monte Carlo
6. Retorna % de vezes que cada variante "venceu"

**Response 200:**
```json
{
  "experiment_id": "5d7e7894-f937-4b43-93a7-140adf619b32",
  "experiment_name": "homepage_cta_test",
  "computed_at": "2025-01-16T00:00:00Z",
  "algorithm": "thompson_sampling (target: rpm)",
  "optimization_target": "rpm",
  "window_days": 14,
  "allocations": [
    {
      "variant_name": "control",
      "is_control": true,
      "allocation_percentage": 15.2,
      "metrics": {
        "sessions": 70000,
        "impressions": 140000,
        "clicks": 4480,
        "revenue": 2100.50,
        "ctr": 0.032,
        "ctr_ci": {
          "lower": 0.0311,
          "upper": 0.0329
        },
        "rps": 0.030,
        "rpm": 15.00
      }
    },
    {
      "variant_name": "variant_a",
      "is_control": false,
      "allocation_percentage": 84.8,
      "metrics": {
        "sessions": 72000,
        "impressions": 140000,
        "clicks": 5880,
        "revenue": 2750.25,
        "ctr": 0.042,
        "ctr_ci": {
          "lower": 0.0410,
          "upper": 0.0430
        },
        "rps": 0.038,
        "rpm": 19.64
      }
    }
  ]
}
```

**Response com Fallback:**

Quando não há dados suficientes:
```json
{
  "algorithm": "thompson_sampling (fallback: prior only, target: rpm)",
  "window_days": 30,
  ...
}
```

**Response 404 (Not Found):**
```json
{
  "detail": "Experiment not found"
}
```

---

### `GET /experiments/{experiment_id}/history`

Retorna histórico de métricas diárias.

**Path Parameters:**

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `experiment_id` | string (UUID) | ID do experimento |

**Response 200:**
```json
{
  "experiment_id": "5d7e7894-f937-4b43-93a7-140adf619b32",
  "experiment_name": "homepage_cta_test",
  "history": [
    {
      "metric_date": "2025-01-15",
      "variant_id": "194890c6-7b14-4431-8ed9-3d4dbd44262c",
      "variant_name": "control",
      "is_control": true,
      "sessions": 5000,
      "impressions": 10000,
      "clicks": 320,
      "revenue": 150.50,
      "ctr": 0.032,
      "ctr_ci_lower": 0.0287,
      "ctr_ci_upper": 0.0356,
      "rps": 0.0301,
      "rpm": 15.05
    },
    {
      "metric_date": "2025-01-15",
      "variant_id": "5c730ac2-64a1-4820-b80c-92b52b20c823",
      "variant_name": "variant_a",
      "is_control": false,
      "sessions": 5200,
      "impressions": 10000,
      "clicks": 420,
      "revenue": 185.75,
      "ctr": 0.042,
      "ctr_ci_lower": 0.0383,
      "ctr_ci_upper": 0.0460,
      "rps": 0.0357,
      "rpm": 18.575
    }
  ]
}
```

---

## Rate Limiting

A API possui rate limiting para proteger contra abuso e garantir disponibilidade.

### Limites por Endpoint

| Endpoint | Limite | Uso |
|----------|--------|-----|
| POST /experiments | 10/min | Criação de experimentos |
| POST /metrics | 100/min | Ingestão de métricas |
| GET /allocation | 300/min | Consulta de alocação (job diário) |
| GET /history | 60/min | Consulta de histórico |
| GET /experiments/{id} | 120/min | Consulta de experimento |
| Default | 100/min | Outros endpoints |

### Headers de Resposta

Toda resposta inclui headers de rate limit:

```
X-RateLimit-Limit: 300        # Limite máximo na janela
X-RateLimit-Remaining: 299    # Requisições restantes
X-RateLimit-Reset: 60         # Segundos até reset da janela
```

### Response 429 (Rate Limit Exceeded)

```json
{
  "detail": {
    "error": "Rate limit exceeded",
    "limit": 300,
    "window_seconds": 60,
    "retry_after": 45
  }
}
```

**Headers adicionais:**
```
Retry-After: 45
```

---

## Logging Estruturado

A API usa logging estruturado em formato JSON para observabilidade.

### Formato dos Logs

```json
{
  "timestamp": "2025-01-15T10:30:00.123Z",
  "level": "INFO",
  "logger": "mab_api",
  "message": "GET /experiments/abc/allocation 200",
  "type": "http_request",
  "method": "GET",
  "path": "/experiments/abc/allocation",
  "status_code": 200,
  "duration_ms": 145.32,
  "client_ip": "192.168.1.1",
  "request_id": "req-12345"
}
```

### Tipos de Log

| Type | Descrição | Campos extras |
|------|-----------|---------------|
| `http_request` | Requisições HTTP | method, path, status_code, duration_ms, client_ip |
| `db_query` | Queries ao Snowflake | query_name, duration_ms, rows_affected |
| `algorithm` | Execução do Thompson Sampling | experiment_id, n_samples, num_variants |
| `error` | Erros e exceções | error_type, message |
| `rate_limit` | Rate limit excedido | key, endpoint, limit |
| `startup` | Inicialização da API | host, port, config |
| `shutdown` | Encerramento da API | - |

### Exemplo de Log de Algoritmo

```json
{
  "timestamp": "2025-01-15T10:30:00.456Z",
  "level": "INFO",
  "type": "algorithm",
  "algorithm": "thompson_sampling",
  "experiment_id": "exp_123",
  "duration_ms": 150.0,
  "n_samples": 10000,
  "num_variants": 3,
  "total_impressions": 450000
}
```

### Integração com Observabilidade

Os logs em JSON são compatíveis com:
- **Datadog**: Log pipeline automático
- **CloudWatch**: Logs Insights queries
- **ELK Stack**: Elasticsearch indexing
- **Splunk**: JSON source type

---

## Códigos de Status

| Código | Significado | Quando ocorre |
|--------|-------------|---------------|
| 200 | OK | Requisição bem sucedida (GET) |
| 201 | Created | Recurso criado com sucesso (POST) |
| 400 | Bad Request | Requisição malformada |
| 404 | Not Found | Experimento ou variante não encontrado |
| 409 | Conflict | Nome de experimento já existe |
| 422 | Unprocessable Entity | Erro de validação |
| 429 | Too Many Requests | Rate limit excedido |
| 500 | Internal Server Error | Erro interno (ex: banco de dados) |

---

## Tipos de Erro

### Erro de Validação (422)
```json
{
  "detail": [
    {
      "loc": ["body", "campo", 0],
      "msg": "Mensagem de erro",
      "type": "tipo_do_erro"
    }
  ]
}
```

### Erro de Negócio (404, 409)
```json
{
  "detail": "Mensagem descritiva do erro"
}
```

### Erro de Rate Limit (429)
```json
{
  "detail": {
    "error": "Rate limit exceeded",
    "limit": 100,
    "window_seconds": 60,
    "retry_after": 30
  }
}
```

### Erro de Banco de Dados (500)
```json
{
  "detail": "Internal server error",
  "type": "DatabaseError"
}
```

---

## Exemplos de Uso

### cURL

**Criar experimento otimizando RPM:**
```bash
curl -X POST http://localhost:8000/experiments \
  -H "Content-Type: application/json" \
  -d '{
    "name": "teste_monetizacao",
    "optimization_target": "rpm",
    "variants": [
      {"name": "layout_atual", "is_control": true},
      {"name": "layout_novo", "is_control": false}
    ]
  }'
```

**Enviar métricas com receita:**
```bash
curl -X POST http://localhost:8000/experiments/5d7e7894-f937-4b43-93a7-140adf619b32/metrics \
  -H "Content-Type: application/json" \
  -d '{
    "date": "2025-01-15",
    "metrics": [
      {
        "variant_name": "layout_atual",
        "sessions": 5000,
        "impressions": 10000,
        "clicks": 320,
        "revenue": 150.50
      },
      {
        "variant_name": "layout_novo",
        "sessions": 5200,
        "impressions": 10000,
        "clicks": 380,
        "revenue": 195.75
      }
    ],
    "source": "gam"
  }'
```

**Obter alocação:**
```bash
curl http://localhost:8000/experiments/5d7e7894-f937-4b43-93a7-140adf619b32/allocation
```

**Verificar headers de rate limit:**
```bash
curl -i http://localhost:8000/experiments/5d7e7894-f937-4b43-93a7-140adf619b32/allocation
```

### Python

```python
import requests

BASE_URL = "http://localhost:8000"

# Criar experimento otimizando receita por sessão
response = requests.post(f"{BASE_URL}/experiments", json={
    "name": "teste_rps",
    "optimization_target": "rps",
    "variants": [
        {"name": "control", "is_control": True},
        {"name": "treatment", "is_control": False}
    ]
})
experiment = response.json()
experiment_id = experiment["id"]

# Verificar rate limit headers
print(f"Rate Limit: {response.headers.get('X-RateLimit-Limit')}")
print(f"Remaining: {response.headers.get('X-RateLimit-Remaining')}")

# Enviar métricas com sessões e receita
requests.post(f"{BASE_URL}/experiments/{experiment_id}/metrics", json={
    "date": "2025-01-15",
    "metrics": [
        {
            "variant_name": "control",
            "sessions": 5000,
            "impressions": 10000,
            "clicks": 300,
            "revenue": 125.00
        },
        {
            "variant_name": "treatment",
            "sessions": 5100,
            "impressions": 10000,
            "clicks": 320,
            "revenue": 175.50
        }
    ]
})

# Obter alocação
response = requests.get(f"{BASE_URL}/experiments/{experiment_id}/allocation")
allocation = response.json()

print(f"Otimizando: {allocation['optimization_target']}")
for variant in allocation["allocations"]:
    print(f"{variant['variant_name']}: {variant['allocation_percentage']}%")
    print(f"  RPM: ${variant['metrics']['rpm']:.2f}")
    print(f"  RPS: ${variant['metrics']['rps']:.4f}")
```

---

## Configuração

### Variáveis de Ambiente

```env
# Snowflake
SNOWFLAKE_ACCOUNT=xxx.us-east-1
SNOWFLAKE_USER=mab_user
SNOWFLAKE_PASSWORD=xxx
SNOWFLAKE_WAREHOUSE=compute_wh
SNOWFLAKE_DATABASE=activeview_mab
SNOWFLAKE_SCHEMA=experiments

# API
API_HOST=0.0.0.0
API_PORT=8000

# Algoritmo
DEFAULT_WINDOW_DAYS=14
MAX_WINDOW_DAYS=30
MIN_IMPRESSIONS=200
THOMPSON_SAMPLES=10000

# Prior (Beta distribution para CTR)
PRIOR_ALPHA=1
PRIOR_BETA=99

# Logging
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_DEFAULT_MAX=100
RATE_LIMIT_DEFAULT_WINDOW=60
```

---

## Métricas Calculadas

| Métrica | Fórmula | Descrição |
|---------|---------|-----------|
| CTR | clicks ÷ impressions | Taxa de cliques |
| CTR CI 95% | Wilson Score Interval | Intervalo de confiança do CTR |
| RPS | revenue ÷ sessions | Receita por sessão |
| RPM | (revenue ÷ impressions) × 1000 | Receita por mil impressões |

### Intervalo de Confiança (Wilson Score)

O intervalo de confiança do CTR é calculado usando o método Wilson Score, mais preciso que Wald para proporções:

```
z = 1.96 (95% confiança)

lower = (p + z²/2n - z × √(p(1-p)/n + z²/4n²)) / (1 + z²/n)
upper = (p + z²/2n + z × √(p(1-p)/n + z²/4n²)) / (1 + z²/n)

onde:
  p = CTR observado (clicks/impressions)
  n = número de impressões
```

---

## Versionamento

A API atualmente não possui versionamento. Para futuras versões, será usado prefixo `/v1/`, `/v2/`, etc.
