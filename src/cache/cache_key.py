import hashlib
import json
from typing import Dict
import xxhash

class CacheKeyGenerator:
    """
    Gera chaves únicas para cache baseado em PDF + Label + Schema
    
    Estratégia:
    - PDF: Hash do conteúdo binário
    - Label: String simples
    - Schema: JSON ordenado (ordem não importa)
    
    Resultado: chave única e determinística
    """
    @staticmethod
    def generate_full_key(pdf_bytes: bytes, label: str, schema: Dict[str, str]) -> str:
        """
        Gera chave completa para cache L1/L2
        
        Format: {pdf_hash}:{label}:{schema_hash}
        Exemplo: "a3f5b2c1:carteira_oab:e4d3a1b2"
        """
        pdf_hash = CacheKeyGenerator._hash_pdf(pdf_bytes)

        schema_hash = CacheKeyGenerator._hash_schema(schema)

        return f"{pdf_hash}:{label}:{schema_hash}"

    @staticmethod
    def generate_pdf_key(pdf_bytes: bytes, label: str) -> str:
        """
        Gera chave para cache L1
        
        Format: {pdf_hash}:{label}
        Exemplo: "a3f5b2c1:carteira_oab"
        """
        pdf_hash = CacheKeyGenerator._hash_pdf(pdf_bytes)
        return f"{pdf_hash}:{label}"

    @staticmethod
    def generate_field_key(pdf_bytes: bytes, label: str, field: str) -> str:
        """
        Gera chave para cache L3
        
        Format: {pdf_hash}:{label}:{field}
        Exemplo: "a3f5b2c1:carteira_oab:nome"
        """
        pdf_hash = CacheKeyGenerator._hash_pdf(pdf_bytes)
        return f"{pdf_hash}:{label}:{field}"

    @staticmethod
    def _hash_pdf(pdf_bytes: bytes) -> str:
        """
        Gera hash do PDF
        """
        return xxhash.xxh64(pdf_bytes).hexdigest()

    @staticmethod
    def _hash_schema(schema: Dict[str, str]) -> str:
        """
        Gera hash do schema
        """
        schema_str = json.dumps(schema, sort_keys=True)
        return xxhash.xxh64(schema_str.encode()).hexdigest()

    @staticmethod
    def parse_key(full_key: str) -> dict[str, str]:
        """
        Parse de uma chave para debug
        
        Input: "a3f5b2c1:carteira_oab:e4d3a1b2"
        Output: {"pdf_hash": "a3f5b2c1", "label": "carteira_oab", ...}
        """
        parts = full_key.split(":")
        
        if len(parts) == 3:
            return {
                "pdf_hash": parts[0],
                "label": parts[1],
                "schema_hash": parts[2],
            }
        elif len(parts) == 4 and parts[0] == "field":
            return {
                "type": "field",
                "pdf_hash": parts[1],
                "label": parts[2],
                "field_name": parts[3],
            }
        
        return {}