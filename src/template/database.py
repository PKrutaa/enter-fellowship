# app/template/database.py

import sqlite3
from typing import Optional, Dict, Any, List
import json
from contextlib import contextmanager

class TemplateDatabase:
    """
    Banco de dados para armazenar templates aprendidos
    
    Estrutura:
    - templates: Metadados do template (label, versão, confiança)
    - template_texts: Texto de referência de cada template
    - field_patterns: Padrões aprendidos para cada campo
    - extraction_history: Histórico de extrações para análise
    """
    
    def __init__(self, db_path: str = "./storage/templates.db"):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Cria tabelas se não existirem"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Tabela de templates
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    label TEXT NOT NULL,
                    version INTEGER DEFAULT 1,
                    document_type TEXT,  -- 'rigid' ou 'flexible'
                    confidence REAL DEFAULT 0.0,
                    sample_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(label, version)
                )
            """)
            
            # Tabela de textos de referência
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS template_texts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    template_id INTEGER,
                    reference_text TEXT NOT NULL,
                    text_hash TEXT NOT NULL,
                    FOREIGN KEY (template_id) REFERENCES templates(id)
                )
            """)
            
            # Tabela de padrões de campos
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS field_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    template_id INTEGER,
                    field_name TEXT NOT NULL,
                    field_description TEXT,
                    extraction_method TEXT,  -- 'position', 'regex', 'context'
                    pattern_data TEXT,  -- JSON com detalhes do padrão
                    confidence REAL DEFAULT 0.0,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    FOREIGN KEY (template_id) REFERENCES templates(id)
                )
            """)
            
            # Tabela de histórico
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS extraction_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    template_id INTEGER,
                    pdf_hash TEXT,
                    extraction_time REAL,
                    success BOOLEAN,
                    method_used TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (template_id) REFERENCES templates(id)
                )
            """)
            
            # Índices para performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_label ON templates(label)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_field_name ON field_patterns(field_name)")
            
            conn.commit()
    
    @contextmanager
    def _get_connection(self):
        """Context manager para conexões"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Permite acessar por nome
        try:
            yield conn
        finally:
            conn.close()
    
    def create_template(
        self,
        label: str,
        document_type: str,
        reference_text: str,
        text_hash: str
    ) -> int:
        """Cria novo template"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Insere template
            cursor.execute("""
                INSERT INTO templates (label, document_type, sample_count)
                VALUES (?, ?, 1)
            """, (label, document_type))
            
            template_id = cursor.lastrowid
            
            # Insere texto de referência
            cursor.execute("""
                INSERT INTO template_texts (template_id, reference_text, text_hash)
                VALUES (?, ?, ?)
            """, (template_id, reference_text, text_hash))
            
            conn.commit()
            return template_id
    
    def get_template(self, label: str) -> Optional[Dict[str, Any]]:
        """Busca template por label (versão mais recente)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM templates
                WHERE label = ?
                ORDER BY version DESC, updated_at DESC
                LIMIT 1
            """, (label,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            return dict(row)
    
    def add_field_pattern(
        self,
        template_id: int,
        field_name: str,
        field_description: str,
        extraction_method: str,
        pattern_data: Dict[str, Any],
        confidence: float = 0.8
    ):
        """Adiciona padrão de campo ao template"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO field_patterns 
                (template_id, field_name, field_description, extraction_method, 
                 pattern_data, confidence, success_count)
                VALUES (?, ?, ?, ?, ?, ?, 1)
            """, (
                template_id,
                field_name,
                field_description,
                extraction_method,
                json.dumps(pattern_data),
                confidence
            ))
            
            conn.commit()
    
    def get_field_patterns(self, template_id: int) -> List[Dict[str, Any]]:
        """Retorna todos os padrões de um template"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM field_patterns
                WHERE template_id = ?
                ORDER BY confidence DESC
            """, (template_id,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def update_pattern_success(self, pattern_id: int, success: bool):
        """Atualiza estatísticas de sucesso de um padrão"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if success:
                cursor.execute("""
                    UPDATE field_patterns
                    SET success_count = success_count + 1,
                        confidence = CASE
                            WHEN confidence < 0.95 THEN confidence + 0.01
                            ELSE confidence
                        END
                    WHERE id = ?
                """, (pattern_id,))
            else:
                cursor.execute("""
                    UPDATE field_patterns
                    SET failure_count = failure_count + 1,
                        confidence = CASE
                            WHEN confidence > 0.3 THEN confidence - 0.05
                            ELSE confidence
                        END
                    WHERE id = ?
                """, (pattern_id,))
            
            conn.commit()
    
    def increment_sample_count(self, template_id: int):
        """Incrementa contador de amostras do template"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE templates
                SET sample_count = sample_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (template_id,))
            
            conn.commit()