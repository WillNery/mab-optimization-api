# Multi-Armed Bandit Optimization API

API para otimização de tráfego em testes A/B usando algoritmo Multi-Armed Bandit (Thompson Sampling).

## Índice

- [Visão Geral](#visão-geral)
- [Arquitetura](#arquitetura)
- [Algoritmo](#algoritmo)
- [Instalação](#instalação)
- [Configuração](#configuração)
- [Uso](#uso)
- [API Endpoints](#api-endpoints)
- [Testes](#testes)
- [Considerações para Produção](#considerações-para-produção)

## Visão Geral

Esta API recebe dados de experimentos A/B (impressões e clicks por variante), processa usando SQL, e retorna a alocação de tráfego otimizada para o dia seguinte.

### Características

- **Algoritmo**: Thompson Sampling com modelo Beta-Bernoulli
- **Banco de dados**: Snowflake
- **Multi-variante**: Suporta N variantes (não apenas A/B)
- **Janela temporal**: 14 dias por padrão
- **Documentação**: Swagger UI automático

## Arquitetura

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  GAM / CDP  │────▶│   FastAPI   │────▶│  Snowflake  │
│  (fontes)   │     │   (API)     │     │   (dados)   │
└─────────────┘     └──────┬──────┘     └─────────────┘
                          │
                          ▼
                   ┌─────────────┐
                   │  Thompson   │
                   │  Sampling   │
                   └─────────────┘
```

### Fluxo de Dados

1. **Ingestão**: Job diário envia dados agregados de GAM/CDP para a API
2. **Armazenamento**: Dados são salvos em `raw_metrics` (auditoria) e `daily_metrics` (limpo)
3. **Cálculo**: Thompson Sampling processa últimos 14 dias e retorna alocação

### Atribuição de Variantes

A atribuição de variante deve ser feita **por sessão** na camada de coleta (CDP):

```
Usuário acessa página → CDP gera session_id → Hash(session_id) % 100 → Define variante
```

Isso garante consistência durante a navegação sem depender de login.

## Algoritmo: Thompson Sampling

### O problema
Queremos alocar mais tráfego para a variante que provavelmente é melhor, 
mas sem ignorar variantes que ainda têm poucas amostras.

### A intuição
Para cada variante, mantemos uma estimativa de "quão bom" ela pode ser, 
junto com nossa incerteza sobre isso. Variantes com poucos dados têm 
incerteza alta — podem ser ótimas ou péssimas.

A cada rodada, sorteamos um valor possível de CTR para cada variante 
(respeitando a incerteza) e alocamos mais tráfego para quem "ganhou" o sorteio.

Variantes incertas às vezes ganham por sorte → recebem tráfego → coletamos 
dados → incerteza diminui. Isso balanceia exploração e explotação naturalmente.

### Implementação
- Cada variante tem uma distribuição Beta(α, β)
- α = cliques + 1
- β = impressões - cliques + 1
- Amostramos 10.000 valores de cada distribuição
- Alocação = % de vezes que cada variante teve o maior valor

### Por que Thompson Sampling e não UCB?
UCB calcula um limite superior fixo e sempre escolhe o maior. 
Thompson Sampling sorteia, então variantes "azaradas" ainda têm chance. 
Na prática, converge mais rápido para a melhor variante.

## Instalação

### Requisitos

- Python 3.11+
- Snowflake account
- Docker (opcional)

### Setup Local

```bash
# Clonar repositório
git clone <repo>
cd mab-api

# Criar ambiente virtual
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# Instalar dependências
pip install -e ".[dev]"

# Copiar configuração
cp .env.example .env
# Editar .env com suas credenciais Snowflake
```

### Setup Snowflake

```bash
# Executar scripts SQL
snowsql -f infrastructure/snowflake/01_create_schema.sql
snowsql -f infrastructure/snowflake/02_create_tables.sql
```

### Docker

```bash
docker-compose up --build
```

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
THOMPSON_SAMPLES=10000
```

## Uso

### Iniciar API

```bash
uvicorn src.main:app --reload
```

A API estará disponível em `http://localhost:8000`.

### Documentação Interativa

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## API Endpoints

### 1. Criar Experimento

```bash
curl -X POST http://localhost:8000/experiments \
  -H "Content-Type: application/json" \
  -d '{
    "name": "homepage_cta_test",
    "description": "Testing CTA button variants",
    "variants": [
      {"name": "control", "is_control": true},
      {"name": "variant_a", "is_control": false},
      {"name": "variant_b", "is_control": false}
    ]
  }'
```

### 2. Registrar Métricas

```bash
curl -X POST http://localhost:8000/experiments/{experiment_id}/metrics \
  -H "Content-Type: application/json" \
  -d '{
    "date": "2025-01-15",
    "metrics": [
      {"variant_name": "control", "impressions": 10000, "clicks": 320},
      {"variant_name": "variant_a", "impressions": 10000, "clicks": 420},
      {"variant_name": "variant_b", "impressions": 10000, "clicks": 380}
    ]
  }'
```

### 3. Obter Alocação

```bash
curl http://localhost:8000/experiments/{experiment_id}/allocation
```

**Resposta:**

```json
{
  "experiment_id": "exp_abc123",
  "experiment_name": "homepage_cta_test",
  "computed_at": "2025-01-16T00:00:00Z",
  "algorithm": "thompson_sampling",
  "window_days": 14,
  "allocations": [
    {
      "variant_name": "control",
      "is_control": true,
      "allocation_percentage": 5.2,
      "metrics": {"impressions": 140000, "clicks": 4480, "ctr": 0.032}
    },
    {
      "variant_name": "variant_a",
      "is_control": false,
      "allocation_percentage": 65.3,
      "metrics": {"impressions": 140000, "clicks": 5880, "ctr": 0.042}
    },
    {
      "variant_name": "variant_b",
      "is_control": false,
      "allocation_percentage": 29.5,
      "metrics": {"impressions": 140000, "clicks": 5320, "ctr": 0.038}
    }
  ]
}
```

### 4. Histórico de Métricas

```bash
curl http://localhost:8000/experiments/{experiment_id}/history
```

## Testes

```bash
# Rodar todos os testes
pytest -v

# Apenas unit tests
pytest tests/unit -v

# Apenas integration tests
pytest tests/integration -v

# Com cobertura
pytest --cov=src
```

## Considerações para Produção

### Contexto Activeview

Para o ambiente da Activeview com 1000+ sites e alto volume de dados:

#### 1. Ingestão de Alto Volume

```
Eventos → Kafka/Kinesis → S3 (Parquet) → Snowpipe → Snowflake
```

A implementação atual usa INSERT direto, adequado para o teste. Em produção:
- Snowpipe para micro-batches automáticos
- Parquet para compressão e performance

#### 2. Agregação

```
raw_events → DBT/Dynamic Table → daily_metrics
```

- Dynamic Tables com refresh automático
- Ou DBT rodando em schedule via Airflow

#### 3. Multi-tenancy

- Adicionar `site_id` em todas as tabelas
- Clustering key por `(site_id, experiment_id)`

#### 4. Custo Snowflake

- Warehouse com auto-suspend de 60s
- Cache Redis se alocação for consultada frequentemente

#### 5. Métricas Adicionais

A implementação otimiza **CTR** conforme especificado. A estrutura permite extensão para **receita por sessão** — bastaria adicionar campos no schema e ajustar a função objetivo.

### Flexibilidade de Ingestão

A API suporta dois cenários:

| Cenário | Fluxo |
|---------|-------|
| **A** (teste) | Job → POST /metrics → Snowflake |
| **B** (produção) | ETL Pipeline → Snowflake ← GET /allocation |

Zero mudança de código para migrar de A para B.

## Estrutura do Projeto

```
mab-api/
├── src/
│   ├── main.py              # FastAPI app
│   ├── config.py            # Settings
│   ├── models/              # Pydantic schemas
│   ├── repositories/        # Data access
│   ├── services/            # Business logic
│   ├── routers/             # API endpoints
│   └── sql/                 # SQL queries
├── infrastructure/
│   └── snowflake/           # DDL scripts
├── tests/
│   ├── unit/
│   └── integration/
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

## Licença

Projeto desenvolvido como teste técnico para Activeview.
