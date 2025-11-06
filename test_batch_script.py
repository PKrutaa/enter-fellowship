#!/usr/bin/env python3
"""
Script de teste rápido para verificar se o batch_extract.py está funcionando

Este script verifica:
1. Imports necessários
2. Funções principais do batch_extract
3. Estrutura do dataset
"""

import sys
from pathlib import Path

# Adiciona o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """Testa se todos os imports necessários funcionam"""
    print("🔍 Testando imports...")
    
    try:
        from src.pipeline import ExtractionPipeline
        print("  ✓ ExtractionPipeline")
    except ImportError as e:
        print(f"  ✗ ExtractionPipeline: {e}")
        return False
    
    try:
        from src.batch_extract import load_dataset, group_by_label
        print("  ✓ batch_extract functions")
    except ImportError as e:
        print(f"  ✗ batch_extract functions: {e}")
        return False
    
    try:
        import tqdm
        print("  ✓ tqdm")
    except ImportError as e:
        print(f"  ✗ tqdm: {e}")
        print("     Instale com: pip install tqdm")
        return False
    
    return True


def test_dataset_structure():
    """Testa se o dataset.json tem a estrutura esperada"""
    print("\n🔍 Testando estrutura do dataset...")
    
    try:
        from src.batch_extract import load_dataset, group_by_label
        
        dataset_path = "ai-fellowship-data/dataset.json"
        dataset = load_dataset(dataset_path)
        
        print(f"  ✓ Dataset carregado: {len(dataset)} itens")
        
        grouped = group_by_label(dataset)
        print(f"  ✓ Agrupado por label: {len(grouped)} labels")
        
        for label, items in grouped.items():
            print(f"    • {label}: {items[0]['pdf_path']} (+{len(items)-1} mais)")
        
        return True
        
    except FileNotFoundError as e:
        print(f"  ✗ Arquivo não encontrado: {e}")
        return False
    except Exception as e:
        print(f"  ✗ Erro: {e}")
        return False


def test_pipeline():
    """Testa se a pipeline pode ser instanciada"""
    print("\n🔍 Testando pipeline...")
    
    try:
        from src.pipeline import ExtractionPipeline
        
        # Tenta criar instância (singleton)
        pipeline = ExtractionPipeline()
        
        print("  ✓ Pipeline instanciada")
        print(f"  ✓ LLM: {pipeline.llm.model}")
        print(f"  ✓ Cache: {pipeline.cache}")
        print(f"  ✓ Template Manager: {pipeline.template_manager}")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Erro ao instanciar pipeline: {e}")
        print("     Nota: Verifique se OPENAI_API_KEY está configurado no .env")
        return False


def main():
    """Executa todos os testes"""
    print("="*80)
    print("🧪 Teste do Script de Extração em Lote")
    print("="*80)
    
    results = []
    
    # Teste 1: Imports
    results.append(("Imports", test_imports()))
    
    # Teste 2: Dataset
    results.append(("Dataset", test_dataset_structure()))
    
    # Teste 3: Pipeline
    results.append(("Pipeline", test_pipeline()))
    
    # Sumário
    print("\n" + "="*80)
    print("📊 SUMÁRIO DOS TESTES")
    print("="*80)
    
    for name, passed in results:
        status = "✓ PASSOU" if passed else "✗ FALHOU"
        print(f"{status}: {name}")
    
    total_passed = sum(1 for _, passed in results if passed)
    total_tests = len(results)
    
    print(f"\nTotal: {total_passed}/{total_tests} testes passaram")
    
    if total_passed == total_tests:
        print("\n✅ Todos os testes passaram! O script está pronto para uso.")
        print("\nPara executar a extração em lote, use:")
        print("  ./run_batch_extraction.sh")
        print("ou")
        print("  python3 src/batch_extract.py --pdf-dir ai-fellowship-data/files --dataset-path ai-fellowship-data/dataset.json")
    else:
        print("\n⚠️ Alguns testes falharam. Verifique os erros acima.")
    
    print("="*80)


if __name__ == "__main__":
    main()

