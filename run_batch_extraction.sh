#!/bin/bash
#
# Script auxiliar para executar extração em lote
# 
# Usage:
#   ./run_batch_extraction.sh
#

set -e

echo "========================================"
echo "  Extração em Lote de PDFs"
echo "========================================"
echo ""

# Configurações padrão
PDF_DIR="ai-fellowship-data/files"
DATASET_PATH="ai-fellowship-data/dataset.json"
OUTPUT_DIR="output"

# Verifica se diretórios existem
if [ ! -d "$PDF_DIR" ]; then
    echo "❌ Erro: Diretório $PDF_DIR não encontrado"
    exit 1
fi

if [ ! -f "$DATASET_PATH" ]; then
    echo "❌ Erro: Arquivo $DATASET_PATH não encontrado"
    exit 1
fi

# Limpa output anterior (opcional - comente se não quiser)
if [ -d "$OUTPUT_DIR" ]; then
    echo "🗑️  Limpando output anterior..."
    rm -rf "$OUTPUT_DIR"
fi

# Executa extração
echo "🚀 Iniciando extração em lote..."
echo ""

python3 src/batch_extract.py \
    --pdf-dir "$PDF_DIR" \
    --dataset-path "$DATASET_PATH" \
    --output-dir "$OUTPUT_DIR"

echo ""
echo "✅ Extração concluída!"
echo ""
echo "📂 Resultados salvos em: $OUTPUT_DIR"
echo "   • JSONs individuais: $OUTPUT_DIR/individual/"
echo "   • JSON consolidado: $OUTPUT_DIR/consolidated_results.json"

