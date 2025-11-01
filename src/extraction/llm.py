import openai
import os
from typing import Dict
from dotenv import load_dotenv
from pypdf import PdfReader
import io
load_dotenv()

class LLM:
    "Modelo de LLM para extração de dados de PDFs"

    def __init__(self, model: str = "gpt-5-mini"):
        self.model: str = model
        self.client: openai.OpenAI = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.temp: float = 0.2

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
                {"role": "system", "content": "Você é um assistente especializado em extrair dados estruturados de documentos. Retorne sempre apenas o JSON solicitado, sem explicações adicionais."},
                {"role": "user", "content": user_message}
            ],
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
        
        # Criar lista de campos com suas descrições
        fields_description = []
        for field_name, field_desc in schema.items():
            fields_description.append(f'- "{field_name}": {field_desc}')
        
        fields_text = "\n".join(fields_description)
        
        prompt = f"""Você é um assistente especializado em extrair informações estruturadas de documentos PDF.

TIPO DE DOCUMENTO: {label}

CAMPOS A EXTRAIR:
{fields_text}

INSTRUÇÕES:
1. Analise cuidadosamente o documento fornecido
2. Extraia APENAS os campos solicitados acima
3. Retorne os dados no formato JSON com as chaves exatamente como especificado
4. Se um campo não for encontrado, use null como valor
5. Preserve o formato original dos dados (não faça conversões desnecessárias)
6. Seja preciso: 1 caractere errado torna o campo inválido
7. Retorne APENAS o JSON, sem texto adicional ou explicações

FORMATO DE SAÍDA ESPERADO:
{{
{self._generate_json_template(schema)}
}}

Extraia os dados do documento e retorne no formato JSON especificado acima."""

        return prompt
    
    def _generate_json_template(self, schema: Dict[str, str]) -> str:
        """Gera um template JSON baseado no schema"""
        template_lines = []
        fields = list(schema.keys())
        for i, field in enumerate(fields):
            comma = "," if i < len(fields) - 1 else ""
            template_lines.append(f'  "{field}": "valor_extraído"{comma}')
        return "\n".join(template_lines)

    def _extract_text_from_pdf(self, pdf_bytes: bytes) -> str:
        """Extrai o texto do arquivo PDF""" 
        pdf_reader = PdfReader(io.BytesIO(pdf_bytes))
        return pdf_reader.pages[0].extract_text()
