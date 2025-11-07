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
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from queue import Queue
import threading

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
    labels: List[str] = Form(..., description="Label para cada arquivo (na mesma ordem dos files)"),
    schemas: List[str] = Form(..., description="JSON schema para cada arquivo (na mesma ordem dos files)")
):
    """
    Extrai dados de múltiplos PDFs em batch com paralelização por label
    
    **Parâmetros:**
    - `files`: Lista de arquivos PDF (multipart/form-data)
    - `labels`: Lista de labels (um para cada arquivo, na mesma ordem)
    - `schemas`: Lista de schemas JSON (um para cada arquivo, na mesma ordem)
    
    **Exemplo de request (JavaScript):**
    ```javascript
    const formData = new FormData();
    
    // Arquivo 1: carteira_oab
    formData.append('files', oab1File, 'oab_1.pdf');
    formData.append('labels', 'carteira_oab');
    formData.append('schemas', JSON.stringify({"nome": "Nome completo"}));
    
    // Arquivo 2: tela_sistema
    formData.append('files', tela1File, 'tela_1.pdf');
    formData.append('labels', 'tela_sistema');
    formData.append('schemas', JSON.stringify({"sistema": "Nome do sistema"}));
    
    fetch('/extract-batch', {method: 'POST', body: formData})
    ```
    
    **Características:**
    - ✅ **Cada arquivo pode ter label/schema diferente**
    - ✅ **Paralelização por label**: Labels diferentes processam em paralelo
    - ✅ **Template learning**: Arquivos do mesmo label processam sequencialmente
    - ✅ **Streaming progressivo**: Resultados chegam via SSE conforme processam
    - ✅ **Falhas individuais não param o batch**
    
    **Formato da Resposta (SSE):**
    
    Evento (por arquivo processado):
    ```
    event: result
    data: {"index": 0, "filename": "oab_1.pdf", "label": "carteira_oab", 
           "success": true, "data": {...}, "metadata": {...}}
    ```
    
    Evento final:
    ```
    event: complete
    data: {"total_files": 3, "successful": 3, "failed": 0, 
           "processing_time_seconds": 5.2, "metadata": {...}}
    ```
    """
    
    # Valida parâmetros antes de iniciar streaming
    try:
        # Valida que há pelo menos 1 arquivo
        if not files or len(files) == 0:
            raise HTTPException(
                status_code=400,
                detail="Nenhum arquivo foi enviado"
            )
        
        # Valida que arrays têm mesmo tamanho
        if not (len(files) == len(labels) == len(schemas)):
            raise HTTPException(
                status_code=400,
                detail=f"files ({len(files)}), labels ({len(labels)}) e schemas ({len(schemas)}) devem ter o mesmo tamanho"
            )
        
        # Parse cada schema JSON
        parsed_schemas = []
        for i, schema_str in enumerate(schemas):
            try:
                parsed_schema = json.loads(schema_str)
                if not isinstance(parsed_schema, dict):
                    raise ValueError("Schema deve ser um objeto JSON")
                parsed_schemas.append(parsed_schema)
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Schema {i} inválido: {str(e)}"
                )
        
        # Cria estrutura de itens e salva arquivos temporariamente
        items = []
        for i, (file, label, schema) in enumerate(zip(files, labels, parsed_schemas)):
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
            
            items.append({
                "index": i,
                "filename": file.filename,
                "temp_path": temp_file.name,
                "label": label,
                "schema": schema
            })
        
        # Agrupa por label para processamento paralelo
        grouped = defaultdict(list)
        for item in items:
            grouped[item["label"]].append(item)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao processar request: {str(e)}"
        )
    
    # Função worker para processar grupo de label com streaming progressivo
    def process_label_group_worker(label, group_items, result_queue):
        """Processa sequencialmente todos os PDFs de um label, enviando resultados progressivamente"""
        for item in group_items:
            try:
                with open(item["temp_path"], "rb") as f:
                    pdf_bytes = f.read()
                
                # Processa usando pipeline
                result = pipeline.extract(
                    pdf_bytes,
                    item["label"],
                    item["schema"]
                )
                
                # Separa dados de metadata
                data = {k: v for k, v in result.items() if not k.startswith("_")}
                
                result_item = {
                    "index": item["index"],
                    "filename": item["filename"],
                    "label": item["label"],
                    "success": True,
                    "data": data,
                    "metadata": {
                        "method": result.get("_pipeline", {}).get("method", "unknown"),
                        "time": result.get("_pipeline", {}).get("time", 0),
                        "pipeline_info": result.get("_pipeline", {}),
                        "cache_info": result.get("_cache", {})
                    }
                }
                
                # Envia resultado IMEDIATAMENTE para a queue
                result_queue.put(result_item)
            
            except Exception as e:
                error_item = {
                    "index": item["index"],
                    "filename": item["filename"],
                    "label": item["label"],
                    "success": False,
                    "error": str(e),
                    "metadata": {}
                }
                
                # Envia erro IMEDIATAMENTE para a queue
                result_queue.put(error_item)
        
        return len(group_items)  # Retorna apenas o count
    
    # Generator para streaming progressivo
    async def generate_results():
        start_time = time.time()
        successful = 0
        failed = 0
        methods_used = {}
        labels_processed = set()
        
        # Queue thread-safe para comunicação entre workers e SSE
        result_queue = Queue()
        
        # Contador de labels ativas
        total_labels = len(grouped)
        completed_labels = 0
        labels_lock = threading.Lock()
        
        # Função para marcar label como completa
        def mark_label_complete(label):
            nonlocal completed_labels
            with labels_lock:
                completed_labels += 1
                labels_processed.add(label)
                
                # Quando todas as labels terminarem, envia sentinel
                if completed_labels == total_labels:
                    result_queue.put(None)  # Sentinel value
        
        try:
            # Processa labels em paralelo usando ThreadPoolExecutor
            with ThreadPoolExecutor() as executor:
                # Submit tarefas para cada label
                futures = []
                for label, group_items in grouped.items():
                    future = executor.submit(
                        process_label_group_worker,
                        label,
                        group_items,
                        result_queue
                    )
                    futures.append((future, label))
                
                # Thread separada para monitorar conclusão dos futures
                def monitor_futures():
                    for future, label in futures:
                        try:
                            future.result(timeout=300)  # 5 min timeout por label
                            mark_label_complete(label)
                        except (TimeoutError, Exception):
                            mark_label_complete(label)
                
                # Inicia thread de monitoramento
                monitor_thread = threading.Thread(target=monitor_futures, daemon=True)
                monitor_thread.start()
                
                # Consome da queue e envia via SSE PROGRESSIVAMENTE
                while True:
                    # Aguarda próximo resultado (blocking)
                    result_item = result_queue.get()
                    
                    # Sentinel value indica que todos terminaram
                    if result_item is None:
                        break
                    
                    # Envia resultado via SSE IMEDIATAMENTE
                    yield f"event: result\n"
                    yield f"data: {json.dumps(result_item, ensure_ascii=False)}\n\n"
                    
                    # Atualiza estatísticas
                    if result_item["success"]:
                        successful += 1
                        method = result_item["metadata"].get("method", "unknown")
                        methods_used[method] = methods_used.get(method, 0) + 1
                    else:
                        failed += 1
            
            # Limpa arquivos temporários
            for item in items:
                try:
                    os.unlink(item["temp_path"])
                except:
                    pass
            
            # Calcula estatísticas finais
            processing_time = time.time() - start_time
            
            final_data = {
                "total_files": len(items),
                "successful": successful,
                "failed": failed,
                "processing_time_seconds": round(processing_time, 3),
                "metadata": {
                    "labels_processed": sorted(list(labels_processed)),
                    "methods_used": methods_used,
                    "avg_time_per_file": round(processing_time / len(items), 3) if items else 0
                }
            }
            
            # Envia evento de conclusão
            yield f"event: complete\n"
            yield f"data: {json.dumps(final_data, ensure_ascii=False)}\n\n"
        
        except Exception as e:
            # Erro geral durante processamento
            error_final = {
                "error": f"Erro durante processamento: {str(e)}",
                "total_files": len(items),
                "successful": successful,
                "failed": failed
            }
            
            yield f"event: error\n"
            yield f"data: {json.dumps(error_final, ensure_ascii=False)}\n\n"
            
            # Limpa arquivos temporários
            for item in items:
                try:
                    os.unlink(item["temp_path"])
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

