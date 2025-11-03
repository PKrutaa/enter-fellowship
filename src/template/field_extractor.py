# app/template/field_extractor.py

import re
from typing import Dict, Any, List, Optional
import json

class FieldExtractor:
    """
    Extrai campos usando padrões aprendidos
    
    Aplica estratégias: position, regex, context, hybrid
    """
    
    def extract_field(
        self,
        pattern_data: Dict[str, Any],
        extraction_method: str,
        elements: List[Dict[str, Any]]
    ) -> Optional[str]:
        """
        Extrai campo baseado no padrão aprendido
        
        Args:
            pattern_data: Dados do padrão (do banco)
            extraction_method: Método de extração
            elements: Elementos estruturados do PDF
            
        Returns:
            Valor extraído ou None
        """
        if isinstance(pattern_data, str):
            pattern_data = json.loads(pattern_data)
        
        if extraction_method == 'none':
            return None
        
        elif extraction_method == 'position':
            return self._extract_by_position(pattern_data, elements)
        
        elif extraction_method == 'regex':
            return self._extract_by_regex(pattern_data, elements)
        
        elif extraction_method == 'context':
            return self._extract_by_context(pattern_data, elements)
        
        elif extraction_method == 'hybrid':
            return self._extract_hybrid(pattern_data, elements)
        
        elif extraction_method == 'value_match':
            # Low confidence: retorna valor esperado
            return pattern_data.get('expected_value')
        
        return None
    
    def _extract_by_position(
        self,
        pattern: Dict[str, Any],
        elements: List[Dict[str, Any]]
    ) -> Optional[str]:
        """
        Extrai por posição (coordenadas)
        
        Estratégia melhorada:
        - Procura na região esperada (tolerância)
        - Filtra por categoria se disponível
        - Prioriza elementos que não são labels comuns
        """
        target_x = pattern['x']
        target_y = pattern['y']
        x_tolerance = pattern.get('x_tolerance', 15)  
        y_tolerance = pattern.get('y_tolerance', 15)
        expected_category = pattern.get('category')
        
        # Labels comuns que provavelmente NÃO são valores
        common_labels = {
            'inscrição', 'seccional', 'subseção', 'categoria', 'nome',
            'endereço', 'telefone', 'situação', 'data', 'sistema', 'produto'
        }
        
        candidates = []
        
        # Procura elementos na região esperada
        for elem in elements:
            x_diff = abs(elem['x'] - target_x)
            y_diff = abs(elem['y'] - target_y)
            
            if x_diff <= x_tolerance and y_diff <= y_tolerance:
                # Verifica categoria se especificada
                if expected_category and elem.get('category') != expected_category:
                    continue
                
                # Calcula score baseado em proximidade
                distance_score = 1.0 / (1.0 + x_diff + y_diff)
                
                # Penaliza se parece label comum
                text_lower = elem['text'].lower().strip()
                is_likely_label = any(label in text_lower for label in common_labels)
                
                if is_likely_label:
                    distance_score *= 0.5  # Reduz score
                
                candidates.append({
                    'element': elem,
                    'score': distance_score
                })
        
        # Retorna candidato com maior score
        if candidates:
            best = max(candidates, key=lambda c: c['score'])
            return best['element']['text']
        
        return None
    
    def _extract_by_regex(
        self,
        pattern: Dict[str, Any],
        elements: List[Dict[str, Any]]
    ) -> Optional[str]:
        """
        Extrai por padrão regex
        """
        regex = pattern['pattern']
        
        # Procura em todos os elementos
        for elem in elements:
            match = re.search(regex, elem['text'])
            if match:
                return match.group(0)
        
        return None
    
    def _extract_by_context(
        self,
        pattern: Dict[str, Any],
        elements: List[Dict[str, Any]]
    ) -> Optional[str]:
        """
        Extrai por contexto (elemento antes/depois)
        """
        prev_text = pattern.get('prev_text')
        
        # Procura elemento anterior que match
        for idx, elem in enumerate(elements):
            if prev_text and idx > 0:
                if prev_text in elements[idx - 1]['text']:
                    # Elemento atual é o que queremos
                    return elem['text']
        
        return None
    
    def _extract_hybrid(
        self,
        pattern: Dict[str, Any],
        elements: List[Dict[str, Any]]
    ) -> Optional[str]:
        """
        Extrai usando múltiplos métodos (maior confiança)
        """
        patterns = pattern.get('patterns', [])
        methods = pattern.get('methods', [])
        
        results = []
        
        for i, method in enumerate(methods):
            if i < len(patterns):
                result = self.extract_field(patterns[i], method, elements)
                if result:
                    results.append(result)
        
        # Se múltiplos métodos retornam mesmo valor, alta confiança
        if results and len(set(results)) == 1:
            return results[0]
        
        # Se resultados diferentes, retorna o primeiro
        return results[0] if results else None
    
    def extract_all_fields(
        self,
        field_patterns: List[Dict[str, Any]],
        elements: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Extrai todos os campos usando padrões
        
        Args:
            field_patterns: Lista de padrões do banco
            elements: Elementos estruturados
            
        Returns:
            Dicionário com campos extraídos
        """
        result = {}
        
        for pattern in field_patterns:
            field_name = pattern['field_name']
            extraction_method = pattern['extraction_method']
            pattern_data = pattern['pattern_data']
            
            value = self.extract_field(pattern_data, extraction_method, elements)
            result[field_name] = value
        
        return result

