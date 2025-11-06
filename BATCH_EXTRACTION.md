# 🚀 Script de Extração em Lote

Script CLI para processar múltiplos PDFs em paralelo, agrupados por label.

## 📋 Características

- ✅ **Processamento Paralelo por Label**: Labels diferentes são processados em paralelo
- ✅ **Processamento Sequencial por Label**: PDFs do mesmo label são processados sequencialmente (evita conflitos no template learning)
- ✅ **Resultados Progressivos**: JSONs individuais são salvos conforme são processados
- ✅ **JSON Consolidado**: Ao final, gera um JSON com todos os resultados
- ✅ **Barra de Progresso**: Acompanhamento visual em tempo real
- ✅ **Tratamento de Erros**: Continua processando mesmo se algum PDF falhar
- ✅ **Estatísticas Detalhadas**: Métricas de tempo, métodos utilizados, taxa de sucesso

## 🔧 Instalação

```bash
# Instalar dependências (incluindo tqdm)
pip install -r requirements.txt

# Ou usando UV (mais rápido)
uv pip install -r requirements.txt
```

## 🚀 Uso

### Comando Básico

```bash
python src/batch_extract.py \
  --pdf-dir ai-fellowship-data/files \
  --dataset-path ai-fellowship-data/dataset.json \
  --output-dir output
```

### Argumentos

| Argumento | Descrição | Obrigatório | Padrão |
|-----------|-----------|-------------|--------|
| `--pdf-dir` | Diretório contendo os arquivos PDF | ✓ | - |
| `--dataset-path` | Caminho para o arquivo dataset.json | ✓ | - |
| `--output-dir` | Diretório de saída para os JSONs | ✗ | `output` |
| `--max-workers` | Número máximo de workers paralelos | ✗ | Número de CPUs |

### Exemplo com Mais Workers

```bash
python src/batch_extract.py \
  --pdf-dir ai-fellowship-data/files \
  --dataset-path ai-fellowship-data/dataset.json \
  --output-dir results \
  --max-workers 4
```

## 📂 Estrutura do Dataset.json

O arquivo `dataset.json` deve ter a seguinte estrutura:

```json
[
  {
    "label": "carteira_oab",
    "extraction_schema": {
      "nome": "Nome do profissional",
      "inscricao": "Número de inscrição",
      "seccional": "Seccional do profissional"
    },
    "pdf_path": "oab_1.pdf"
  },
  {
    "label": "tela_sistema",
    "extraction_schema": {
      "data_base": "Data base da operação",
      "produto": "Produto da operação"
    },
    "pdf_path": "tela_sistema_1.pdf"
  }
]
```

## 📁 Estrutura de Saída

Após a execução, a estrutura de saída será:

```
output/
├── individual/
│   ├── oab_1.json              # Resultado individual
│   ├── oab_2.json
│   ├── oab_3.json
│   ├── tela_sistema_1.json
│   ├── tela_sistema_2.json
│   └── tela_sistema_3.json
└── consolidated_results.json   # Todos os resultados consolidados
```

### Formato do JSON Individual

```json
{
  "pdf_path": "oab_1.pdf",
  "label": "carteira_oab",
  "success": true,
  "data": {
    "nome": "João Silva",
    "inscricao": "123456",
    "seccional": "SP"
  },
  "metadata": {
    "method": "llm",
    "pipeline_info": {
      "method": "llm",
      "time": 2.3,
      "learned": true
    }
  }
}
```

### Formato do JSON Consolidado

```json
{
  "total_processed": 6,
  "total_success": 6,
  "total_failed": 0,
  "processing_time_seconds": 12.5,
  "results": [
    {
      "pdf_path": "oab_1.pdf",
      "label": "carteira_oab",
      "success": true,
      "data": {...},
      "metadata": {...}
    },
    ...
  ]
}
```

## 🔄 Fluxo de Processamento

```
1. Carrega dataset.json
   ↓
2. Agrupa PDFs por label
   ├── carteira_oab: [oab_1.pdf, oab_2.pdf, oab_3.pdf]
   └── tela_sistema: [tela_sistema_1.pdf, tela_sistema_2.pdf, tela_sistema_3.pdf]
   ↓
3. Processa labels em PARALELO
   ├── Worker 1 (Label: carteira_oab)
   │   ├── oab_1.pdf → ✓ Saved
   │   ├── oab_2.pdf → ✓ Saved
   │   └── oab_3.pdf → ✓ Saved
   │
   └── Worker 2 (Label: tela_sistema)  [Em paralelo com Worker 1]
       ├── tela_sistema_1.pdf → ✓ Saved
       ├── tela_sistema_2.pdf → ✓ Saved
       └── tela_sistema_3.pdf → ✓ Saved
   ↓
4. Gera JSON consolidado
```

## 📊 Exemplo de Saída do Console

```
================================================================================
🚀 Extração em Lote de PDFs - Processamento Paralelo por Label
================================================================================
📂 PDF Dir: ai-fellowship-data/files
📄 Dataset: ai-fellowship-data/dataset.json
💾 Output: output
================================================================================

✓ Dataset carregado: 6 PDFs
✓ Agrupado por label: 2 labels diferentes
  • carteira_oab: 3 PDFs
  • tela_sistema: 3 PDFs

🔄 Processando PDFs...

✓ [carteira_oab] oab_1.pdf (llm)
✓ [tela_sistema] tela_sistema_1.pdf (llm)
✓ [carteira_oab] oab_2.pdf (template)
✓ [tela_sistema] tela_sistema_2.pdf (template)
✓ [carteira_oab] oab_3.pdf (template)
✓ [tela_sistema] tela_sistema_3.pdf (template)

Total Progress: 100%|██████████████████████████| 6/6 [00:12<00:00,  2.08s/pdf]

📄 Consolidated JSON saved: output/consolidated_results.json

================================================================================
📊 ESTATÍSTICAS FINAIS
================================================================================
✓ Total processado: 6 PDFs
✓ Sucesso: 6
✗ Falhas: 0
⏱️  Tempo total: 12.45s
⚡ Tempo médio: 2.08s por PDF

📈 Métodos utilizados:
  • llm: 2 PDFs (33.3%)
  • template: 4 PDFs (66.7%)

================================================================================
✅ Processamento concluído!
================================================================================
```

## 🎯 Vantagens da Abordagem

### 1. **Processamento Paralelo Inteligente**
- Labels diferentes processam em paralelo (máxima velocidade)
- Mesmo label processa sequencialmente (evita conflitos)

### 2. **Template Learning Eficiente**
- Cada worker aprende templates do seu label
- Não há contenção no banco de dados de templates
- Aprendizado acontece em paralelo para labels diferentes

### 3. **Resultados Progressivos**
- JSONs individuais salvos imediatamente após processamento
- Não precisa esperar todos os PDFs terminarem
- Útil para processar grandes lotes

### 4. **Resiliência a Erros**
- Se um PDF falhar, os outros continuam
- Erros são registrados no JSON individual
- Estatísticas finais mostram taxa de sucesso

## ⚡ Performance

Com 2 labels diferentes e 3 PDFs cada:

- **Sem paralelismo**: ~15-20s (sequencial)
- **Com paralelismo**: ~7-12s (labels em paralelo)
- **Speedup**: ~1.5-2x

Com mais labels:

- **4 labels**: ~3-4x speedup
- **8 labels**: ~5-8x speedup (limitado por CPUs)

## 🐛 Troubleshooting

### Erro: "Dataset não encontrado"
```bash
# Verifique o caminho do dataset
ls -la ai-fellowship-data/dataset.json
```

### Erro: "PDF não encontrado"
```bash
# Verifique os arquivos PDF
ls -la ai-fellowship-data/files/
```

### Erro: "ModuleNotFoundError: No module named 'tqdm'"
```bash
# Instale as dependências
pip install -r requirements.txt
```

### Processamento muito lento
```bash
# Reduza o número de workers se a máquina tiver pouca RAM
python src/batch_extract.py ... --max-workers 2
```

## 📝 Notas

- O script cria automaticamente o diretório de saída se não existir
- JSONs são salvos com encoding UTF-8 e indentação de 2 espaços
- Cada processo worker tem sua própria instância da pipeline
- O cache e template learning funcionam normalmente em cada worker
- Resultados são coletados conforme os workers terminam (ordem pode variar)

---

**Desenvolvido para Enter AI Fellowship** | Novembro 2025

