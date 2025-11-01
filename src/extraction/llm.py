import openai
import os
from typing import Dict
from dotenv import load_dotenv
from pypdf import PdfReader
import io
load_dotenv()

class LLM:

    def __init__(self, model: str = "gpt-5-mini"):
        self.model: str = model
        self.client: openai.OpenAI = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def extract_data(self, pdf_bytes: bytes, prompt: str) -> str:
        """Extrai dados de um PDF usando o modelo LLM
        
        Args:
            pdf_bytes: Bytes do arquivo PDF
            prompt: Prompt com instruções de extração
            
        Returns:
            str: Resposta do modelo (JSON com dados extraídos)
        """
        pdf_text = self._extract_text_from_pdf(pdf_bytes)
        
        user_message = f"{prompt}\n\nDOCUMENTO:\n{pdf_text}"
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "user", "content": user_message}
            ],
            #max_completion_tokens=2000,
            response_format={"type": "json_object"},
            store=False,
        )
        
        return response.choices[0].message.content
    
    def generate_prompt(self, label: str, schema: Dict[str,str]) -> str:
        """Gerador de prompt para extração de dados de PDFs
        
        Args:
            label: Tipo do documento (ex: 'carteira_oab', 'tela_sistema')
            schema: Dicionário com campos a serem extraídos e suas descrições
            
        Returns:
            str: Prompt formatado para o modelo LLM
        """
        
        # Prompt MINIMALISTA para máxima velocidade
        fields_list = "\n".join([f'"{k}": {v}' for k, v in schema.items()])
        
        prompt = f"""Extraia em JSON do documento "{label}":

{fields_list}

Use null se ausente. Retorne só JSON:
{self._generate_json_template(schema)}"""

        return prompt
    
    def _generate_json_template(self, schema: Dict[str, str]) -> str:
        """Gera um template JSON compacto baseado no schema"""
        # Versão compacta para economizar tokens - JSON válido com chaves
        fields = ", ".join([f'"{k}": "..."' for k in schema.keys()])
        return f"{{{fields}}}"

    def _extract_text_from_pdf(self, pdf_bytes: bytes) -> str:
        """Extrai o texto do arquivo PDF""" 
        pdf_reader = PdfReader(io.BytesIO(pdf_bytes))
        return pdf_reader.pages[0].extract_text()
