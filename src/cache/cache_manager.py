# app/cache/cache_manager.py

import time
from typing import Optional, Dict, Any, List
from collections import OrderedDict
from diskcache import Cache
from .cache_key import CacheKeyGenerator
import json

class CacheManager:
    """
    Sistema de cache multi-level para extração de PDFs
    
    Arquitetura:
    - L1: Memory Cache (LRU) - 100 itens, ~10MB RAM
    - L2: Disk Cache (DiskCache) - Ilimitado, persistente
    - L3: Field Cache - Para partial schema matching
    
    Performance esperada:
    - L1 Hit: <0.001s
    - L2 Hit: 0.01-0.05s
    - L3 Hit: 0.05-0.1s
    - Miss: 3-8s (LLM call)
    """
    
    def __init__(
        self,
        cache_dir: str = "./cache_data",
        memory_size: int = 100,
        disk_size_limit: int = 1024**3  # 1GB
    ):
        """
        Inicializa o cache manager
        
        Args:
            cache_dir: Diretório para disk cache
            memory_size: Número de itens no L1
            disk_size_limit: Tamanho máximo do L2 em bytes
        """
        # L1: Memory Cache (OrderedDict para LRU)
        self.memory_cache: OrderedDict = OrderedDict()
        self.memory_size = memory_size
        
        # L2: Disk Cache
        self.disk_cache = Cache(
            cache_dir,
            size_limit=disk_size_limit,
            eviction_policy='least-recently-used'
        )
        
        # Gerador de keys
        self.key_gen = CacheKeyGenerator()
        
        # Estatísticas
        self.stats = {
            "l1_hits": 0,
            "l2_hits": 0,
            "l3_hits": 0,
            "misses": 0,
            "total_requests": 0,
            "total_time_saved": 0.0,  # segundos economizados
            "total_cost_saved": 0.0   # $ economizados
        }
    
    def get(
        self,
        pdf_bytes: bytes,
        label: str,
        schema: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """
        Busca no cache (L1 → L2 → L3)
        
        Returns:
            Dict com resultado + metadata se encontrado
            None se cache miss
        """
        start_time = time.time()
        self.stats["total_requests"] += 1
        
        # Gera chave
        full_key = self.key_gen.generate_full_key(pdf_bytes, label, schema)
        
        # ========== L1: MEMORY CACHE ==========
        if full_key in self.memory_cache:
            result = self.memory_cache[full_key]
            
            # Move para o final (LRU)
            self.memory_cache.move_to_end(full_key)
            
            self.stats["l1_hits"] += 1
            elapsed = time.time() - start_time
            
            return self._prepare_result(
                result,
                cache_source="L1_MEMORY",
                cache_time=elapsed
            )
        
        # ========== L2: DISK CACHE ==========
        disk_result = self.disk_cache.get(full_key)
        if disk_result is not None:
            # Promove para L1
            self._add_to_memory_cache(full_key, disk_result)
            
            self.stats["l2_hits"] += 1
            elapsed = time.time() - start_time
            
            return self._prepare_result(
                disk_result,
                cache_source="L2_DISK",
                cache_time=elapsed
            )
        
        # ========== L3: PARTIAL SCHEMA MATCH ==========
        partial_result = self._try_partial_match(pdf_bytes, label, schema)
        if partial_result:
            self.stats["l3_hits"] += 1
            elapsed = time.time() - start_time
            
            return self._prepare_result(
                partial_result,
                cache_source="L3_PARTIAL",
                cache_time=elapsed,
                is_partial=True
            )
        
        # ========== CACHE MISS ==========
        self.stats["misses"] += 1
        return None
    
    def set(
        self,
        pdf_bytes: bytes,
        label: str,
        schema: Dict[str, str],
        result: Dict[str, Any],
        metadata: Optional[Dict] = None
    ):
        """
        Armazena no cache (L1 + L2 + field-level)
        """
        full_key = self.key_gen.generate_full_key(pdf_bytes, label, schema)
        
        cache_entry = {
            "result": result,
            "label": label,
            "schema": schema,
            "timestamp": time.time(),
            "metadata": metadata or {}
        }
        
        # Armazena em L1
        self._add_to_memory_cache(full_key, cache_entry)
        
        # Armazena em L2
        self.disk_cache.set(full_key, cache_entry)
        
        # Armazena fields individuais (para L3)
        self._store_fields(pdf_bytes, label, schema, result)
        
        # Atualiza estatísticas de economia
        if metadata:
            self.stats["total_time_saved"] += metadata.get("time_saved", 0)
            self.stats["total_cost_saved"] += metadata.get("cost_saved", 0)
    
    def _add_to_memory_cache(self, key: str, value: Any):
        """
        Adiciona ao cache L1 com política LRU
        """
        # Remove mais antigo se necessário
        if len(self.memory_cache) >= self.memory_size:
            # Remove o primeiro (mais antigo)
            self.memory_cache.popitem(last=False)
        
        # Adiciona no final
        self.memory_cache[key] = value
    
    def _try_partial_match(
        self,
        pdf_bytes: bytes,
        label: str,
        schema: Dict[str, str]
    ) -> Optional[Dict]:
        """
        Tenta encontrar match parcial do schema
        
        Cenário:
        - Cache tem campos {A, B, C} extraídos
        - Request pede campos {A, B, D}
        - Retorna: {A: valor, B: valor, D: None, _needs_extraction: ['D']}
        
        Isso permite extrair só o campo D com LLM!
        """
        result = {}
        found_fields = []
        missing_fields = []
        
        # Para cada campo solicitado, busca no field cache
        for field_name, field_description in schema.items():
            field_key = self.key_gen.generate_field_key(
                pdf_bytes, label, field_name
            )
            
            cached_field = self.disk_cache.get(field_key)
            
            if cached_field:
                result[field_name] = cached_field["value"]
                found_fields.append(field_name)
            else:
                result[field_name] = None
                missing_fields.append(field_name)
        
        # Só retorna se encontrou pelo menos 50% dos campos
        match_rate = len(found_fields) / len(schema) if schema else 0
        
        if match_rate >= 0.5:
            return {
                "result": result,
                "found_fields": found_fields,
                "missing_fields": missing_fields,
                "match_rate": match_rate,
                "label": label,
                "schema": schema,
                "timestamp": time.time()
            }
        
        return None
    
    def _store_fields(
        self,
        pdf_bytes: bytes,
        label: str,
        schema: Dict[str, str],
        result: Dict[str, Any]
    ):
        """
        Armazena cada campo individualmente para partial matching
        """
        for field_name, field_value in result.items():
            # Ignora campos null e metadata
            if field_value is None or field_name.startswith("_"):
                continue
            
            field_key = self.key_gen.generate_field_key(
                pdf_bytes, label, field_name
            )
            
            field_entry = {
                "value": field_value,
                "description": schema.get(field_name, ""),
                "timestamp": time.time()
            }
            
            self.disk_cache.set(field_key, field_entry)
    
    def _prepare_result(
        self,
        cache_entry: Dict,
        cache_source: str,
        cache_time: float,
        is_partial: bool = False
    ) -> Dict[str, Any]:
        """
        Prepara resultado do cache com metadata
        """
        result = cache_entry["result"].copy()
        
        # Adiciona metadata do cache
        result["_cache"] = {
            "hit": True,
            "source": cache_source,
            "cached_at": cache_entry.get("timestamp"),
            "age_seconds": time.time() - cache_entry.get("timestamp", time.time()),
            "retrieval_time": cache_time,
            "is_partial": is_partial
        }
        
        # Se é partial match, adiciona info sobre campos faltantes
        if is_partial:
            result["_cache"]["found_fields"] = cache_entry.get("found_fields", [])
            result["_cache"]["missing_fields"] = cache_entry.get("missing_fields", [])
            result["_cache"]["match_rate"] = cache_entry.get("match_rate", 0)
        
        return result
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Retorna estatísticas detalhadas do cache
        """
        total = self.stats["total_requests"]
        
        if total == 0:
            hit_rate = 0
            l1_rate = 0
            l2_rate = 0
            l3_rate = 0
        else:
            total_hits = (
                self.stats["l1_hits"] + 
                self.stats["l2_hits"] + 
                self.stats["l3_hits"]
            )
            hit_rate = (total_hits / total) * 100
            l1_rate = (self.stats["l1_hits"] / total) * 100
            l2_rate = (self.stats["l2_hits"] / total) * 100
            l3_rate = (self.stats["l3_hits"] / total) * 100
        
        return {
            "total_requests": total,
            "cache_hits": {
                "l1_memory": self.stats["l1_hits"],
                "l2_disk": self.stats["l2_hits"],
                "l3_partial": self.stats["l3_hits"],
                "total": self.stats["l1_hits"] + self.stats["l2_hits"] + self.stats["l3_hits"]
            },
            "cache_misses": self.stats["misses"],
            "hit_rates": {
                "overall": f"{hit_rate:.2f}%",
                "l1": f"{l1_rate:.2f}%",
                "l2": f"{l2_rate:.2f}%",
                "l3": f"{l3_rate:.2f}%"
            },
            "cache_sizes": {
                "memory_items": len(self.memory_cache),
                "memory_max": self.memory_size,
                "disk_items": len(self.disk_cache),
                "disk_size_mb": self.disk_cache.volume() / (1024**2)
            },
            "savings": {
                "time_saved_seconds": round(self.stats["total_time_saved"], 2),
                "cost_saved_dollars": round(self.stats["total_cost_saved"], 4),
                "avg_time_per_hit": round(
                    self.stats["total_time_saved"] / max(1, self.stats["l1_hits"] + self.stats["l2_hits"]),
                    3
                )
            }
        }
    
    def clear_all(self):
        """Limpa todos os caches"""
        self.memory_cache.clear()
        self.disk_cache.clear()
        self.stats = {
            "l1_hits": 0,
            "l2_hits": 0,
            "l3_hits": 0,
            "misses": 0,
            "total_requests": 0,
            "total_time_saved": 0.0,
            "total_cost_saved": 0.0
        }
    
    def clear_memory_only(self):
        """Limpa apenas L1 (útil para testes)"""
        self.memory_cache.clear()
    
    def invalidate_pdf(self, pdf_bytes: bytes):
        """
        Remove todas as entradas relacionadas a um PDF específico
        
        Útil se você detectar que um PDF foi processado incorretamente
        """
        pdf_hash = self.key_gen._hash_pdf(pdf_bytes)
        
        # Remove do memory cache
        keys_to_remove = [
            k for k in self.memory_cache.keys() 
            if k.startswith(pdf_hash)
        ]
        for key in keys_to_remove:
            del self.memory_cache[key]
        
        # Remove do disk cache (mais complexo, precisa iterar)
        # Por simplicidade, não implementado aqui
        # Em produção, você poderia manter um índice
    
    def get_cached_labels(self) -> List[str]:
        """
        Retorna lista de labels que têm dados em cache
        """
        labels = set()
        
        for key in self.disk_cache.iterkeys():
            parsed = self.key_gen.parse_key(key)
            if "label" in parsed:
                labels.add(parsed["label"])
        
        return sorted(list(labels))