#!/usr/bin/env python3
"""
BACKEND API - Sistema de Extração de Dados de PDFs

Endpoints:
- POST /extract → Extração de dados de PDF
- GET /health → Status da API
- GET /stats → Estatísticas de cache e templates

Metas:
- Acurácia ≥80%
- Tempo <10s por requisição
- Cache máximo para reduzir custos
"""

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
import json
import tempfile
import os
import time
import uvicorn

# Imports da pipeline
from src.extraction.llm import LLM
from src.cache.cache_manager import CacheManager
from src.template.template_manager import TemplateManager

# ==================== CONFIGURAÇÃO ====================

app = FastAPI(
    title="PDF Data Extraction API",
    description="API para extração estruturada de dados de PDFs com cache e template learning",
    version="1.0.0"
)

# CORS (permite chamadas do frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== PIPELINE SINGLETON ====================

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
            
            if should_use:
                # USA TEMPLATE
                template_start = time.time()
                result = self.template_manager.extract_with_template(template_id, elements_data)
                template_time = time.time() - template_start
                
                self.stats["template_hits"] += 1
                
                # Armazena no cache
                self.cache.set(pdf_bytes, label, schema, result, 
                             metadata={"method": "template", "time": template_time})
                
                result["_pipeline"] = {
                    "method": "template",
                    "similarity": round(similarity * 100, 1),
                    "time": template_time
                }
                
                return result
            
            # STEP 3: LLM
            llm_start = time.time()
            prompt = self.llm.generate_prompt(label, schema)
            result_json = self.llm.extract_data(tmp_path, prompt)
            llm_time = time.time() - llm_start
            
            self.stats["llm_calls"] += 1
            self.stats["llm_time"] = self.stats.get("llm_time", 0) + llm_time
            
            # Parse
            try:
                result = json.loads(result_json)
            except json.JSONDecodeError:
                result = {field: None for field in schema.keys()}
            
            # STEP 4: Learning
            self.template_manager.learn_from_extraction(
                pdf_path=tmp_path,
                label=label,
                schema=schema,
                extracted_data=result,
                elements=elements_data,
                extraction_time=llm_time
            )
            
            # STEP 5: Cache Storage
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


# Inicializa pipeline
pipeline = ExtractionPipeline()


# ==================== MODELS ====================

class ExtractResponse(BaseModel):
    """Modelo de resposta da extração"""
    success: bool
    data: Dict[str, Any]
    metadata: Dict[str, Any] = Field(
        description="Metadata sobre a extração (método, tempo, etc)"
    )


class HealthResponse(BaseModel):
    """Modelo de resposta do health check"""
    status: str
    version: str
    uptime_seconds: float
    components: Dict[str, str]


# ==================== ENDPOINTS ====================

@app.post("/extract", response_model=ExtractResponse)
async def extract_data(
    file: UploadFile = File(..., description="Arquivo PDF para extração"),
    label: str = Form(..., description="Tipo do documento (ex: 'carteira_oab', 'tela_sistema')"),
    extraction_schema: str = Form(..., description="JSON com schema de campos a extrair")
):
    """
    Extrai dados estruturados de um PDF
    
    **Parâmetros:**
    - `file`: Arquivo PDF (multipart/form-data)
    - `label`: Tipo do documento
    - `extraction_schema`: Schema em JSON (chave: nome do campo, valor: descrição)
    
    **Exemplo de extraction_schema:**
    ```json
    {
        "nome": "Nome do profissional",
        "cpf": "CPF no formato XXX.XXX.XXX-XX",
        "data_nascimento": "Data de nascimento"
    }
    ```
    
    **Resposta:**
    - `success`: True/False
    - `data`: Dados extraídos (JSON)
    - `metadata`: Informações sobre a extração (método usado, tempo, etc)
    
    **Pipeline:**
    1. Verifica cache (L1 Memory → L2 Disk → L3 Partial)
    2. Se cache miss, verifica template aprendido
    3. Se template não aplicável, usa LLM
    4. Aprende padrões do resultado
    5. Armazena no cache para futuras requisições
    """
    
    start_time = time.time()
    
    try:
        # Valida tipo de arquivo
        if not file.filename.endswith('.pdf'):
            raise HTTPException(
                status_code=400,
                detail="Arquivo deve ser um PDF (.pdf)"
            )
        
        # Lê PDF
        pdf_bytes = await file.read()
        
        if len(pdf_bytes) == 0:
            raise HTTPException(
                status_code=400,
                detail="Arquivo PDF está vazio"
            )
        
        # Parse schema
        try:
            schema_dict = json.loads(extraction_schema)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400,
                detail="extraction_schema deve ser um JSON válido"
            )
        
        if not isinstance(schema_dict, dict):
            raise HTTPException(
                status_code=400,
                detail="extraction_schema deve ser um objeto JSON (dict)"
            )
        
        # Extrai usando pipeline
        result = pipeline.extract(
            pdf_bytes=pdf_bytes,
            label=label,
            schema=schema_dict
        )
        
        # Separa dados de metadata
        data = {k: v for k, v in result.items() if not k.startswith("_")}
        metadata = {
            "method": result.get("_pipeline", {}).get("method", "unknown"),
            "time_seconds": round(time.time() - start_time, 3),
            "pipeline_info": result.get("_pipeline", {}),
            "cache_info": result.get("_cache", {})
        }
        
        return ExtractResponse(
            success=True,
            data=data,
            metadata=metadata
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro durante extração: {str(e)}"
        )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check da API
    
    Retorna:
    - Status da API
    - Versão
    - Uptime
    - Status dos componentes (LLM, Cache, Templates)
    """
    
    uptime = time.time() - pipeline.stats["start_time"]
    
    # Verifica componentes
    components = {
        "llm": "ok",
        "cache": "ok",
        "template_db": "ok"
    }
    
    # Testa LLM (básico)
    try:
        _ = pipeline.llm.model
    except:
        components["llm"] = "error"
    
    # Testa cache
    try:
        _ = pipeline.cache.stats
    except:
        components["cache"] = "error"
    
    # Testa template DB
    try:
        _ = pipeline.template_manager.db
    except:
        components["template_db"] = "error"
    
    all_ok = all(status == "ok" for status in components.values())
    
    return HealthResponse(
        status="healthy" if all_ok else "degraded",
        version="1.0.0",
        uptime_seconds=round(uptime, 2),
        components=components
    )


@app.get("/stats")
async def get_stats():
    """
    Retorna estatísticas detalhadas da pipeline
    
    Inclui:
    - Estatísticas de requisições (cache hits, template hits, LLM calls)
    - Performance (tempos médios)
    - Cache (L1/L2/L3 hits, tamanho)
    - Templates (total aprendidos, por label)
    """
    
    try:
        stats = pipeline.get_stats()
        return JSONResponse(content=stats)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao obter estatísticas: {str(e)}"
        )


@app.get("/")
async def root():
    """
    Endpoint raiz - informações básicas da API
    """
    return {
        "name": "PDF Data Extraction API",
        "version": "1.0.0",
        "endpoints": {
            "extract": "POST /extract - Extrai dados de PDF",
            "health": "GET /health - Status da API",
            "stats": "GET /stats - Estatísticas detalhadas",
            "docs": "GET /docs - Documentação interativa (Swagger)"
        },
        "documentation": "/docs"
    }


# ==================== STARTUP/SHUTDOWN ====================

@app.on_event("startup")
async def startup_event():
    """Executado ao iniciar a API"""
    print("="*80)
    print("🚀 PDF Data Extraction API - Starting...")
    print("="*80)
    print(f"\n✅ LLM initialized: {pipeline.llm.model}")
    print(f"✅ Cache initialized")
    print(f"✅ Template Manager initialized")
    print(f"\n🌐 API ready!")
    print(f"📖 Docs: http://localhost:8000/docs")
    print("="*80 + "\n")


@app.on_event("shutdown")
async def shutdown_event():
    """Executado ao encerrar a API"""
    print("\n" + "="*80)
    print("📊 ESTATÍSTICAS FINAIS:")
    print("="*80)
    
    stats = pipeline.get_stats()
    print(f"\n• Total de requisições: {stats['requests']['total']}")
    print(f"• Cache hits: {stats['requests']['cache_hits']}")
    print(f"• LLM calls: {stats['requests']['llm_calls']}")
    print(f"• Cache hit rate: {stats['performance']['cache_hit_rate']}")
    print(f"\n👋 API encerrada.")
    print("="*80)


# ==================== RUN ====================

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True, 
        log_level="info"
    )

