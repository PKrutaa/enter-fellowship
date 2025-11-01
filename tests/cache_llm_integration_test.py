import sys
from pathlib import Path
import json
import os
import time
from typing import Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.extraction.llm import LLM
from src.cache.cache_manager import CacheManager

DATASET_PATH = "ai-fellowship-data/dataset.json"
PDF_PATH = "ai-fellowship-data/files/"

class CachedLLMExtractor:
    """
    Wrapper que combina LLM + Cache para extração otimizada
    """
    
    def __init__(self):
        self.llm = LLM()
        self.cache = CacheManager(
            cache_dir="./cache_data",
            memory_size=100
        )
    
    def extract(
        self, 
        pdf_bytes: bytes, 
        label: str, 
        schema: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Extrai dados com cache automático
        
        Flow:
        1. Verifica cache (L1 → L2 → L3)
        2. Se cache miss, chama LLM
        3. Armazena resultado no cache
        4. Retorna resultado + metadata
        """
        start_time = time.time()
        
        # Tenta buscar no cache
        cached_result = self.cache.get(pdf_bytes, label, schema)
        
        if cached_result:
            # CACHE HIT! 🎯
            elapsed = time.time() - start_time
            
            print(f"✅ CACHE HIT ({cached_result['_cache']['source']}) - {elapsed*1000:.1f}ms")
            return cached_result
        
        # CACHE MISS - chama LLM
        print("❌ CACHE MISS - Chamando LLM...")
        llm_start = time.time()
        
        prompt = self.llm.generate_prompt(label, schema)
        result_json = self.llm.extract_data(pdf_bytes, prompt)
        
        llm_time = time.time() - llm_start
        
        # Parse JSON
        try:
            result = json.loads(result_json)
        except json.JSONDecodeError:
            print(f"⚠️  JSON inválido: {result_json}")
            result = {}
        
        # Armazena no cache
        self.cache.set(
            pdf_bytes=pdf_bytes,
            label=label,
            schema=schema,
            result=result,
            metadata={
                "llm_time": llm_time,
                "time_saved": llm_time,  # Tempo que será economizado em próximas calls
                "cost_saved": self._estimate_cost(result_json)
            }
        )
        
        total_time = time.time() - start_time
        print(f"⏱️  LLM respondeu em {llm_time:.2f}s (total: {total_time:.2f}s)")
        
        # Adiciona metadata
        result["_cache"] = {
            "hit": False,
            "source": "LLM",
            "llm_time": llm_time
        }
        
        return result
    
    def _estimate_cost(self, response: str) -> float:
        """
        Estima custo da chamada LLM
        
        gpt-5-mini pricing (aproximado):
        - Input: ~$0.03 / 1M tokens
        - Output: ~$0.06 / 1M tokens
        """
        # Estimativa simples: ~1000 tokens input, ~200 tokens output
        input_tokens = 1000
        output_tokens = len(response.split())
        
        input_cost = (input_tokens / 1_000_000) * 0.03
        output_cost = (output_tokens / 1_000_000) * 0.06
        
        return input_cost + output_cost
    
    def get_stats(self):
        """Retorna estatísticas do cache"""
        return self.cache.get_stats()


def print_separator(title: str = ""):
    """Imprime separador visual"""
    if title:
        print(f"\n{'='*80}")
        print(f"  {title}")
        print('='*80)
    else:
        print('='*80)


def print_result(result: Dict[str, Any], show_cache_info: bool = True):
    """Imprime resultado formatado"""
    # Separa dados do cache dos dados extraídos
    cache_info = result.pop("_cache", None)
    
    print("\n📄 DADOS EXTRAÍDOS:")
    for key, value in result.items():
        if not key.startswith("_"):
            print(f"  • {key}: {value}")
    
    if show_cache_info and cache_info:
        print(f"\n💾 CACHE INFO:")
        print(f"  • Source: {cache_info.get('source', 'N/A')}")
        if cache_info.get('hit'):
            print(f"  • Retrieval time: {cache_info.get('retrieval_time', 0)*1000:.1f}ms")
            if cache_info.get('is_partial'):
                print(f"  • Match rate: {cache_info.get('match_rate', 0)*100:.0f}%")
                print(f"  • Missing fields: {cache_info.get('missing_fields', [])}")
        else:
            print(f"  • LLM time: {cache_info.get('llm_time', 0):.2f}s")


def test_cache_performance():
    """
    Teste de performance do cache com cenários reais
    """
    print_separator("🚀 TESTE DE PERFORMANCE: LLM + CACHE")
    
    extractor = CachedLLMExtractor()
    
    # Carrega dataset
    with open(DATASET_PATH, "r") as f:
        dataset = json.load(f)
    
    # Pega primeiro item para teste
    test_item = dataset[0]
    
    with open(os.path.join(PDF_PATH, test_item["pdf_path"]), "rb") as f:
        pdf_bytes = f.read()
    
    label = test_item["label"]
    schema = test_item["extraction_schema"]
    
    print(f"\n📋 Documento: {test_item['pdf_path']}")
    print(f"📌 Label: {label}")
    print(f"🔑 Campos: {len(schema)}")
    
    # ========== TESTE 1: PRIMEIRA CHAMADA (CACHE MISS) ==========
    print_separator("TESTE 1: Primeira chamada (CACHE MISS esperado)")
    
    result1 = extractor.extract(pdf_bytes, label, schema)
    print_result(result1)
    
    # ========== TESTE 2: SEGUNDA CHAMADA - MESMO REQUEST (L1 HIT) ==========
    print_separator("TESTE 2: Mesma chamada (L1 MEMORY HIT esperado)")
    
    result2 = extractor.extract(pdf_bytes, label, schema)
    print_result(result2)
    
    # ========== TESTE 3: LIMPA L1, BUSCA DE NOVO (L2 HIT) ==========
    print_separator("TESTE 3: Limpa L1, busca novamente (L2 DISK HIT esperado)")
    
    extractor.cache.clear_memory_only()
    print("🧹 Memory cache limpo (L1)")
    
    result3 = extractor.extract(pdf_bytes, label, schema)
    print_result(result3)
    
    # ========== TESTE 4: PARTIAL SCHEMA MATCH (L3) ==========
    print_separator("TESTE 4: Schema parcial (L3 PARTIAL HIT esperado)")
    
    # Cria schema reduzido (remove alguns campos)
    partial_schema = dict(list(schema.items())[:3])  # Apenas 3 primeiros campos
    print(f"📝 Schema reduzido: {list(partial_schema.keys())}")
    
    result4 = extractor.extract(pdf_bytes, label, partial_schema)
    print_result(result4)
    
    # ========== TESTE 5: MÚLTIPLAS CHAMADAS (BENCHMARK) ==========
    print_separator("TESTE 5: Benchmark - 10 chamadas consecutivas")
    
    times = []
    for i in range(10):
        start = time.time()
        extractor.extract(pdf_bytes, label, schema)
        elapsed = time.time() - start
        times.append(elapsed)
        print(f"  Call {i+1}: {elapsed*1000:.1f}ms")
    
    avg_time = sum(times) / len(times)
    print(f"\n📊 Média: {avg_time*1000:.1f}ms")
    print(f"⚡ Mais rápido: {min(times)*1000:.1f}ms")
    print(f"🐌 Mais lento: {max(times)*1000:.1f}ms")
    
    # ========== ESTATÍSTICAS FINAIS ==========
    print_separator("📊 ESTATÍSTICAS FINAIS DO CACHE")
    
    stats = extractor.get_stats()
    
    print(f"\n📈 REQUISIÇÕES:")
    print(f"  • Total: {stats['total_requests']}")
    print(f"  • Cache hits: {stats['cache_hits']['total']}")
    print(f"  • Cache misses: {stats['cache_misses']}")
    
    print(f"\n🎯 HIT RATES:")
    print(f"  • Overall: {stats['hit_rates']['overall']}")
    print(f"  • L1 (Memory): {stats['hit_rates']['l1']}")
    print(f"  • L2 (Disk): {stats['hit_rates']['l2']}")
    print(f"  • L3 (Partial): {stats['hit_rates']['l3']}")
    
    print(f"\n💾 CACHE SIZE:")
    print(f"  • Memory items: {stats['cache_sizes']['memory_items']}/{stats['cache_sizes']['memory_max']}")
    print(f"  • Disk items: {stats['cache_sizes']['disk_items']}")
    print(f"  • Disk size: {stats['cache_sizes']['disk_size_mb']:.2f} MB")
    
    print(f"\n💰 ECONOMIA:")
    print(f"  • Tempo economizado: {stats['savings']['time_saved_seconds']:.2f}s")
    print(f"  • Custo economizado: ${stats['savings']['cost_saved_dollars']:.4f}")
    print(f"  • Tempo médio por hit: {stats['savings']['avg_time_per_hit']*1000:.1f}ms")
    
    print_separator("✅ TESTE COMPLETO!")
    
    # Análise de velocidade
    cache_speedup = (max(times) / min(times))
    print(f"\n🚀 GANHO DE VELOCIDADE:")
    print(f"  • Cache vs LLM: ~{cache_speedup:.0f}x mais rápido")
    print(f"  • LLM: ~{max(times):.2f}s")
    print(f"  • Cache: ~{min(times)*1000:.1f}ms")


def test_multiple_documents():
    """
    Teste com múltiplos documentos do dataset
    """
    print_separator("📚 TESTE COM MÚLTIPLOS DOCUMENTOS")
    
    extractor = CachedLLMExtractor()
    
    with open(DATASET_PATH, "r") as f:
        dataset = json.load(f)
    
    # Processa até 3 documentos
    for idx, item in enumerate(dataset[:3], 1):
        print(f"\n\n{'─'*80}")
        print(f"📄 DOCUMENTO {idx}/{min(3, len(dataset))}: {item['pdf_path']}")
        print('─'*80)
        
        with open(os.path.join(PDF_PATH, item["pdf_path"]), "rb") as f:
            pdf_bytes = f.read()
        
        # Primeira chamada
        print("\n1️⃣  Primeira extração:")
        result1 = extractor.extract(pdf_bytes, item["label"], item["extraction_schema"])
        
        # Segunda chamada (deve vir do cache)
        print("\n2️⃣  Segunda extração (mesmos parâmetros):")
        result2 = extractor.extract(pdf_bytes, item["label"], item["extraction_schema"])
    
    # Estatísticas finais
    print_separator("📊 ESTATÍSTICAS CONSOLIDADAS")
    stats = extractor.get_stats()
    
    print(f"\n✅ Processados: 3 documentos")
    print(f"📊 Total de requisições: {stats['total_requests']}")
    print(f"🎯 Hit rate: {stats['hit_rates']['overall']}")
    print(f"💰 Tempo economizado: {stats['savings']['time_saved_seconds']:.2f}s")


if __name__ == "__main__":
    # Executa teste principal
    test_cache_performance()
    
    print("\n\n")
    
    # Executa teste com múltiplos documentos
    # Descomente para executar:
    # test_multiple_documents()

