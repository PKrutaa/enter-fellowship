# app/template/template_manager.py

import hashlib
import json
import time
from typing import Dict, Any, List, Optional, Tuple
from .database import TemplateDatabase
from .pattern_learner import PatternLearner, FieldPattern
from .template_matcher import TemplateMatcher
from .field_extractor import FieldExtractor

class TemplateManager:
    """
    Orquestrador principal do Template Learning
    
    Fluxo:
    1. Recebe (pdf_path, label, schema)
    2. Verifica se template existe
    3. Se SIM: tenta usar template (rápido)
    4. Se NÃO ou FALHA: usa LLM (fallback)
    5. Aprende padrões do resultado da LLM
    """
    
    # Thresholds - Balanceados para acurácia e velocidade
    RIGID_THRESHOLD = 0.70  # Formulários com estrutura similar (70%+)
    FLEXIBLE_THRESHOLD = 0.60  # Documentos mais flexíveis (60%+)
    MIN_CONFIDENCE = 0.80  # Confiança mínima no template
    MIN_SAMPLES = 2  # Mínimo de 2 amostras para considerar template confiável
    
    def __init__(self, db_path: str = "./src/storage/templates.db"):
        self.db = TemplateDatabase(db_path)
        self.learner = PatternLearner()
        self.matcher = TemplateMatcher()
        self.extractor = FieldExtractor()
    
    def should_use_template(
        self,
        pdf_path: str,
        label: str,
        elements: List[Dict[str, Any]]
    ) -> Tuple[bool, Optional[int], float]:
        """
        Decide se deve usar template ou LLM
        
        IMPORTANTE: Templates são ESPECÍFICOS por label
        - carteira_oab só usa template de carteira_oab
        - tela_sistema só usa template de tela_sistema
        - Labels diferentes NUNCA compartilham templates
        
        Args:
            pdf_path: Path do PDF
            label: Label do documento (ex: 'carteira_oab')
            elements: Elementos estruturados
        
        Returns:
            (should_use, template_id, similarity)
        """
        # CRITICAL: Busca template APENAS para este label específico
        template = self.db.get_template(label)
        
        if not template:
            # Nenhum template aprendido para este label ainda
            return False, None, 0.0
        
        # Calcula similaridade
        text_current = self._elements_to_text(elements)
        text_hash = self._hash_text(text_current)
        
        # Busca texto de referência do template
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT reference_text FROM template_texts
                WHERE template_id = ?
                LIMIT 1
            """, (template['id'],))
            
            row = cursor.fetchone()
            if not row:
                return False, None, 0.0
            
            reference_text = row['reference_text']
        
        # Calcula similaridade
        similarity = self.matcher.calculate_similarity(text_current, reference_text)
        
        template_id = template['id']
        doc_type = template['document_type']
        confidence = template['confidence']
        sample_count = template['sample_count']
        
        # CRITÉRIOS RIGOROSOS para garantir acurácia ≥80%
        
        # 1. Precisa de amostras suficientes
        if sample_count < self.MIN_SAMPLES:
            return False, None, similarity
        
        # 2. Precisa de alta confiança E alta similaridade
        if doc_type == 'rigid':
            # Formulários rígidos: aceita só se MUITO similar
            if similarity >= self.RIGID_THRESHOLD and confidence >= self.MIN_CONFIDENCE:
                return True, template_id, similarity
        
        elif doc_type == 'flexible':
            # Flexíveis: threshold ainda mais alto
            if similarity >= self.FLEXIBLE_THRESHOLD and confidence >= 0.90:
                return True, template_id, similarity
        
        # 3. Fallback: usa LLM (preferir precisão a velocidade)
        return False, None, similarity
    
    def extract_with_template(
        self,
        template_id: int,
        elements: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Extrai usando padrões do template
        
        Returns:
            Dicionário com campos extraídos
        """
        # Busca padrões do template
        patterns = self.db.get_field_patterns(template_id)
        
        # Extrai campos
        result = self.extractor.extract_all_fields(patterns, elements)
        
        return result
    
    def learn_from_extraction(
        self,
        pdf_path: str,
        label: str,
        schema: Dict[str, str],
        extracted_data: Dict[str, Any],
        elements: List[Dict[str, Any]],
        extraction_time: float
    ):
        """
        Aprende padrões de uma extração bem-sucedida (LLM)
        
        IMPORTANTE: Cada label tem seu próprio template
        - Templates de 'carteira_oab' só servem para 'carteira_oab'
        - Templates de 'tela_sistema' só servem para 'tela_sistema'
        - Isso garante que padrões sejam relevantes e específicos
        
        Args:
            pdf_path: Path do PDF
            label: Tipo do documento (ex: 'carteira_oab')
            schema: Schema de campos
            extracted_data: Dados extraídos pela LLM
            elements: Elementos estruturados
            extraction_time: Tempo que levou
        """
        # Texto de referência
        text = self._elements_to_text(elements)
        text_hash = self._hash_text(text)
        
        # Verifica se template já existe PARA ESTE LABEL
        template = self.db.get_template(label)
        
        if template:
            # Template existe: atualiza
            template_id = template['id']
            
            # Incrementa contador de amostras
            self.db.increment_sample_count(template_id)
            
            # Atualiza confiança baseado em sucessos
            # Fórmula ajustada: começa em 0.70, cresce 0.10 por sample
            # Com 3 samples: 0.70 + 0.30 = 1.00 (limitado a 0.95)
            sample_count = template['sample_count'] + 1
            new_confidence = min(0.95, 0.70 + (sample_count * 0.10))
            
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE templates
                    SET confidence = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (new_confidence, template_id))
                conn.commit()
        
        else:
            # Template não existe: cria novo
            # Determina tipo (rigid vs flexible)
            doc_type = "rigid"  # Default, pode refinar depois
            
            template_id = self.db.create_template(
                label=label,
                document_type=doc_type,
                reference_text=text,
                text_hash=text_hash
            )
            
            # Define confidence inicial (primeiro sample)
            initial_confidence = 0.70 + (1 * 0.10)  # = 0.80
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE templates
                    SET confidence = ?
                    WHERE id = ?
                """, (initial_confidence, template_id))
                conn.commit()
        
        # Aprende padrões para cada campo
        for field_name, field_desc in schema.items():
            field_value = extracted_data.get(field_name)
            
            # Aprende padrão
            pattern = self.learner.learn_pattern(
                field_name=field_name,
                field_value=field_value,
                structured_elements=elements,
                description=field_desc
            )
            
            # Salva padrão no banco
            self.db.add_field_pattern(
                template_id=template_id,
                field_name=field_name,
                field_description=field_desc,
                extraction_method=pattern.extraction_method,
                pattern_data=pattern.pattern_data,
                confidence=pattern.confidence
            )
    
    def _elements_to_text(self, elements: List[Dict[str, Any]]) -> str:
        """Converte elementos para texto"""
        return "\n".join([
            f"[x={e['x']}, y={e['y']}] {e.get('category', '')}: {e['text']}"
            for e in elements
        ])
    
    def _hash_text(self, text: str) -> str:
        """Gera hash do texto"""
        return hashlib.md5(text.encode()).hexdigest()
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas dos templates"""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            
            # Total de templates
            cursor.execute("SELECT COUNT(*) as count FROM templates")
            total_templates = cursor.fetchone()['count']
            
            # Templates por label
            cursor.execute("""
                SELECT label, COUNT(*) as count, AVG(confidence) as avg_confidence
                FROM templates
                GROUP BY label
            """)
            by_label = [dict(row) for row in cursor.fetchall()]
            
            # Total de padrões
            cursor.execute("SELECT COUNT(*) as count FROM field_patterns")
            total_patterns = cursor.fetchone()['count']
            
            return {
                "total_templates": total_templates,
                "templates_by_label": by_label,
                "total_patterns": total_patterns
            }

