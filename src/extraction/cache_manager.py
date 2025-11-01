import hashlib
import json
from typing import Dict, Optional, Any
from functools import lru_cache
from diskcache import Cache
import time

class CacheManager:
    "Sistema de cache para extração de dados de PDFs"

    def __init__(self, cache_dir: str = r"src/storage/cache_data"):
        self.memory_cache = {}
        self.memory_cache_max_size = 100

        self.disk_cache = Cache(cache_dir)

        self.stats = {
            "l1_hits": 0,
            "l2_hits": 0,
            "l3_hits": 0,
            "misses": 0,
            "total_requests": 0,
        }

    def generate_key(self, pdf_bytes: bytes, label: str, schema: Dict[str, str]) -> str:
        "Gera uma chave única para cada PDF"

        # Hash PDF
        pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()

        # Hash Label
        label_hash = hashlib.sha256(label.encode()).hexdigest()

        # Hash Schema
        schema_str = json.dumps(schema, sort_keys=True)
        schema_hash = hashlib.sha256(schema_str.encode()).hexdigest()

        combined_hash = f"{pdf_hash}:{label_hash}:{schema_hash}"
        final_hash = hashlib.sha256(combined_hash.encode()).hexdigest()

        return final_hash

    