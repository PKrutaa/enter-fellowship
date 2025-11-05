# Dockerfile Otimizado - Multi-stage build com UV

# ============== STAGE 1: Builder ==============
FROM python:3.13-slim as builder

# Variáveis de ambiente para build
ENV UV_SYSTEM_PYTHON=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Instala dependências do sistema (compilação + UV)
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    g++ \
    libmagic-dev \
    && rm -rf /var/lib/apt/lists/*

# Instala UV
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Adiciona UV ao PATH
ENV PATH="/root/.local/bin:$PATH"

# Copia e instala dependências
COPY requirements.txt .
RUN /root/.local/bin/uv pip install --system -r requirements.txt


# ============== STAGE 2: Runtime ==============
FROM python:3.13-slim

# Metadados
LABEL maintainer="Enter AI Fellowship"
LABEL description="API de extração de dados de PDFs - Otimizado com UV"

# Variáveis de ambiente
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Instala apenas runtime dependencies (não precisa compiladores)
RUN apt-get update && apt-get install -y \
    libmagic1 \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-por \
    curl \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copia dependências Python instaladas do builder
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copia código da aplicação
COPY src/ ./src/
COPY .env .env

# Cria diretórios necessários
RUN mkdir -p ./src/storage/cache_data && \
    mkdir -p ./src/storage && \
    chmod -R 777 ./src/storage

# Expõe porta
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Comando para iniciar a API
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]

