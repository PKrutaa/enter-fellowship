import openai
import os
from typing import Dict, Any
from dotenv import load_dotenv
from unstructured.partition.pdf import partition_pdf
import json

load_dotenv()

class LLM:

    def __init__(self, model: str = "gpt-5-mini"):
        self.model: str = model
        self.client: openai.OpenAI = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def extract_data(self, pdf_path: str, prompt: str, schema: Dict[str, str], label: str = "") -> str:
        """Extrai dados de um PDF usando o modelo LLM com Structured Outputs
        
        Args:
            pdf_path: Caminho para o arquivo PDF
            prompt: Prompt com instruções de extração
            schema: Schema de campos a extrair
            label: Label do documento (para debug)
            
        Returns:
            str: Resposta do modelo (JSON com dados extraídos)
        """
        elements = self._structure_pdf(pdf_path)
        pdf_text = self._prepare_for_llm(elements)
        
        user_message = f"{prompt}\n\n{pdf_text}"
        
        # Cria JSON Schema para structured outputs
        json_schema = self._create_json_schema(schema)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": user_message}
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": json_schema
                },
                store=False,
                reasoning_effort="minimal",
                timeout=120.0  # 2 minutos timeout
            )
        except Exception:
            raise
        
        # Parse e limpa resultado
        result_dict = json.loads(response.choices[0].message.content)
        
        # Limpa cada valor
        cleaned_result = {}
        for field_name, value in result_dict.items():
            cleaned_result[field_name] = self._clean_extracted_value(value, field_name)
        
        return json.dumps(cleaned_result)
    
    def generate_prompt(self, label: str, schema: Dict[str, str]) -> str:
        """Gerador de prompt otimizado para extração de dados de PDFs brasileiros
        
        Args:
            label: Tipo do documento (ex: 'carteira_oab', 'tela_sistema')
            schema: Dicionário com campos a serem extraídos e suas descrições
            
        Returns:
            str: Prompt formatado para o modelo LLM
        """
        fields_list = "\n".join([f'  "{k}": {v}' for k, v in schema.items()])
        
        prompt = f"""Você é um extrator ESPECIALIZADO em documentos BRASILEIROS do tipo "{label}".

⚠️ CONTEXTO IMPORTANTE: Todos os dados são do BRASIL (pt-BR).

REGRAS CRÍTICAS DE EXTRAÇÃO:

1. EXTRAIA APENAS O VALOR EXATO
   - Sem texto adjacente, prefixos ou sufixos
   - Exemplo: "0 CONSIGNADO" → extrair "CONSIGNADO"

2. FORMATOS BRASILEIROS - PRESTE MUITA ATENÇÃO:
   
   📱 TELEFONE (8-9 dígitos + DDD):
      - Formato: (DD) 9XXXX-XXXX ou (DD) XXXX-XXXX
      - Exemplos: "(11) 98765-4321", "(21) 3456-7890"
      - NÃO confunda com CEP ou outros números!
   
   📮 CEP (8 dígitos):
      - Formato: XXXXX-XXX ou XXXXXXXX
      - Exemplos: "01310-300", "04567890"
      - Sempre 8 dígitos, geralmente com hífen
      - NÃO confunda com telefone!
      - Se existir o campo de endereço, coloque o CEP no campo de endereço.
   
   🆔 CPF (11 dígitos):
      - Formato: XXX.XXX.XXX-XX
      - Exemplo: "123.456.789-01"
      - Sempre 11 dígitos
   
   🏢 CNPJ (14 dígitos):
      - Formato: XX.XXX.XXX/XXXX-XX
      - Exemplo: "12.345.678/0001-90"
   
    Valores monetários:
        - No documento: "2.372,64"
        - Extraia somente o valor numerico separado por virgula ou ponto.
   
   📅 DATAS:
      - Formato: DD/MM/YYYY
      - Exemplo: "15/03/2024"
   
   🔢 NÚMERO DE PARCELAS:
      - Apenas o número, sem texto
      - Exemplos: "12", "24", "96"
      - NÃO extraia CEP ou telefone como parcelas!

3. VALIDAÇÃO DE NÚMEROS - PENSE ANTES DE EXTRAIR:
   
   ❓ É um CEP? → Deve ter 8 dígitos
   ❓ É um telefone? → Deve ter DDD + 8 ou 9 dígitos
   ❓ É parcelas? → Geralmente número pequeno (1-120)
   ❓ É CPF? → Sempre 11 dígitos
   ❓ É valor? → Pode ter decimais
   
   SE O NÚMERO NÃO FAZ SENTIDO PARA O CAMPO → USE null

4. EXEMPLOS ESPECÍFICOS:
   
   ✅ CORRETO:
   - "CEP: 01310-300" → extrair "01310-300" (8 dígitos = CEP)
   - "Tel: (11) 98765-4321" → extrair "(11) 98765-4321" (DDD + 9 dígitos = telefone)
   - "Parcelas: 24" → extrair "24" (número pequeno = parcelas)
   - "96 parcelas" → extrair "96"
   
   ❌ ERRADO:
   - Extrair CEP como telefone
   - Extrair telefone como CEP
   - Extrair CEP como número de parcelas
   - Inventar dados que não existem

5. SE CAMPO AUSENTE:
   - Use null (não invente dados)
   - Melhor null do que dado errado

CAMPOS A EXTRAIR:
{fields_list}

FORMATO DE SAÍDA:
Retorne APENAS um objeto JSON válido com os campos acima.

LEMBRE-SE: VALIDE se o número extraído faz SENTIDO para o campo!

DOCUMENTO:
"""
        return prompt
    
    def _generate_json_template(self, schema: Dict[str, str]) -> str:
        """Gera um template JSON compacto baseado no schema"""
        # Versão compacta para economizar tokens - JSON válido com chaves
        fields = ", ".join([f'"{k}": "..."' for k in schema.keys()])
        return f"{{{fields}}}"
    
    def _create_json_schema(self, schema: Dict[str, str]) -> Dict[str, Any]:
        """Cria JSON Schema para Structured Outputs da OpenAI"""
        properties = {}
        for field_name, field_desc in schema.items():
            properties[field_name] = {
                "type": ["string", "null"],
                "description": field_desc
            }
        
        return {
            "name": "pdf_extraction",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": properties,
                "required": list(schema.keys()),
                "additionalProperties": False
            }
        }
    
    def _clean_extracted_value(self, value: Any, field_name: str) -> Any:
        """Limpa e valida valor extraído com validação de formatos brasileiros"""
        import re
        
        if value is None or value == "null":
            return None
        
        value_str = str(value).strip()
        field_lower = field_name.lower()
        
        # Remove prefixos numéricos isolados (ex: "0 CONSIGNADO" → "CONSIGNADO")
        if ' ' in value_str and len(value_str) > 0 and value_str[0].isdigit():
            parts = value_str.split(' ', 1)
            if len(parts[0]) <= 2 and parts[0].isdigit():
                value_str = parts[1]
        
        # VALIDAÇÃO: CEP (8 dígitos)
        if any(x in field_lower for x in ['cep', 'codigo_postal']):
            digits = re.sub(r'\D', '', value_str)
            if len(digits) == 8:
                return f"{digits[:5]}-{digits[5:]}"
            return None
        
        # VALIDAÇÃO: Telefone (10-11 dígitos com DDD)
        if any(x in field_lower for x in ['telefone', 'phone', 'celular', 'fone']):
            digits = re.sub(r'\D', '', value_str)
            if len(digits) == 11:  # DDD + 9 dígitos (celular)
                return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
            elif len(digits) == 10:  # DDD + 8 dígitos (fixo)
                return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
            return None
        
        # VALIDAÇÃO: CPF (11 dígitos)
        if any(x in field_lower for x in ['cpf']):
            digits = re.sub(r'\D', '', value_str)
            if len(digits) == 11:
                return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
            return None
        
        # VALIDAÇÃO: CNPJ (14 dígitos)
        if any(x in field_lower for x in ['cnpj']):
            digits = re.sub(r'\D', '', value_str)
            if len(digits) == 14:
                return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"
            return None
        
        # VALIDAÇÃO: Número de parcelas (1-200)
        if any(x in field_lower for x in ['parcela', 'qtd', 'quantidade']):
            digits = re.sub(r'\D', '', value_str)
            if digits.isdigit():
                num = int(digits)
                if 1 <= num <= 200:
                    return str(num)
            return None
        
        # Limpa valores monetários
        if any(x in field_lower for x in ['valor', 'preco', 'price', 'total']):
            value_str = value_str.replace('R$', '').replace(' ', '').strip()
            if ',' in value_str:
                value_str = value_str.replace('.', '').replace(',', '.')
            try:
                float(value_str)
                return value_str
            except:
                return None
        
        # Limpa datas (DD/MM/YYYY)
        if any(x in field_lower for x in ['data', 'date']):
            value_str = value_str.replace('Data Referência:', '').replace('Data:', '').strip()
            if re.match(r'\d{2}/\d{2}/\d{4}', value_str):
                return value_str
            return None
        
        return value_str if value_str else None

    def _structure_pdf(self, pdf_path: str) -> list:
        """
        Extrai e estrutura PDF em elementos semânticos usando unstructured
        
        Estratégias disponíveis:
        - "fast": Rápido, usa pdfminer (bom para PDFs com texto)
        - "hi_res": Lento, usa detecção de layout (melhor para PDFs complexos)
        - "ocr_only": Apenas OCR (para PDFs escaneados)
        """
        return partition_pdf(
            filename=pdf_path,
            strategy="fast",  # Rápido e eficiente para PDFs com texto
            languages=["por"],
            include_page_breaks=False,  # Não precisamos (1 página só)
            infer_table_structure=True,  # Detecta estrutura de tabelas
            extract_images_in_pdf=False,  # Não precisamos de imagens
            # Otimizações adicionais:
            chunking_strategy=None,  # Sem chunking, queremos tudo
            max_characters=None,  # Sem limite
            extract_element_metadata=True
        )

    def _prepare_for_llm(self, elements: list) -> str:
        """
        Converte elementos estruturados para texto otimizado para LLM
        
        Estratégia:
        - Fornece coordenadas exatas (x, y) de cada elemento
        - Ordena elementos por posição de leitura natural
        - Remove viés de interpretação (CAMPO/VALOR)
        - LLM decide o que é label ou valor baseado nas coordenadas
        """
        
        # Extrai elementos com metadados de posição
        elements_data = []
        for elem in elements:
            if not elem.text or not elem.text.strip():
                continue
            
            # Coordenadas padrão
            x, y = 0, 0
            
            # Tenta extrair coordenadas
            if hasattr(elem, 'metadata') and elem.metadata:
                if hasattr(elem.metadata, 'coordinates') and elem.metadata.coordinates:
                    if hasattr(elem.metadata.coordinates, 'points') and elem.metadata.coordinates.points:
                        x, y = elem.metadata.coordinates.points[0]
            
            elements_data.append({
                'text': elem.text.strip(),
                'category': elem.category,
                'x': round(x, 1),
                'y': round(y, 1)
            })
        
        # Ordena por posição (top-to-bottom, left-to-right)
        elements_data.sort(key=lambda e: (e['y'], e['x']))
        
        # Agrupa elementos por proximidade vertical (linhas)
        lines = []
        current_line = []
        last_y = None
        y_tolerance = 10
        
        for elem in elements_data:
            if last_y is None or abs(elem['y'] - last_y) <= y_tolerance:
                current_line.append(elem)
            else:
                if current_line:
                    lines.append(current_line)
                current_line = [elem]
            last_y = elem['y']
        
        if current_line:
            lines.append(current_line)
        
        # Gera texto estruturado com coordenadas exatas e agrupamento
        text_parts = []
        text_parts.append("="*70)
        text_parts.append("Elementos organizados de cima para baixo, esquerda para direita")
        text_parts.append("Elementos na mesma linha vertical (~mesma coordenada y) estão próximos")
        text_parts.append("="*70)
        text_parts.append("DOCUMENTO ESTRUTURADO:")
        
        for line_idx, line in enumerate(lines, 1):
            # Ordena elementos da linha por X
            line.sort(key=lambda e: e['x'])
            
            # Mostra elementos da linha
            if len(line) == 1:
                elem = line[0]
                text_parts.append(
                    f"\n[x={elem['x']}, y={elem['y']}] {elem['category']}: {elem['text']}"
                )
            else:
                # Múltiplos elementos na mesma linha (potencial label-valor ou colunas)
                avg_y = round(sum(e['y'] for e in line) / len(line), 1)
                text_parts.append(f"\nLinha y≈{avg_y} com {len(line)} elementos:")
                for elem in line:
                    text_parts.append(
                        f"  [x={elem['x']}, y={elem['y']}] {elem['category']}: {elem['text']}"
                    )
        
        result = "\n".join(text_parts)
        return self._clean_extracted_text(result)
    
    def _get_vertical_region(self, y: float) -> str:
        """Determina região vertical (TOPO, CENTRO, RODAPÉ)"""
        PAGE_HEIGHT = 842  # A4 em pontos
        
        if y < PAGE_HEIGHT * 0.30:
            return "TOPO"
        elif y < PAGE_HEIGHT * 0.70:
            return "CENTRO"
        else:
            return "RODAPÉ"
    
    def _get_horizontal_position(self, x: float) -> str:
        """Determina posição horizontal (ESQUERDA, CENTRO, DIREITA)"""
        PAGE_WIDTH = 595  # A4 em pontos
        
        if x < PAGE_WIDTH * 0.35:
            return "ESQUERDA"
        elif x < PAGE_WIDTH * 0.65:
            return "CENTRO"
        else:
            return "DIREITA"
    
    def _clean_extracted_text(self, text: str) -> str:
        """
        Limpeza e normalização do texto extraído
        """
        import re
        
        # Remove múltiplas linhas vazias
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
        
        # Remove espaços no final das linhas
        text = '\n'.join(line.rstrip() for line in text.split('\n'))
        
        # Remove espaços múltiplos
        text = re.sub(r' {2,}', ' ', text)
        
        return text.strip()
