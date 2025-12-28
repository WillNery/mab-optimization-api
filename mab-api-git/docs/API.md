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

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `name` | string | Sim | Nome único do experimento |
| `description` | string | Não | Descrição do experimento |
| `variants` | array | Sim | Lista de variantes (mínimo 2) |
| `variants[].name` | string | Sim | Nome da variante |
| `variants[].is_control` | boolean | Sim | Se é a variante de controle |

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

Registra métricas diárias de impressões e clicks por variante.

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
      "impressions": 10000,
      "clicks": 320
    },
    {
      "variant_name": "variant_a",
      "impressions": 10000,
      "clicks": 450
    },
    {
      "variant_name": "variant_b",
      "impressions": 10000,
      "clicks": 380
    }
  ],
  "source": "gam",
  "batch_id": "batch_20250115_001"
}
```

**Parâmetros:**

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `date` | string (YYYY-MM-DD) | Sim | Data das métricas |
| `metrics` | array | Sim | Lista de métricas por variante |
| `metrics[].variant_name` | string | Sim | Nome da variante |
| `metrics[].impressions` | integer | Sim | Número de impressões (≥ 0) |
| `metrics[].clicks` | integer | Sim | Número de clicks (≥ 0) |
| `source` | string | Não | Origem dos dados: `api`, `gam`, `cdp`, `manual` (default: `api`) |
| `batch_id` | string | Não | ID do batch para rastreabilidade |

**Validações:**
- `clicks` não pode ser maior que `impressions`
- `variant_name` deve existir no experimento
- `impressions` e `clicks` devem ser ≥ 0

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
4. Calcula posterior Beta para cada variante:
   - `α = 1 + clicks`
   - `β = 99 + impressions - clicks`
5. Roda 10.000 simulações Monte Carlo
6. Retorna % de vezes que cada variante "venceu"

**Response 200:**
```json
{
  "experiment_id": "5d7e7894-f937-4b43-93a7-140adf619b32",
  "experiment_name": "homepage_cta_test",
  "computed_at": "2025-01-16T00:00:00Z",
  "algorithm": "thompson_sampling",
  "window_days": 14,
  "allocations": [
    {
      "variant_name": "control",
      "is_control": true,
      "allocation_percentage": 5.2,
      "metrics": {
        "impressions": 140000,
        "clicks": 4480,
        "ctr": 0.032
      }
    },
    {
      "variant_name": "variant_a",
      "is_control": false,
      "allocation_percentage": 65.3,
      "metrics": {
        "impressions": 140000,
        "clicks": 5880,
        "ctr": 0.042
      }
    },
    {
      "variant_name": "variant_b",
      "is_control": false,
      "allocation_percentage": 29.5,
      "metrics": {
        "impressions": 140000,
        "clicks": 5320,
        "ctr": 0.038
      }
    }
  ]
}
```

**Response com Fallback:**

Quando não há dados suficientes, o campo `algorithm` indica:
```json
{
  "algorithm": "thompson_sampling (fallback: prior only)",
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
  "history": [
    {
      "date": "2025-01-15",
      "variant_name": "control",
      "is_control": true,
      "impressions": 10000,
      "clicks": 320,
      "ctr": 0.032
    },
    {
      "date": "2025-01-15",
      "variant_name": "variant_a",
      "is_control": false,
      "impressions": 10000,
      "clicks": 450,
      "ctr": 0.045
    },
    {
      "date": "2025-01-14",
      "variant_name": "control",
      "is_control": true,
      "impressions": 9500,
      "clicks": 285,
      "ctr": 0.030
    }
  ]
}
```

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

**Criar experimento:**
```bash
curl -X POST http://localhost:8000/experiments \
  -H "Content-Type: application/json" \
  -d '{
    "name": "teste_botao",
    "variants": [
      {"name": "azul", "is_control": true},
      {"name": "verde", "is_control": false}
    ]
  }'
```

**Enviar métricas:**
```bash
curl -X POST http://localhost:8000/experiments/5d7e7894-f937-4b43-93a7-140adf619b32/metrics \
  -H "Content-Type: application/json" \
  -d '{
    "date": "2025-01-15",
    "metrics": [
      {"variant_name": "azul", "impressions": 1000, "clicks": 30},
      {"variant_name": "verde", "impressions": 1000, "clicks": 45}
    ],
    "source": "gam"
  }'
```

**Obter alocação:**
```bash
curl http://localhost:8000/experiments/5d7e7894-f937-4b43-93a7-140adf619b32/allocation
```

**Obter alocação com janela customizada:**
```bash
curl "http://localhost:8000/experiments/5d7e7894-f937-4b43-93a7-140adf619b32/allocation?window_days=7"
```

### Python

```python
import requests

BASE_URL = "http://localhost:8000"

# Criar experimento
response = requests.post(f"{BASE_URL}/experiments", json={
    "name": "teste_python",
    "variants": [
        {"name": "control", "is_control": True},
        {"name": "treatment", "is_control": False}
    ]
})
experiment = response.json()
experiment_id = experiment["id"]

# Enviar métricas
requests.post(f"{BASE_URL}/experiments/{experiment_id}/metrics", json={
    "date": "2025-01-15",
    "metrics": [
        {"variant_name": "control", "impressions": 1000, "clicks": 30},
        {"variant_name": "treatment", "impressions": 1000, "clicks": 50}
    ]
})

# Obter alocação
response = requests.get(f"{BASE_URL}/experiments/{experiment_id}/allocation")
allocation = response.json()

for variant in allocation["allocations"]:
    print(f"{variant['variant_name']}: {variant['allocation_percentage']}%")
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

# Prior (Beta distribution)
PRIOR_ALPHA=1
PRIOR_BETA=99
```

---

## Rate Limits

Atualmente não há rate limiting implementado. Para produção, recomenda-se:

| Endpoint | Limite sugerido |
|----------|-----------------|
| POST /experiments | 10/minuto |
| POST /metrics | 100/minuto |
| GET /allocation | 60/minuto |

---

## Versionamento

A API atualmente não possui versionamento. Para futuras versões, será usado prefixo `/v1/`, `/v2/`, etc.
