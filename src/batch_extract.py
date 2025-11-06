#!/usr/bin/env python3
"""
Script de Extração em Lote de PDFs

Processa múltiplos PDFs em paralelo, agrupados por label para evitar
conflitos no template learning. Salva JSONs individuais conforme são
processados e gera um JSON consolidado ao final.

Usage:
    python src/batch_extract.py \
        --pdf-dir ai-fellowship-data/files \
        --dataset-path ai-fellowship-data/dataset.json \
        --output-dir output
"""

import json
import os
import sys
import argparse
import time
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Dict, List, Any
from tqdm import tqdm

# Adiciona o diretório raiz ao path para permitir imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pipeline import ExtractionPipeline


def load_dataset(dataset_path: str) -> List[Dict[str, Any]]:
    """Carrega e valida dataset.json
    
    Args:
        dataset_path: Caminho para o arquivo dataset.json
        
    Returns:
        Lista de dicionários com {label, extraction_schema, pdf_path}
        
    Raises:
        FileNotFoundError: Se dataset.json não existir
        json.JSONDecodeError: Se dataset.json não for JSON válido
        ValueError: Se dataset.json não tiver estrutura esperada
    """
    if not os.path.exists(dataset_path):
        raise FileNotFoundError(f"Dataset não encontrado: {dataset_path}")
    
    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)
    
    # Valida estrutura
    if not isinstance(dataset, list):
        raise ValueError("Dataset deve ser uma lista de objetos")
    
    for i, item in enumerate(dataset):
        if not all(k in item for k in ["label", "extraction_schema", "pdf_path"]):
            raise ValueError(f"Item {i} do dataset está faltando campos obrigatórios")
    
    return dataset


def group_by_label(dataset: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Agrupa itens do dataset por label
    
    Args:
        dataset: Lista de itens do dataset
        
    Returns:
        Dicionário {label: [items]}
    """
    grouped = defaultdict(list)
    for item in dataset:
        grouped[item["label"]].append(item)
    return dict(grouped)


def process_single_pdf(
    pdf_path: str,
    full_pdf_path: str,
    label: str,
    extraction_schema: Dict[str, str],
    output_dir: str
) -> Dict[str, Any]:
    """Processa um único PDF e salva resultado individual
    
    Args:
        pdf_path: Nome do arquivo PDF (para identificação)
        full_pdf_path: Caminho completo para o arquivo PDF
        label: Label do documento
        extraction_schema: Schema de extração
        output_dir: Diretório de saída
        
    Returns:
        Dicionário com resultado da extração
    """
    try:
        # Lê o PDF
        with open(full_pdf_path, "rb") as f:
            pdf_bytes = f.read()
        
        # Processa usando pipeline
        pipeline = ExtractionPipeline()
        result = pipeline.extract(
            pdf_bytes=pdf_bytes,
            label=label,
            schema=extraction_schema
        )
        
        # Separa dados de metadata
        data = {k: v for k, v in result.items() if not k.startswith("_")}
        metadata = {
            "method": result.get("_pipeline", {}).get("method", "unknown"),
            "pipeline_info": result.get("_pipeline", {}),
            "cache_info": result.get("_cache", {})
        }
        
        # Prepara resultado estruturado
        structured_result = {
            "pdf_path": pdf_path,
            "label": label,
            "success": True,
            "data": data,
            "metadata": metadata
        }
        
        # Salva JSON individual
        save_individual_result(structured_result, pdf_path, output_dir)
        
        return structured_result
        
    except Exception as e:
        # Em caso de erro, retorna resultado com falha
        error_result = {
            "pdf_path": pdf_path,
            "label": label,
            "success": False,
            "error": str(e),
            "data": None,
            "metadata": None
        }
        
        # Salva JSON individual mesmo em caso de erro
        save_individual_result(error_result, pdf_path, output_dir)
        
        return error_result


def save_individual_result(result: Dict[str, Any], pdf_path: str, output_dir: str) -> None:
    """Salva resultado individual em JSON
    
    Args:
        result: Dicionário com resultado da extração
        pdf_path: Nome do arquivo PDF
        output_dir: Diretório de saída
    """
    individual_dir = os.path.join(output_dir, "individual")
    os.makedirs(individual_dir, exist_ok=True)
    
    # Remove extensão .pdf e adiciona .json
    json_filename = os.path.splitext(pdf_path)[0] + ".json"
    json_path = os.path.join(individual_dir, json_filename)
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)


def process_label_group(
    label: str,
    items: List[Dict[str, Any]],
    pdf_dir: str,
    output_dir: str
) -> List[Dict[str, Any]]:
    """Processa todos os PDFs de um label sequencialmente
    
    Esta função é executada em paralelo para cada label diferente,
    mas processa os PDFs do mesmo label sequencialmente para evitar
    conflitos no template learning.
    
    Args:
        label: Label do grupo
        items: Lista de itens do dataset para este label
        pdf_dir: Diretório com os arquivos PDF
        output_dir: Diretório de saída
        
    Returns:
        Lista de resultados da extração
    """
    results = []
    
    for item in items:
        pdf_path = item["pdf_path"]
        full_pdf_path = os.path.join(pdf_dir, pdf_path)
        
        if not os.path.exists(full_pdf_path):
            print(f"⚠️  [{label}] PDF não encontrado: {pdf_path}")
            results.append({
                "pdf_path": pdf_path,
                "label": label,
                "success": False,
                "error": "File not found",
                "data": None,
                "metadata": None
            })
            continue
        
        result = process_single_pdf(
            pdf_path=pdf_path,
            full_pdf_path=full_pdf_path,
            label=label,
            extraction_schema=item["extraction_schema"],
            output_dir=output_dir
        )
        
        results.append(result)
        
        # Log de progresso
        status = "✓" if result["success"] else "✗"
        method = result.get("metadata", {}).get("method", "unknown") if result["success"] else "error"
        print(f"{status} [{label}] {pdf_path} ({method})")
    
    return results


def create_consolidated_json(output_dir: str, all_results: List[Dict[str, Any]], total_time: float) -> None:
    """Cria JSON consolidado com todos os resultados
    
    Args:
        output_dir: Diretório de saída
        all_results: Lista com todos os resultados
        total_time: Tempo total de processamento
    """
    total_success = sum(1 for r in all_results if r["success"])
    total_failed = len(all_results) - total_success
    
    consolidated = {
        "total_processed": len(all_results),
        "total_success": total_success,
        "total_failed": total_failed,
        "processing_time_seconds": round(total_time, 2),
        "results": all_results
    }
    
    consolidated_path = os.path.join(output_dir, "consolidated_results.json")
    with open(consolidated_path, "w", encoding="utf-8") as f:
        json.dump(consolidated, f, indent=2, ensure_ascii=False)
    
    print(f"\n📄 Consolidated JSON saved: {consolidated_path}")


def main():
    """Função principal do script"""
    
    # Parse argumentos
    parser = argparse.ArgumentParser(
        description="Extração em lote de PDFs com processamento paralelo por label",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--pdf-dir",
        type=str,
        required=True,
        help="Diretório contendo os arquivos PDF"
    )
    
    parser.add_argument(
        "--dataset-path",
        type=str,
        required=True,
        help="Caminho para o arquivo dataset.json"
    )
    
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output",
        help="Diretório de saída para os JSONs (padrão: output)"
    )
    
    parser.add_argument(
        "--max-workers",
        type=int,
        default=None,
        help="Número máximo de workers paralelos (padrão: número de CPUs)"
    )
    
    args = parser.parse_args()
    
    # Validações
    if not os.path.exists(args.pdf_dir):
        print(f"❌ Diretório de PDFs não encontrado: {args.pdf_dir}")
        sys.exit(1)
    
    if not os.path.exists(args.dataset_path):
        print(f"❌ Dataset não encontrado: {args.dataset_path}")
        sys.exit(1)
    
    # Cria diretório de saída
    os.makedirs(args.output_dir, exist_ok=True)
    os.makedirs(os.path.join(args.output_dir, "individual"), exist_ok=True)
    
    # Banner inicial
    print("=" * 80)
    print("🚀 Extração em Lote de PDFs - Processamento Paralelo por Label")
    print("=" * 80)
    print(f"📂 PDF Dir: {args.pdf_dir}")
    print(f"📄 Dataset: {args.dataset_path}")
    print(f"💾 Output: {args.output_dir}")
    print("=" * 80 + "\n")
    
    # Carrega dataset
    try:
        dataset = load_dataset(args.dataset_path)
        print(f"✓ Dataset carregado: {len(dataset)} PDFs")
    except Exception as e:
        print(f"❌ Erro ao carregar dataset: {e}")
        sys.exit(1)
    
    # Agrupa por label
    grouped = group_by_label(dataset)
    print(f"✓ Agrupado por label: {len(grouped)} labels diferentes")
    for label, items in grouped.items():
        print(f"  • {label}: {len(items)} PDFs")
    print()
    
    # Processamento paralelo por label
    start_time = time.time()
    all_results = []
    
    print("🔄 Processando PDFs...\n")
    
    # Usa ProcessPoolExecutor para processar labels em paralelo
    with ProcessPoolExecutor(max_workers=args.max_workers) as executor:
        # Submit tasks para cada label
        future_to_label = {
            executor.submit(
                process_label_group,
                label,
                items,
                args.pdf_dir,
                args.output_dir
            ): label
            for label, items in grouped.items()
        }
        
        # Processa resultados conforme são completados
        with tqdm(total=len(dataset), desc="Total Progress", unit="pdf") as pbar:
            for future in as_completed(future_to_label):
                label = future_to_label[future]
                try:
                    results = future.result()
                    all_results.extend(results)
                    pbar.update(len(results))
                except Exception as e:
                    print(f"\n❌ Erro ao processar label {label}: {e}")
                    pbar.update(len(grouped[label]))
    
    total_time = time.time() - start_time
    
    # Cria JSON consolidado
    create_consolidated_json(args.output_dir, all_results, total_time)
    
    # Estatísticas finais
    print("\n" + "=" * 80)
    print("📊 ESTATÍSTICAS FINAIS")
    print("=" * 80)
    
    total_success = sum(1 for r in all_results if r["success"])
    total_failed = len(all_results) - total_success
    
    print(f"✓ Total processado: {len(all_results)} PDFs")
    print(f"✓ Sucesso: {total_success}")
    print(f"✗ Falhas: {total_failed}")
    print(f"⏱️  Tempo total: {total_time:.2f}s")
    print(f"⚡ Tempo médio: {total_time / len(all_results):.2f}s por PDF")
    
    # Estatísticas por método
    methods = defaultdict(int)
    for r in all_results:
        if r["success"]:
            method = r.get("metadata", {}).get("method", "unknown")
            methods[method] += 1
    
    if methods:
        print(f"\n📈 Métodos utilizados:")
        for method, count in methods.items():
            print(f"  • {method}: {count} PDFs ({count/total_success*100:.1f}%)")
    
    print("\n" + "=" * 80)
    print("✅ Processamento concluído!")
    print("=" * 80)


if __name__ == "__main__":
    main()
