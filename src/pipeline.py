"""
Pipeline de Extração de Dados de PDFs

Classe reutilizável que implementa o fluxo completo:
Cache → Template → LLM → Learning → Storage
"""

import json
import tempfile
import os
import time
from typing import Dict, Any

from src.extraction.llm import LLM
from src.cache.cache_manager import CacheManager
from src.template.template_manager import TemplateManager


class ExtractionPipeline:
    """Pipeline singleton compartilhada entre requests"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.llm = LLM()
        self.cache = CacheManager(cache_dir="./src/storage/cache_data")
        self.template_manager = TemplateManager(db_path="./src/storage/templates.db")
        
        self.stats = {
            "total_requests": 0,
            "cache_hits": 0,
            "template_hits": 0,
            "llm_calls": 0,
            "total_time": 0,
            "start_time": time.time()
        }
        
        self._initialized = True
    
    def extract(
        self,
        pdf_bytes: bytes,
        label: str,
        schema: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Extrai dados usando pipeline completa
        
        Flow: Cache → Template → LLM → Learning → Storage
        """
        request_start = time.time()
        self.stats["total_requests"] += 1
        
        # STEP 1: Cache Check
        cached = self.cache.get(pdf_bytes, label, schema)
        if cached:
            self.stats["cache_hits"] += 1
            cached["_pipeline"] = {
                "method": "cache",
                "cache_source": cached["_cache"]["source"],
                "time": time.time() - request_start
            }
            return cached
        
        # Salva PDF temporário para processamento
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name
        
        try:
            # Estrutura PDF
            elements = self.llm._structure_pdf(tmp_path)
            elements_data = self._extract_elements_data(elements)
            
            # STEP 2: Template Check
            should_use, template_id, similarity = self.template_manager.should_use_template(
                pdf_path=tmp_path,
                label=label,
                elements=elements_data
            )
            
            # PATH A: Template puro (alta confiança >= 90%)
            if should_use and similarity >= 0.90:
                template_start = time.time()
                result = self.template_manager.extract_with_template(template_id, elements_data)
                template_time = time.time() - template_start
                
                method_used = "template"
                total_time = template_time
                self.stats["template_hits"] += 1
                
                # Armazena no cache
                self.cache.set(pdf_bytes, label, schema, result,
                             metadata={"method": method_used, "time": total_time})
                
                result["_pipeline"] = {
                    "method": method_used,
                    "similarity": round(similarity * 100, 1),
                    "time": total_time
                }
                
                return result
            
            # PATH B: LLM com structured outputs
            llm_start = time.time()
            prompt = self.llm.generate_prompt(label, schema)
            result_json = self.llm.extract_data(tmp_path, prompt, schema, label)
            llm_time = time.time() - llm_start
            
            self.stats["llm_calls"] += 1
            self.stats["llm_time"] = self.stats.get("llm_time", 0) + llm_time
            
            # Parse
            try:
                result = json.loads(result_json)
            except json.JSONDecodeError:
                result = {field: None for field in schema.keys()}
            
            # STEP 3: Learning - aprende padrões para futuras extrações
            self.template_manager.learn_from_extraction(
                pdf_path=tmp_path,
                label=label,
                schema=schema,
                extracted_data=result,
                elements=elements_data,
                extraction_time=llm_time
            )
            
            # STEP 4: Cache Storage
            self.cache.set(pdf_bytes, label, schema, result,
                         metadata={"method": "llm", "time": llm_time})
            
            total_time = time.time() - request_start
            self.stats["total_time"] += total_time
            
            result["_pipeline"] = {
                "method": "llm",
                "similarity": round(similarity * 100, 1),
                "time": llm_time,
                "learned": True
            }
            
            return result
        
        finally:
            # Limpa arquivo temporário
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    def _extract_elements_data(self, elements) -> list:
        """Extrai dados dos elementos"""
        elements_data = []
        for elem in elements:
            if elem.text and elem.text.strip():
                x, y = 0, 0
                if hasattr(elem, 'metadata') and elem.metadata:
                    if hasattr(elem.metadata, 'coordinates') and elem.metadata.coordinates:
                        if hasattr(elem.metadata.coordinates, 'points') and elem.metadata.coordinates.points:
                            x, y = elem.metadata.coordinates.points[0]
                
                elements_data.append({
                    'text': elem.text.strip(),
                    'category': elem.category,
                    'x': round(x, 1),
                    'y': round(y, 1)
                })
        return elements_data
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas da pipeline"""
        uptime = time.time() - self.stats["start_time"]
        
        return {
            "uptime_seconds": round(uptime, 2),
            "requests": {
                "total": self.stats["total_requests"],
                "cache_hits": self.stats["cache_hits"],
                "template_hits": self.stats["template_hits"],
                "llm_calls": self.stats["llm_calls"]
            },
            "performance": {
                "avg_llm_time": f"{self.stats.get('llm_time', 0) / max(1, self.stats['llm_calls']):.2f}s",
                "total_time": f"{self.stats['total_time']:.2f}s",
                "cache_hit_rate": f"{self.stats['cache_hits'] / max(1, self.stats['total_requests']) * 100:.1f}%"
            },
            "cache": self.cache.get_stats(),
            "templates": self.template_manager.get_stats()
        }

