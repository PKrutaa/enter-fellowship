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
        Calcula similaridade entre dois textos usando múltiplas métricas
        
        Combina:
        1. Similaridade estrutural (campos/labels) - peso 50%
        2. Similaridade de tokens (palavras) - peso 30%
        3. Similaridade de caracteres (difflib) - peso 20%
        
        Retorna valor entre 0 e 1
        """
        # 1. Similaridade estrutural (mais importante)
        structural_sim = TemplateMatcher.calculate_structural_similarity(text1, text2)
        
        # 2. Similaridade de tokens (palavras importantes)
        token_sim = TemplateMatcher._calculate_token_similarity(text1, text2)
        
        # 3. Similaridade de caracteres (menos importante)
        text1_norm = TemplateMatcher._normalize_text(text1)
        text2_norm = TemplateMatcher._normalize_text(text2)
        matcher = difflib.SequenceMatcher(None, text1_norm, text2_norm)
        char_sim = matcher.ratio()
        
        # Combina com pesos (estrutura é MUITO mais importante)
        # Para documentos do mesmo tipo, a estrutura é o principal indicador
        final_similarity = (
            structural_sim * 0.70 +  # Estrutura: 70% (aumentado de 50%)
            token_sim * 0.20 +       # Tokens: 20% (reduzido de 30%)
            char_sim * 0.10          # Caracteres: 10% (reduzido de 20%)
        )
        
        return final_similarity
    
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
        
        # Palavras comuns estruturais (expandido para capturar mais campos)
        structural_patterns = [
            r'nome[:\s]',
            r'cpf[:\s]',
            r'cnpj[:\s]',
            r'rg[:\s]',
            r'endereço[:\s]',
            r'telefone[:\s]',
            r'email[:\s]',
            r'data[:\s]',
            r'assinatura[:\s]',
            r'valor[:\s]',
            r'total[:\s]',
            r'inscrição[:\s]',
            r'inscricao[:\s]',
            r'categoria[:\s]',
            r'situação[:\s]',
            r'situacao[:\s]',
            r'seccional[:\s]',
            r'subseção[:\s]',
            r'subsecao[:\s]',
            r'profissional[:\s]',
            r'cliente[:\s]',
            r'empresa[:\s]',
        ]
        
        keywords = set()
        for pattern in structural_patterns:
            matches = re.findall(pattern, text_clean, re.IGNORECASE)
            keywords.update([m.strip().lower() for m in matches])
        
        return keywords
    
    @staticmethod
    def calculate_structural_similarity(text1: str, text2: str) -> float:
        """
        Calcula similaridade baseada em estrutura (keywords)
        
        Útil para documentos com valores variáveis mas estrutura fixa
        """
        keywords1 = TemplateMatcher.extract_structural_keywords(text1)
        keywords2 = TemplateMatcher.extract_structural_keywords(text2)
        
        if not keywords1 and not keywords2:
            # Ambos sem keywords estruturais - considerar similar
            return 0.5
        
        if not keywords1 or not keywords2:
            # Apenas um tem keywords - considerar diferente
            return 0.0
        
        # Jaccard similarity
        intersection = len(keywords1 & keywords2)
        union = len(keywords1 | keywords2)
        
        return intersection / union if union > 0 else 0.0
    
    @staticmethod
    def _calculate_token_similarity(text1: str, text2: str) -> float:
        """
        Calcula similaridade baseada em tokens (palavras importantes)
        
        Remove stopwords e números, foca em termos relevantes
        """
        # Stopwords comuns em português
        stopwords = {
            'de', 'a', 'o', 'que', 'e', 'do', 'da', 'em', 'um', 'para',
            'é', 'com', 'não', 'uma', 'os', 'no', 'se', 'na', 'por', 'mais',
            'as', 'dos', 'como', 'mas', 'ao', 'ele', 'das', 'à', 'seu', 'sua'
        }
        
        # Extrai tokens (palavras de 3+ caracteres, sem números)
        tokens1 = set()
        tokens2 = set()
        
        for word in re.findall(r'\b[a-záàâãéèêíïóôõöúçñ]{3,}\b', text1.lower()):
            if word not in stopwords:
                tokens1.add(word)
        
        for word in re.findall(r'\b[a-záàâãéèêíïóôõöúçñ]{3,}\b', text2.lower()):
            if word not in stopwords:
                tokens2.add(word)
        
        if not tokens1 or not tokens2:
            return 0.0
        
        # Jaccard similarity
        intersection = len(tokens1 & tokens2)
        union = len(tokens1 | tokens2)
        
        return intersection / union if union > 0 else 0.0