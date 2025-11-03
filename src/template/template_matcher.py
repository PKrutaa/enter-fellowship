# app/template/template_matcher.py

import difflib
from typing import Tuple, Optional
import re

class TemplateMatcher:
    """
    Determina se um documento corresponde a um template existente
    
    Usa múltiplas técnicas:
    1. Similaridade de texto (difflib)
    2. Estrutura de palavras-chave
    3. Layout de seções
    """
    
    # Thresholds
    RIGID_SIMILARITY_THRESHOLD = 0.90  # Formulários idênticos
    FLEXIBLE_SIMILARITY_THRESHOLD = 0.70  # Contratos/faturas
    
    @staticmethod
    def calculate_similarity(text1: str, text2: str) -> float:
        """
        Calcula similaridade entre dois textos
        
        Usa SequenceMatcher do difflib (algoritmo Ratcliff-Obershelp)
        Retorna valor entre 0 e 1
        """
        # Normaliza textos (remove espaços extras, lowercase)
        text1_norm = TemplateMatcher._normalize_text(text1)
        text2_norm = TemplateMatcher._normalize_text(text2)
        
        # Calcula similaridade
        matcher = difflib.SequenceMatcher(None, text1_norm, text2_norm)
        return matcher.ratio()
    
    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normaliza texto para comparação"""
        # Remove números (podem variar entre documentos)
        text = re.sub(r'\d+', '', text)
        
        # Remove espaços extras
        text = re.sub(r'\s+', ' ', text)
        
        # Lowercase
        text = text.lower().strip()
        
        return text
    
    @staticmethod
    def determine_document_type(
        new_text: str,
        reference_text: str
    ) -> Tuple[str, float]:
        """
        Determina se documento é 'rigid' ou 'flexible'
        
        Returns:
            Tuple[tipo, similaridade]
        """
        similarity = TemplateMatcher.calculate_similarity(new_text, reference_text)
        
        if similarity >= TemplateMatcher.RIGID_SIMILARITY_THRESHOLD:
            return "rigid", similarity
        elif similarity >= TemplateMatcher.FLEXIBLE_SIMILARITY_THRESHOLD:
            return "flexible", similarity
        else:
            return "unknown", similarity
    
    @staticmethod
    def extract_structural_keywords(text: str) -> set:
        """
        Extrai palavras-chave estruturais do documento
        
        Ignora valores variáveis, foca em labels/estrutura
        """
        # Remove números e valores
        text_clean = re.sub(r'\d+', '', text)
        
        # Palavras comuns estruturais
        structural_patterns = [
            r'nome[:\s]',
            r'cpf[:\s]',
            r'endereço[:\s]',
            r'telefone[:\s]',
            r'data[:\s]',
            r'assinatura[:\s]',
            r'valor[:\s]',
            r'total[:\s]',
        ]
        
        keywords = set()
        for pattern in structural_patterns:
            matches = re.findall(pattern, text_clean, re.IGNORECASE)
            keywords.update(matches)
        
        return keywords
    
    @staticmethod
    def calculate_structural_similarity(text1: str, text2: str) -> float:
        """
        Calcula similaridade baseada em estrutura (keywords)
        
        Útil para documentos com valores variáveis mas estrutura fixa
        """
        keywords1 = TemplateMatcher.extract_structural_keywords(text1)
        keywords2 = TemplateMatcher.extract_structural_keywords(text2)
        
        if not keywords1 or not keywords2:
            return 0.0
        
        # Jaccard similarity
        intersection = len(keywords1 & keywords2)
        union = len(keywords1 | keywords2)
        
        return intersection / union if union > 0 else 0.0