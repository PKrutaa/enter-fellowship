import sys
from pathlib import Path
import json
import os
import time
from typing import Dict, Any, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.extraction.llm import LLM

DATASET_PATH = "ai-fellowship-data/dataset.json"
PDF_PATH = "ai-fellowship-data/files/"
GT_PATH = "gt_pdf/"


def normalize_value(value: Any) -> str:
    """
    Normaliza valores para comparação case-insensitive
    """
    if value is None or value == "null":
        return "null"
    return str(value).strip().lower()


def compare_fields(predicted: Dict, ground_truth: Dict, schema: Dict[str, str]) -> Tuple[int, int, list]:
    """
    Compara campos preditos com ground truth
    
    Returns:
        (correct_fields, total_fields, errors)
    """
    correct = 0
    total = len(schema)
    errors = []
    
    for field in schema.keys():
        pred_value = normalize_value(predicted.get(field))
        gt_value = normalize_value(ground_truth.get(field))
        
        if pred_value == gt_value:
            correct += 1
        else:
            errors.append({
                "field": field,
                "predicted": predicted.get(field),
                "expected": ground_truth.get(field)
            })
    
    return correct, total, errors


def load_ground_truth(pdf_filename: str) -> Dict:
    """
    Carrega ground truth para um PDF
    """
    gt_filename = pdf_filename.replace(".pdf", ".json")
    gt_filepath = os.path.join(GT_PATH, gt_filename)
    
    if not os.path.exists(gt_filepath):
        return None
    
    with open(gt_filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def print_separator(char="=", length=80):
    print(char * length)


def print_comparison(predicted: Dict, ground_truth: Dict, errors: list):
    """
    Imprime comparação detalhada
    """
    print("\n📊 COMPARAÇÃO DETALHADA:")
    
    for field, pred_value in predicted.items():
        gt_value = ground_truth.get(field)
        
        # Verifica se está correto
        is_correct = normalize_value(pred_value) == normalize_value(gt_value)
        
        if is_correct:
            status = "✅"
        else:
            status = "❌"
        
        print(f"\n  {status} Campo: {field}")
        print(f"     Previsto: {pred_value}")
        print(f"     Esperado: {gt_value}")


def main():
    print_separator()
    print("🧪 TESTE DE ACURÁCIA: LLM vs Ground Truth")
    print_separator()
    
    llm_client = LLM()
    
    # Estatísticas globais
    global_stats = {
        "total_documents": 0,
        "total_fields": 0,
        "correct_fields": 0,
        "total_time": 0,
        "documents": []
    }
    
    with open(DATASET_PATH, "r") as f:
        dataset = json.load(f)
    
    for idx, item in enumerate(dataset, 1):
        pdf_path = os.path.join(PDF_PATH, item["pdf_path"])
        
        # Carrega ground truth
        ground_truth = load_ground_truth(item["pdf_path"])
        
        if not ground_truth:
            print(f"\n⚠️  Sem ground truth para: {item['pdf_path']}")
            continue
        
        print(f"\n{'─'*80}")
        print(f"📄 DOCUMENTO [{idx}/{len(dataset)}]: {item['pdf_path']}")
        print(f"📌 Label: {item['label']}")
        print(f"🔑 Campos: {len(item['extraction_schema'])}")
        print('─'*80)
        
        # Extração
        start_time = time.time()
        
        try:
            prompt = llm_client.generate_prompt(
                label=item["label"], 
                schema=item["extraction_schema"]
            )
            
            result_json = llm_client.extract_data(
                pdf_path=pdf_path, 
                prompt=prompt
            )
            
            extraction_time = time.time() - start_time
            
            # Parse resultado
            predicted = json.loads(result_json)
            
            # Compara com ground truth
            correct, total, errors = compare_fields(
                predicted, 
                ground_truth, 
                item["extraction_schema"]
            )
            
            accuracy = (correct / total * 100) if total > 0 else 0
            
            # Imprime resultados
            print(f"\n⏱️  Tempo de extração: {extraction_time:.2f}s")
            print(f"🎯 Acurácia: {correct}/{total} campos corretos ({accuracy:.1f}%)")
            
            if errors:
                print(f"\n❌ ERROS ENCONTRADOS ({len(errors)}):")
                for error in errors:
                    print(f"\n  Campo: '{error['field']}'")
                    print(f"  Previsto: {error['predicted']}")
                    print(f"  Esperado: {error['expected']}")
            else:
                print("\n✅ Todos os campos corretos!")
            
            # Mostra comparação completa
            print_comparison(predicted, ground_truth, errors)
            
            # Atualiza estatísticas globais
            global_stats["total_documents"] += 1
            global_stats["total_fields"] += total
            global_stats["correct_fields"] += correct
            global_stats["total_time"] += extraction_time
            global_stats["documents"].append({
                "filename": item["pdf_path"],
                "accuracy": accuracy,
                "correct": correct,
                "total": total,
                "time": extraction_time,
                "errors": len(errors)
            })
            
        except json.JSONDecodeError as e:
            print(f"❌ Erro ao parsear JSON: {e}")
            print(f"Resposta recebida: {result_json[:200]}...")
        except Exception as e:
            print(f"❌ Erro durante extração: {e}")
            import traceback
            traceback.print_exc()
    
    # Relatório final
    print("\n" + "="*80)
    print("📊 RELATÓRIO FINAL DE ACURÁCIA")
    print("="*80)
    
    if global_stats["total_documents"] > 0:
        overall_accuracy = (global_stats["correct_fields"] / global_stats["total_fields"] * 100)
        avg_time = global_stats["total_time"] / global_stats["total_documents"]
        
        print(f"\n📈 ESTATÍSTICAS GLOBAIS:")
        print(f"  • Documentos processados: {global_stats['total_documents']}")
        print(f"  • Total de campos: {global_stats['total_fields']}")
        print(f"  • Campos corretos: {global_stats['correct_fields']}")
        print(f"  • Acurácia geral: {overall_accuracy:.2f}%")
        print(f"  • Tempo médio: {avg_time:.2f}s/documento")
        print(f"  • Tempo total: {global_stats['total_time']:.2f}s")
        
        print(f"\n📄 DETALHES POR DOCUMENTO:")
        for doc in global_stats["documents"]:
            status = "✅" if doc["accuracy"] == 100 else "⚠️" if doc["accuracy"] >= 80 else "❌"
            print(f"  {status} {doc['filename']:25s} - {doc['accuracy']:5.1f}% ({doc['correct']}/{doc['total']}) - {doc['time']:.2f}s - {doc['errors']} erros")
        
        # Avaliação final
        print(f"\n🎯 AVALIAÇÃO FINAL:")
        if overall_accuracy >= 80:
            print(f"  ✅ META ALCANÇADA! Acurácia: {overall_accuracy:.2f}% (meta: ≥80%)")
        else:
            print(f"  ❌ Abaixo da meta. Acurácia: {overall_accuracy:.2f}% (meta: ≥80%)")
        
        if avg_time < 10:
            print(f"  ✅ Tempo OK! Média: {avg_time:.2f}s (meta: <10s)")
        else:
            print(f"  ⚠️  Tempo acima da meta. Média: {avg_time:.2f}s (meta: <10s)")
    else:
        print("\n⚠️  Nenhum documento foi processado com sucesso.")
    
    print("\n" + "="*80)


if __name__ == "__main__":
    main()