#!/bin/bash
# Inicia a API localmente com UV

set -e

echo "🚀 Iniciando API com UV..."

# Verifica se UV está instalado
if ! command -v uv &> /dev/null; then
    echo "❌ UV não encontrado. Instalando..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    
    # Adiciona UV ao PATH da sessão atual
    export PATH="$HOME/.cargo/bin:$PATH"
fi

# Verifica .env
if [ ! -f .env ]; then
    echo "⚠️  Arquivo .env não encontrado"
    echo "📝 Crie um arquivo .env com: OPENAI_API_KEY=sua-chave"
    exit 1
fi

# Verifica se API key está configurada
if ! grep -q "OPENAI_API_KEY=" .env; then
    echo "⚠️  OPENAI_API_KEY não encontrada no .env"
    echo "📝 Adicione: OPENAI_API_KEY=sua-chave-aqui"
    exit 1
fi

# Instala dependências
echo "📦 Instalando dependências..."
uv pip install -r requirements.txt

echo ""
echo "✅ Tudo pronto!"
echo "📍 API rodando em: http://localhost:8000"
echo "📚 Docs disponíveis em: http://localhost:8000/docs"
echo "🏥 Health check: http://localhost:8000/health"
echo ""
echo "Para testar:"
echo "  curl http://localhost:8000/health"
echo ""

# Inicia API
uv run src/main.py

