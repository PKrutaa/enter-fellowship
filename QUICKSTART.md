# ⚡ Guia Rápido

## 🐳 1. Rodar com Docker

```bash
# Configure API key
echo "OPENAI_API_KEY=sua-chave-aqui" > .env

# Inicie
docker compose up -d

# Verifique
curl http://localhost:8000/health
```

**Pronto!** API rodando em http://localhost:8000

Acesse o frontend: https://enter-fellowship-front.vercel.app/

---

## 📦 2. Processar Batch de PDFs (Sem UI)

### Via Script CLI

```bash
# Prepare dataset.json
cat > dataset.json << EOF
[
  {
    "pdf_path": "doc1.pdf",
    "label": "carteira_oab",
    "extraction_schema": {
      "nome": "Nome completo",
      "inscricao": "Número OAB"
    }
  }
]
EOF

# Execute dentro do Docker
docker compose exec api python src/batch_extract.py \
  --pdf-dir ./pdfs \
  --dataset-path dataset.json \
  --output-dir output

# Ou localmente
uv run src/batch_extract.py \
  --pdf-dir ./pdfs \
  --dataset-path dataset.json \
  --output-dir output
```

---

## 📖 3. Usar a API

### Documentação Interativa
http://localhost:8000/docs

### Exemplo cURL

```bash
# Extrair PDF individual
curl -X POST "http://localhost:8000/extract" \
  -F "file=@documento.pdf" \
  -F "label=carteira_oab" \
  -F 'extraction_schema={"nome":"Nome","inscricao":"Número OAB"}'

# Ver estatísticas
curl http://localhost:8000/stats
```

### Exemplo Python

```python
import requests

# Upload arquivo
with open("documento.pdf", "rb") as f:
    response = requests.post(
        "http://localhost:8000/extract",
        files={"file": f},
        data={
            "label": "carteira_oab",
            "extraction_schema": '{"nome":"Nome","inscricao":"Número OAB"}'
        }
    )

result = response.json()
print(result["data"])  # {"nome": "João Silva", "inscricao": "123456"}
```

---

## 🔧 4. Comandos Docker Úteis

```bash
# Ver logs
docker compose logs -f

# Parar
docker compose down

# Rebuild após mudanças
docker compose up -d --build

# Entrar no container
docker compose exec api bash

# Limpar tudo
docker compose down -v
```

---

## 📊 5. Monitorar

```bash
# Health check
curl http://localhost:8000/health

# Estatísticas
curl http://localhost:8000/stats

# Ver uso de recursos
docker stats
```

---

## 🎯 Próximos Passos

1. Leia o [README.md](README.md) completo para entender a arquitetura
3. Acesse http://localhost:8000/docs para API interativa
4. Modifique schemas conforme seus documentos

---

**Dúvidas?** Veja [README.md](README.md) ou [troubleshooting](README.md#-troubleshooting)

