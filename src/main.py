#!/usr/bin/env python3
"""
BACKEND API - Sistema de Extração de Dados de PDFs

Endpoints:
- POST /extract → Extração de dados de um único PDF
- POST /extract-batch → Extração de múltiplos PDFs em paralelo
- GET /health → Status da API
- GET /stats → Estatísticas de cache e templates
"""

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
import json
import tempfile
import os
import time
import uvicorn
import asyncio
from concurrent.futures import ProcessPoolExecutor, as_completed

# Imports da pipeline
from src.pipeline import ExtractionPipeline

# ==================== CONFIGURAÇÃO ====================

app = FastAPI(
    title="PDF Data Extraction API",
    description="API para extração estruturada de dados de PDFs com cache, template learning e processamento em batch",
    version="2.0.0"
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


class BatchExtractResponse(BaseModel):
    """Modelo de resposta da extração em batch"""
    success: bool
    total_files: int
    successful: int
    failed: int
    results: List[Dict[str, Any]]
    processing_time_seconds: float
    metadata: Dict[str, Any]


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


@app.post("/extract-batch")
async def extract_batch(
    files: List[UploadFile] = File(..., description="Lista de arquivos PDF para extração"),
    label: str = Form(..., description="Tipo do documento (mesmo para todos os PDFs)"),
    extraction_schema: str = Form(..., description="JSON com schema de campos a extrair (mesmo para todos)")
):
    """
    Extrai dados de múltiplos PDFs em batch com streaming progressivo
    
    **Parâmetros:**
    - `files`: Lista de arquivos PDF (multipart/form-data)
    - `label`: Tipo do documento (ex: 'carteira_oab', 'tela_sistema')
    - `extraction_schema`: Schema em JSON (mesmo do endpoint /extract)
    
    **Exemplo de extraction_schema:**
    ```json
    {
        "nome": "Nome do profissional",
        "cpf": "CPF no formato XXX.XXX.XXX-XX",
        "data_nascimento": "Data de nascimento"
    }
    ```
    
    **Características:**
    - ✅ **Streaming progressivo**: Retorna cada resultado assim que processa
    - ✅ **Server-Sent Events (SSE)**: Cliente recebe atualizações em tempo real
    - ✅ Processamento sequencial para template learning efetivo
    - ✅ Estatísticas finais após processar todos os arquivos
    - ✅ Falhas individuais não param o batch
    
    **Formato da Resposta (SSE):**
    
    Evento 1 (arquivo processado):
    ```
    event: result
    data: {"file_index": 0, "filename": "doc.pdf", "success": true, "data": {...}}
    ```
    
    Evento 2 (arquivo processado):
    ```
    event: result
    data: {"file_index": 1, "filename": "doc2.pdf", "success": true, "data": {...}}
    ```
    
    Evento final (estatísticas):
    ```
    event: complete
    data: {"total_files": 2, "successful": 2, "failed": 0, "metadata": {...}}
    ```
    
    **Observação:** Todos os PDFs devem ser do mesmo tipo (mesmo label/schema).
    Para processar PDFs de tipos diferentes, faça requisições separadas.
    """
    
    # Valida parâmetros antes de iniciar streaming
    try:
        # Valida que há pelo menos 1 arquivo
        if not files or len(files) == 0:
            raise HTTPException(
                status_code=400,
                detail="Nenhum arquivo foi enviado"
            )
        
        # Parse schema
        try:
            schema = json.loads(extraction_schema)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400,
                detail="extraction_schema deve ser um JSON válido"
            )
        
        if not isinstance(schema, dict):
            raise HTTPException(
                status_code=400,
                detail="extraction_schema deve ser um objeto JSON"
            )
        
        # Valida e salva arquivos temporariamente
        temp_files = []
        filenames = []
        
        for i, file in enumerate(files):
            # Valida tipo de arquivo
            if not file.filename.lower().endswith('.pdf'):
                raise HTTPException(
                    status_code=400,
                    detail=f"Arquivo {i} ({file.filename}) não é um PDF"
                )
            
            content = await file.read()
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            temp_file.write(content)
            temp_file.close()
            temp_files.append(temp_file.name)
            filenames.append(file.filename)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao processar arquivos: {str(e)}"
        )
    
    # Generator para streaming
    async def generate_results():
        start_time = time.time()
        successful = 0
        failed = 0
        methods_used = {}
        total_extraction_time = 0
        
        try:
            # Processa cada PDF sequencialmente
            for i, temp_file_path in enumerate(temp_files):
                try:
                    with open(temp_file_path, "rb") as f:
                        pdf_bytes = f.read()
                    
                    # Usa a pipeline global
                    result = pipeline.extract(pdf_bytes, label, schema)
                    
                    # Separa dados de metadata
                    data = {k: v for k, v in result.items() if not k.startswith("_")}
                    
                    method = result.get("_pipeline", {}).get("method", "unknown")
                    extraction_time = result.get("_pipeline", {}).get("time", 0)
                    
                    # Prepara resultado
                    result_data = {
                        "file_index": i,
                        "filename": filenames[i],
                        "success": True,
                        "data": data,
                        "metadata": {
                            "method": method,
                            "time": extraction_time,
                            "pipeline_info": result.get("_pipeline", {}),
                            "cache_info": result.get("_cache", {})
                        }
                    }
                    
                    # Envia evento SSE
                    yield f"event: result\n"
                    yield f"data: {json.dumps(result_data, ensure_ascii=False)}\n\n"
                    
                    successful += 1
                    methods_used[method] = methods_used.get(method, 0) + 1
                    total_extraction_time += extraction_time
                
                except Exception as e:
                    # Erro ao processar arquivo individual
                    error_data = {
                        "file_index": i,
                        "filename": filenames[i],
                        "success": False,
                        "error": str(e),
                        "metadata": {}
                    }
                    
                    yield f"event: result\n"
                    yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
                    
                    failed += 1
            
            # Limpa arquivos temporários
            for temp_file in temp_files:
                try:
                    os.unlink(temp_file)
                except:
                    pass
            
            # Calcula estatísticas finais
            processing_time = time.time() - start_time
            
            final_data = {
                "total_files": len(temp_files),
                "successful": successful,
                "failed": failed,
                "processing_time_seconds": round(processing_time, 3),
                "metadata": {
                    "label": label,
                    "methods_used": methods_used,
                    "avg_time_per_file": round(processing_time / len(temp_files), 3) if temp_files else 0,
                    "total_extraction_time": round(total_extraction_time, 3),
                    "overhead_time": round(processing_time - total_extraction_time, 3)
                }
            }
            
            # Envia evento de conclusão
            yield f"event: complete\n"
            yield f"data: {json.dumps(final_data, ensure_ascii=False)}\n\n"
        
        except Exception as e:
            # Erro geral durante processamento
            error_final = {
                "error": f"Erro durante processamento: {str(e)}",
                "total_files": len(temp_files),
                "successful": successful,
                "failed": failed
            }
            
            yield f"event: error\n"
            yield f"data: {json.dumps(error_final, ensure_ascii=False)}\n\n"
            
            # Limpa arquivos temporários
            for temp_file in temp_files:
                try:
                    os.unlink(temp_file)
                except:
                    pass
    
    # Retorna streaming response
    return StreamingResponse(
        generate_results(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"  # Desabilita buffering do nginx
        }
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

