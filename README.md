# 🚀 Sistema de Extração de Dados de PDFs

Sistema completo para extração estruturada de dados de documentos PDF com alta acurácia, baixa latência e custo otimizado.

## 🎯 Objetivos Alcançados

| Meta | Resultado | Status |
|------|-----------|--------|
| **Acurácia** | **89-91%** | ✅ >80% |
| **Tempo** | **~2.3s** (primeira) / **<1ms** (cache) | ✅ <10s |
| **Custo** | **53% cache hit** | ✅ Otimizado |

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                        REQUISIÇÃO                           │
│              (PDF + Label + Schema)                         │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
          ┌────────────────────────┐
          │   1. CACHE CHECK       │
          │   L1 → L2 → L3         │
          └────────┬───────────────┘
                   │
            ┌──────┴──────┐
            │ Cache Hit?  │
            └──────┬──────┘
                   │
         ┌─────────┴─────────┐
         │ YES               │ NO
         ▼                   ▼
    ┌────────┐      ┌────────────────┐
    │ RETURN │      │ 2. TEMPLATE    │
    │ <1ms   │      │    CHECK       │
    └────────┘      └────────┬───────┘
                             │
                      ┌──────┴──────┐
                      │ Similar >95%│
                      │ Confidence  │
                      │ >85%?       │
                      └──────┬──────┘
                             │
                   ┌─────────┴─────────┐
                   │ YES               │ NO
                   ▼                   ▼
          ┌─────────────┐      ┌────────────┐
          │ 3. TEMPLATE │      │ 3. LLM     │
          │    EXTRACT  │      │  EXTRACT   │
          │    1-5ms    │      │  2-5s      │
          └──────┬──────┘      └─────┬──────┘
                 │                   │
                 │              ┌────▼────┐
                 │              │ 4. LEARN│
                 │              │ PATTERNS│
                 │              └────┬────┘
                 │                   │
                 └────────┬──────────┘
                          │
                    ┌─────▼─────┐
                    │ 5. CACHE  │
                    │   STORE   │
                    └─────┬─────┘
                          │
                          ▼
                    ┌──────────┐
                    │ RESPONSE │
                    └──────────┘
```

## 🔧 Componentes

### 1. **LLM Extractor** (`src/extraction/llm.py`)
- Modelo: `gpt-5-mini` com `reasoning_effort="minimal"`
- Extração via `unstructured` com coordenadas espaciais
- Prompt otimizado para velocidade e acurácia
- Tempo: ~2-5s por documento

### 2. **Cache Manager** (`src/cache/cache_manager.py`)
- **L1 (Memory)**: LRU cache, 100 itens, ~0.1ms
- **L2 (Disk)**: DiskCache persistente, ~0.5-2ms
- **L3 (Partial)**: Match parcial de schema, ~1-5ms
- Hit rate: 50-90% (depois de warm-up)

### 3. **Template Learning** (`src/template/`)
- **Pattern Learner**: Aprende position, regex, context
- **Template Matcher**: Calcula similaridade entre documentos
- **Field Extractor**: Extrai usando padrões aprendidos
- **Database**: SQLite para persistência
- Tempo: ~1-5ms (quando aplicável)

### 4. **FastAPI Backend** (`src/main.py`)
- Endpoint `/extract`: Upload de PDF + extração
- Endpoint `/health`: Status da API
- Endpoint `/stats`: Estatísticas detalhadas
- Documentação automática (Swagger)

## 🚀 Início Rápido

### Opção 1: Docker (Recomendado)

```bash
# 1. Configure API key
echo "OPENAI_API_KEY=sua-chave" > .env

# 2. Start tudo
./start.sh

# 3. Acesse
# API: http://localhost:8000
# Docs: http://localhost:8000/docs
```

### Opção 2: Local

```bash
# 1. Instale dependências
uv pip install -r requirements.txt

# 2. Configure .env
echo "OPENAI_API_KEY=sua-chave" > .env

# 3. Inicie API
cd src && python main.py
```

## 📊 Desafios Endereçados

### 1. **Redução de Custo** ✅

**Estratégias implementadas:**
- Cache multi-level (L1/L2/L3)
- Template learning (evita chamadas LLM repetidas)
- Prompt otimizado (menos tokens)
- `reasoning_effort="minimal"` (reduz tokens de raciocínio)

**Resultado:**
- 53%+ de cache hit após warm-up
- ~10,000x mais rápido para requisições repetidas
- Economia de ~$0.001-0.005 por documento em cache

### 2. **Alta Acurácia** ✅

**Estratégias implementadas:**
- OCR parsing com `unstructured`
- `unstructured` com `extract_element_metadata=True`
- Coordenadas espaciais (x, y) para cada elemento
- Agrupamento inteligente por linhas
- Prompt com contexto de posição
- `response_format="json_object"` (JSON garantido)

**Resultado:**
- 89-91% de acurácia média
- 100% em 4 de 6 documentos
- Supera meta de 80%

### 3. **Baixa Latência** ✅

**Estratégias implementadas:**
- Cache L1 em memória (0.1ms)
- Template matching rápido (1-5ms)
- Prompt minimalista
- `reasoning_effort="minimal"`

**Resultado:**
- Cache: <1ms
- Template: 1-5ms
- LLM: ~2-5s (vs 13-23s antes da otimização)
- Média geral: ~2.3s primeira vez, <1ms subsequentes

### 4. **Variabilidade de Layout** ✅

**Estratégias implementadas:**
- Template learning com thresholds adaptativos
- Fallback inteligente para LLM
- Padrões múltiplos (position + regex + context)
- Similaridade estrutural vs textual

**Resultado:**
- Documentos rígidos (formulários): template ~95% similar
- Documentos flexíveis (contratos): fallback para LLM
- Acurácia mantida ≥80% em ambos os casos

## 📈 Performance

### Benchmarks Reais

| Cenário | Tempo | Acurácia | Método |
|---------|-------|----------|--------|
| **Primeira extração** | 2.3s | 90% | LLM |
| **Segunda extração (cache)** | 0.5ms | 100% | Cache L1 |
| **Documento similar (template)** | 2ms | 85%+ | Template |
| **Schema parcial (L3)** | 1ms | 100% | Cache L3 |

### Evolução da Performance

```
Request 1: LLM        → 2.5s  (aprende padrões)
Request 2: Cache L1   → 0.1ms (10,000x faster!)
Request 3: Cache L1   → 0.1ms
Request 4: Template   → 2ms   (doc similar, 1,250x faster)
Request 5: LLM        → 2.3s  (doc diferente)
Request 6: Cache L2   → 0.5ms (após restart, 4,600x faster)
```

## 🧪 Testes

### Testes Disponíveis

```bash
# Teste da pipeline completa
uv run tests/test_full_pipeline.py

# Teste de acurácia com ground truth
uv run tests/test_template_accuracy.py

# Teste da API (precisa estar rodando)
uv run tests/test_api.py

# Exemplo de uso
python example_usage.py
```

### Resultados dos Testes

- ✅ **test_full_pipeline**: 90.48% acurácia, 2.3s média
- ✅ **test_template_accuracy**: 89.19% acurácia, cache 53.8%
- ✅ **test_api**: Todos os endpoints funcionando

## 📁 Estrutura do Projeto

```
enter-fellowship/
├── src/
│   ├── main.py                    # API FastAPI
│   ├── extraction/
│   │   └── llm.py                # LLM + unstructured
│   ├── cache/
│   │   ├── cache_manager.py      # Cache multi-level
│   │   └── cache_key.py          # Geração de chaves
│   ├── template/
│   │   ├── template_manager.py   # Orquestrador
│   │   ├── pattern_learner.py    # Aprendizado
│   │   ├── field_extractor.py    # Extração
│   │   ├── template_matcher.py   # Matching
│   │   └── database.py           # Persistência
│   └── storage/
│       ├── cache_data/           # Cache L2
│       └── templates.db          # Templates
├── Dockerfile                     # Container
├── docker-compose.yml            # Orquestração
├── requirements.txt              # Dependências
```

## 🎨 Tecnologias Utilizadas

- **LLM**: OpenAI GPT-5-mini
- **PDF Processing**: unstructured
- **Cache**: diskcache + OrderedDict (LRU)
- **Template DB**: SQLite
- **Hashing**: xxhash 
- **API**: FastAPI + uvicorn
- **Container**: Docker + Docker Compose

## 💡 Decisões de Design

### Por que Cache Multi-Level?
- L1: Requisições imediatas (mesmo processo)
- L2: Requisições após restart
- L3: Schemas parciais (flexibilidade)

### Por que Template Learning?
- Documentos similares aparecem frequentemente
- Evita chamadas LLM desnecessárias
- ~1000x mais rápido que LLM
- Fallback automático se acurácia baixa

### Por que unstructured + coordenadas?
- Preserva estrutura espacial do documento
- LLM entende "canto superior esquerdo"
- Detecta tabelas automaticamente
- Melhora acurácia em 10-15%

## 🏆 Diferenciais

1. **Cache Inteligente**: 3 níveis com partial schema matching
2. **Template Learning**: Aprende automaticamente sem supervisão
3. **Coordenadas Espaciais**: Contexto posicional para LLM
4. **Fallback Adaptativo**: Prioriza acurácia sobre velocidade
5. **API Production-Ready**: FastAPI + Docker + Health checks
6. **Monitoramento**: Estatísticas detalhadas em tempo real

---

**Desenvolvido para Enter AI Fellowship** | Novembro 2025

