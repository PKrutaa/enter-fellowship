# 🚀 Sistema de Extração de Dados de PDFs

Sistema de extração estruturada de dados de documentos PDF com alta acurácia, baixa latência e custo otimizado. Production-ready.

## 📋 Tabela de Conteúdo

- [Início Rápido com Docker](#-início-rápido-com-docker)
- [Processamento em Batch (Sem UI)](#-processamento-em-batch-sem-ui)
- [API REST](#-api-rest)
- [Arquitetura](#-arquitetura)
- [Performance](#-performance)

---

## 🐳 Início Rápido com Docker

### Pré-requisitos
- Docker e Docker Compose instalados
- Chave da API OpenAI

### Passo a Passo

**1. Configure a API Key**
```bash
echo "OPENAI_API_KEY=sua-chave-aqui" > .env
```

**2. Inicie os containers**
```bash
docker compose up -d
```

**3. Verifique se está funcionando**
```bash
# Ver logs
docker compose logs -f

# Testar health check
curl http://localhost:8000/health
```

**4. Acesse a API**
- **API**: http://localhost:8000
- **Documentação**: http://localhost:8000/docs
- **Health**: http://localhost:8000/health
- **Stats**: http://localhost:8000/stats

### Comandos Docker Úteis

```bash
# Parar containers
docker compose down

# Rebuild após mudanças
docker compose up -d --build

# Ver logs em tempo real
docker compose logs -f api

# Entrar no container
docker compose exec api bash

# Ver uso de recursos
docker stats

# Limpar tudo (incluindo volumes)
docker compose down -v
```

---

## 📦 Processamento em Batch (Sem UI)

### Opção 1: Script CLI (Recomendado)

Para processamento offline em lote de um diretório:

**Executar o script:**
```bash
# Dentro do container Docker
docker compose exec api python src/batch_extract.py \
  --pdf-dir ai-fellowship-data/files \
  --dataset-path ai-fellowship-data/dataset.json \
  --output-dir output

# Ou localmente (se tiver Python configurado)
python src/batch_extract.py \
  --pdf-dir ai-fellowship-data/files \
  --dataset-path ai-fellowship-data/dataset.json \
  --output-dir output

# Ou utilize uv (recomendado)
uv run src/batch_extract.py \
  --pdf-dir ai-fellowship-data/files \
  --dataset-path ai-fellowship-data/dataset.json \
  --output-dir output
```

**Estrutura esperada do dataset.json:**
```json
[
  {
    "pdf_path": "oab_1.pdf",
    "label": "carteira_oab",
    "extraction_schema": {
      "nome": "Nome completo",
      "inscricao": "Número de inscrição OAB"
    }
  },
  {
    "pdf_path": "tela_sistema_1.pdf",
    "label": "tela_sistema",
    "extraction_schema": {
      "sistema": "Nome do sistema",
      "valor_parcela": "Valor da parcela"
    }
  }
]
```

**Saída:**
- Cria arquivo `output/consolidated_results.json` com todos os resultados
- Cria arquivos individuais em `output/` para cada PDF processado
- Cada resultado inclui: dados extraídos, método usado (cache/template/llm), metadata do pipeline

**Exemplo de saída (`consolidated_results.json`):**
```json
{
  "total_processed": 2,
  "total_success": 2,
  "total_failed": 0,
  "processing_time_seconds": 7.84,
  "results": [
    {
      "pdf_path": "oab_1.pdf",
      "label": "carteira_oab",
      "success": true,
      "data": {
        "nome": "João Silva",
        "inscricao": "123456"
      },
      "metadata": {
        "method": "llm",
        "pipeline_info": {
          "method": "llm",
          "time": 3.62
        }
      }
    },
    {
      "pdf_path": "oab_2.pdf",
      "label": "carteira_oab",
      "success": true,
      "data": {
        "nome": "Maria Santos",
        "inscricao": "789012"
      },
      "metadata": {
        "method": "template",
        "pipeline_info": {
          "method": "template",
          "similarity": 92.5,
          "time": 0.51
        }
      }
    }
  ]
}
```


### Opção 2: Via API com Streaming

A API suporta **processamento progressivo com Server-Sent Events (SSE)**:

**Características:**
- ✅ **Múltiplos PDFs, múltiplas labels**: Cada arquivo pode ter label e schema diferentes
- ✅ **Processamento paralelo por label**: Labels diferentes processam simultaneamente
- ✅ **Resultados progressivos**: Recebe cada PDF assim que é processado (não espera o batch completo)
- ✅ **Template learning**: Documentos do mesmo label processam sequencialmente para aprendizado

**Exemplo Python:**

```python
import requests
import json

# Preparar arquivos e metadados
files_data = [
    {
        "file": ("oab_1.pdf", open("oab_1.pdf", "rb"), "application/pdf"),
        "label": "carteira_oab",
        "schema": {"nome": "Nome completo", "inscricao": "Número OAB"}
    },
    {
        "file": ("tela_1.pdf", open("tela_1.pdf", "rb"), "application/pdf"),
        "label": "tela_sistema",
        "schema": {"sistema": "Nome do sistema", "valor": "Valor total"}
    },
    {
        "file": ("oab_2.pdf", open("oab_2.pdf", "rb"), "application/pdf"),
        "label": "carteira_oab",
        "schema": {"nome": "Nome completo", "inscricao": "Número OAB"}
    }
]

# Criar FormData
form_data = []
for item in files_data:
    form_data.append(("files", item["file"]))
    
# Adicionar labels e schemas na mesma ordem
labels = [item["label"] for item in files_data]
schemas = [json.dumps(item["schema"]) for item in files_data]

data = {
    "labels": labels,
    "schemas": schemas
}

# Fazer request com streaming
response = requests.post(
    "http://localhost:8000/extract-batch",
    files=[("files", f[1]) for f in form_data],
    data={
        "labels": labels,
        "schemas": schemas
    },
    stream=True  # 🔥 Importante: habilita streaming
)

# Processar resultados progressivamente
for line in response.iter_lines(decode_unicode=True):
    if not line:
        continue
        
    if line.startswith("event:"):
        event_type = line.split(":", 1)[1].strip()
    elif line.startswith("data:"):
        data = json.loads(line.split(":", 1)[1].strip())
        
        if event_type == "result":
            # Resultado individual (recebido assim que processa)
            filename = data["filename"]
            success = data["success"]
            method = data["metadata"].get("method", "unknown")
            time = data["metadata"].get("time", 0)
            
            print(f"✓ {filename}: {method} ({time:.2f}s)")
            
            if success:
                print(f"  Dados: {data['data']}")
            else:
                print(f"  Erro: {data['error']}")
        
        elif event_type == "complete":
            # Estatísticas finais
            print(f"\n📊 Processamento completo:")
            print(f"  Total: {data['total_files']}")
            print(f"  Sucesso: {data['successful']}")
            print(f"  Falhas: {data['failed']}")
            print(f"  Tempo: {data['processing_time_seconds']:.2f}s")
            print(f"  Labels: {', '.join(data['metadata']['labels_processed'])}")
```

**Como o streaming funciona:**
```
Envio: 2 PDFs "carteira_oab" + 3 PDFs "tela_sistema"

Processamento:
├─ Thread 1: carteira_oab (processa sequencialmente)
│   ├─ oab_1.pdf → 📤 SSE evento 1
│   └─ oab_2.pdf → 📤 SSE evento 2
│
└─ Thread 2: tela_sistema (processa sequencialmente)
    ├─ tela_1.pdf → 📤 SSE evento 3
    ├─ tela_2.pdf → 📤 SSE evento 4
    └─ tela_3.pdf → 📤 SSE evento 5

📤 Evento final: complete

Resultado: Frontend recebe cada arquivo IMEDIATAMENTE após processar!
```
---

## 🌐 API REST

### Endpoints Disponíveis

#### POST `/extract`
Extrai dados de um PDF individual.

**Request:**
```bash
curl -X POST "http://localhost:8000/extract" \
  -F "file=@documento.pdf" \
  -F "label=carteira_oab" \
  -F 'extraction_schema={"nome":"Nome completo","inscricao":"Número OAB"}'
```

**Response:**
```json
{
  "success": true,
  "data": {
    "nome": "João Silva",
    "inscricao": "123456"
  },
  "metadata": {
    "method": "llm",
    "time_seconds": 2.341,
    "pipeline_info": {...}
  }
}
```

#### POST `/extract-batch`
Extrai dados de múltiplos PDFs com streaming progressivo (SSE).

Ver exemplo completo em [Processamento em Batch](#-processamento-em-batch-sem-ui).

#### GET `/health`
Verifica saúde da API.

```bash
curl http://localhost:8000/health
```

#### GET `/stats`
Estatísticas detalhadas do sistema.

```bash
curl http://localhost:8000/stats
```

**Response:**
```json
{
  "cache": {
    "l1_size": 42,
    "l1_hits": 158,
    "l1_misses": 23,
    "l2_hits": 12
  },
  "templates": {
    "carteira_oab": 5,
    "tela_sistema": 3
  },
  "extraction_counts": {
    "llm_calls": 31,
    "template_hits": 142,
    "cache_hits": 170
  }
}
```

---

## 🏗️ Arquitetura

### Pipeline de Extração

```
┌─────────────┐
│   PDF Input │
└──────┬──────┘
       │
       ▼
┌──────────────┐
│ 1. Cache L1  │ ─── Hit? ──> Retorna (0.1ms)
│    (Memory)  │
└──────┬───────┘
       │ Miss
       ▼
┌──────────────┐
│ 2. Cache L2  │ ─── Hit? ──> Retorna (1-2ms)
│    (Disk)    │
└──────┬───────┘
       │ Miss
       ▼
┌──────────────┐
│ 3. Template  │
│    Matching  │
└──────┬───────┘
       │
       ▼
  ┌────────────┐
  │ Similaridade│
  │   >= 90%?  │
  └─────┬──────┘
        │
   ┌────┴────┐
   │ SIM     │ NÃO
   ▼         ▼
┌────────┐ ┌────────┐
│Template│ │  LLM   │
│ (0.5s) │ │(2-5s)  │
└───┬────┘ └───┬────┘
    │          │
    └────┬─────┘
         ▼
   ┌──────────┐
   │ 4. Learn │
   │ Template │
   └─────┬────┘
         │
         ▼
   ┌──────────┐
   │ 5. Cache │
   └─────┬────┘
         │
         ▼
    ┌────────┐
    │Response│
    └────────┘
```

### Componentes

1. **LLM Extractor** (`src/extraction/llm.py`)
   - Modelo: `gpt-5-mini` com structured outputs
   - Parser: `unstructured` com coordenadas espaciais
   - Validação: Formatos brasileiros (CPF, CEP, telefone, etc.)
   - Timeout: 120s por documento

2. **Cache Manager** (`src/cache/`)
   - L1 (Memory): LRU cache, ~0.1ms
   - L2 (Disk): DiskCache persistente, ~1-2ms
   - Hit rate: 50-90% após warm-up

3. **Template Learning** (`src/template/`)
   - Aprende padrões automaticamente de extrações LLM
   - Similaridade >= 90% para ativar template
   - Extração ~10x mais rápida que LLM

4. **FastAPI Backend** (`src/main.py`)
   - Documentação automática (Swagger UI)
   - Health checks e monitoramento
   - Batch processing com streaming

---

## 📊 Performance

### Benchmarks

| Cenário | Tempo | Método |
|---------|-------|--------|
| **Primeira extração** | ~3.5s | LLM completo |
| **Cache hit (L1)** | <0.001s | Cache memória |
| **Cache hit (L2)** | ~0.001s | Cache disco |
| **Template match (>90%)** | ~0.5s | Template puro |
| **Documento novo** | ~3.5s | LLM completo |

### Evolução com Template Learning

```
Request 1 (doc_1.pdf): LLM    → 3.62s (aprende)
Request 2 (doc_1.pdf): Cache  → 0.2ms (18.000x faster ⚡)
Request 3 (doc_2.pdf): LLM    → 3.41s (aprende)
Request 4 (doc_3.pdf): Template → 0.51s (7x faster ⚡)
Request 5 (doc_2.pdf): Cache  → 0.2ms (cache hit)
```

**💡 Sistema aprende e fica progressivamente mais rápido!**

### Acurácia

- **Média geral**: 89-97%
- **Validação de formatos **: CEP, CPF, telefone, valores monetários
- **Structured outputs**: Garante JSON válido sempre

---

## 🎯 Tecnologias

- **LLM**: OpenAI GPT-5-mini com structured outputs
- **PDF Processing**: unstructured (coordenadas espaciais)
- **Cache**: diskcache + LRU in-memory
- **Template DB**: SQLite
- **API**: FastAPI + uvicorn
- **Container**: Docker + Docker Compose

---

## 🔧 Variáveis de Ambiente

Crie um arquivo `.env` na raiz:

```bash
# Obrigatório
OPENAI_API_KEY=sk-proj-...

# Opcionais
PORT=8000
HOST=0.0.0.0
LOG_LEVEL=info
```

---

## 📁 Estrutura do Projeto

```
enter-fellowship/
├── src/
│   ├── main.py              # API FastAPI
│   ├── pipeline.py          # Pipeline de extração
│   ├── extraction/
│   │   └── llm.py          # LLM + unstructured
│   ├── cache/
│   │   ├── cache_manager.py
│   │   └── cache_key.py
│   ├── template/
│   │   ├── template_manager.py
│   │   ├── pattern_learner.py
│   │   ├── field_extractor.py
│   │   ├── template_matcher.py
│   │   └── database.py
│   ├── batch_extract.py     # Script CLI para batch
│   └── storage/
│       ├── cache_data/      # Cache L2
│       └── templates.db     # Templates aprendidos
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env
```

---

## 🐛 Troubleshooting

### Docker

**Porta 8000 em uso:**
```bash
# Opção 1: Parar processo
lsof -ti:8000 | xargs kill -9

# Opção 2: Mudar porta no docker-compose.yml
ports:
  - "8001:8000"
```

**Mudanças não refletem:**
```bash
docker compose down
docker compose up -d --build
```

**Erro de permissão:**
```bash
docker compose down -v
docker compose up -d
```

### API

**Erro 500 ao extrair:**
- Verifique `OPENAI_API_KEY` no `.env`
- Veja logs: `docker compose logs -f api`

**Batch muito lento:**
- Normal na primeira vez (aprende templates)
- Documentos subsequentes serão mais rápidos
- Use `/stats` para ver cache hits

**Acurácia baixa:**
- Verifique se schema está bem definido
- Confira qualidade do PDF (OCR pode falhar em PDFs ruins)
- Veja logs de validação para campos específicos

---

## 🏆 Diferenciais

1. **🎯 Template Learning Automático**: Aprende com cada extração, fica 7-10x mais rápido
2. **⚡ Streaming Progressivo (SSE)**: Batch com resultados em tempo real
3. **💾 Cache Multi-Level**: <1ms para documentos repetidos
4. **📍 Validação BR**: Formatos brasileiros (CPF, CEP, telefone)
5. **🚀 Production-Ready**: Docker, health checks, monitoramento
6. **🧠 Structured Outputs**: JSON válido garantido

---

**Desenvolvido para Enter AI Fellowship** | 2025
