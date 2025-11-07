# app/template/pattern_learner.py

import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

@dataclass
class FieldPattern:
    """Representa um padrão aprendido para um campo"""
    field_name: str
    extraction_method: str  # 'position', 'regex', 'context', 'hybrid'
    pattern_data: Dict[str, Any]
    confidence: float

class PatternLearner:
    """
    Aprende padrões de extração baseado em exemplos
    
    Estratégias:
    1. Position-based: Campo sempre na mesma posição no texto estruturado
    2. Regex-based: Campo segue padrão específico (CPF, telefone, etc)
    3. Context-based: Campo aparece após/antes de palavra-chave
    4. Hybrid: Combinação das anteriores
    """
    
    # Padrões regex comuns
    COMMON_PATTERNS = {
        'cpf': r'\d{3}\.?\d{3}\.?\d{3}-?\d{2}',
        'cnpj': r'\d{2}\.?\d{3}\.?\d{3}/?0001-?\d{2}',
        'telefone': r'\(?\d{2}\)?\s?\d{4,5}-?\d{4}',
        'cep': r'\d{5}-?\d{3}',
        'email': r'[\w\.-]+@[\w\.-]+\.\w+',
        'data': r'\d{2}/\d{2}/\d{4}',
        'hora': r'\d{2}:\d{2}',
        'valor': r'R\$\s?\d+[.,]\d{2}',
        'numero': r'\d+',
        'inscricao': r'\d{5,8}',
    }
    
    def learn_pattern(
        self,
        field_name: str,
        field_value: Any,
        structured_elements: List[Dict[str, Any]],
        description: str = ""
    ) -> FieldPattern:
        """
        Aprende padrão de extração para um campo baseado em exemplo
        
        Args:
            field_name: Nome do campo
            field_value: Valor extraído (do LLM)
            structured_elements: Lista de elementos com coordenadas
            description: Descrição do campo do schema
            
        Returns:
            FieldPattern com melhor estratégia aprendida
        """
        if field_value is None or field_value == "null":
            # Campo ausente, aprende padrão de ausência
            return FieldPattern(
                field_name=field_name,
                extraction_method='none',
                pattern_data={'expected': None},
                confidence=0.9
            )
        
        field_value_str = str(field_value).strip()
        
        # Tenta aprender padrões (ordem de prioridade)
        patterns = []
        
        # 1. Position-based (usando coordenadas)
        position_pattern = self._learn_position_pattern(
            field_value_str, structured_elements
        )
        if position_pattern:
            patterns.append(position_pattern)
        
        # 2. Regex-based (para padrões conhecidos)
        regex_pattern = self._learn_regex_pattern(
            field_name, field_value_str, description
        )
        if regex_pattern:
            patterns.append(regex_pattern)
        
        # 3. Context-based (antes/depois de keywords)
        context_pattern = self._learn_context_pattern(
            field_value_str, structured_elements
        )
        if context_pattern:
            patterns.append(context_pattern)
        
        # Escolhe melhor padrão (ou híbrido se múltiplos)
        if len(patterns) >= 2:
            # Híbrido: combina position + regex/context
            return FieldPattern(
                field_name=field_name,
                extraction_method='hybrid',
                pattern_data={
                    'patterns': [p.pattern_data for p in patterns],
                    'methods': [p.extraction_method for p in patterns]
                },
                confidence=0.85
            )
        elif len(patterns) == 1:
            return patterns[0]
        else:
            # Fallback: apenas valor esperado (low confidence)
            return FieldPattern(
                field_name=field_name,
                extraction_method='value_match',
                pattern_data={'expected_value': field_value_str},
                confidence=0.3
            )
    
    def _learn_position_pattern(
        self,
        field_value: str,
        elements: List[Dict[str, Any]]
    ) -> Optional[FieldPattern]:
        """
        Aprende padrão baseado em posição (coordenadas x, y)
        
        Melhoria: Procura match EXATO ou valor dentro do texto,
        evitando aprender labels como valores
        """
        # Labels comuns a evitar
        common_labels = {
            'inscrição', 'seccional', 'subseção', 'categoria', 'nome',
            'endereço', 'telefone', 'situação', 'data', 'sistema', 'produto',
            'valor', 'quantidade', 'tipo', 'cidade', 'referência'
        }
        
        best_match = None
        best_score = 0
        
        # Procura elemento que contém o valor
        for elem in elements:
            text_lower = elem['text'].lower().strip()
            value_lower = field_value.lower().strip()
            
            # Verifica se é label comum (evitar)
            is_label = any(label in text_lower for label in common_labels)
            
            # Match exato (melhor)
            if elem['text'].strip() == field_value:
                score = 1.0
                if not is_label:
                    score = 1.5  # Boost se não é label
                
                if score > best_score:
                    best_score = score
                    best_match = elem
            
            # Match parcial (valor dentro do texto)
            elif field_value in elem['text']:
                score = 0.8
                if not is_label:
                    score = 1.2
                
                if score > best_score:
                    best_score = score
                    best_match = elem
        
        if best_match:
            return FieldPattern(
                field_name="",
                extraction_method='position',
                pattern_data={
                    'x': best_match['x'],
                    'y': best_match['y'],
                    'x_tolerance': 30,  # Aumentado de 15 para 30 (mais flexível)
                    'y_tolerance': 20,  # Aumentado de 15 para 20
                    'category': best_match.get('category', 'Unknown'),
                    'expected_text': field_value,  # Para validação
                    'match_score': best_score
                },
                confidence=min(0.95, 0.7 + (best_score * 0.2))
            )
        
        return None
    
    def _learn_regex_pattern(
        self,
        field_name: str,
        field_value: str,
        description: str
    ) -> Optional[FieldPattern]:
        """
        Aprende padrão regex baseado no tipo de campo
        """
        field_lower = field_name.lower()
        desc_lower = description.lower()
        
        # Tenta identificar tipo pelo nome/descrição
        for pattern_type, regex in self.COMMON_PATTERNS.items():
            if pattern_type in field_lower or pattern_type in desc_lower:
                # Valida se o valor atual match o padrão
                if re.search(regex, field_value):
                    return FieldPattern(
                        field_name="",
                        extraction_method='regex',
                        pattern_data={
                            'pattern': regex,
                            'pattern_type': pattern_type
                        },
                        confidence=0.9
                    )
        
        return None
    
    def _learn_context_pattern(
        self,
        field_value: str,
        elements: List[Dict[str, Any]]
    ) -> Optional[FieldPattern]:
        """
        Aprende padrão baseado em contexto (elemento antes/depois)
        """
        # Procura elemento que contém o valor
        for idx, elem in enumerate(elements):
            if field_value in elem['text']:
                context = {}
                
                # Elemento anterior (possível label)
                if idx > 0:
                    prev_elem = elements[idx - 1]
                    context['prev_text'] = prev_elem['text']
                    context['prev_category'] = prev_elem.get('category')
                
                # Elemento posterior
                if idx < len(elements) - 1:
                    next_elem = elements[idx + 1]
                    context['next_text'] = next_elem['text']
                
                if context:
                    return FieldPattern(
                        field_name="",
                        extraction_method='context',
                        pattern_data=context,
                        confidence=0.7
                    )
        
        return None