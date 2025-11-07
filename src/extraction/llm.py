import openai
import os
from typing import Dict
from dotenv import load_dotenv
from unstructured.partition.pdf import partition_pdf

load_dotenv()

class LLM:

    def __init__(self, model: str = "gpt-5-mini"):
        self.model: str = model
        self.client: openai.OpenAI = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def extract_data(self, pdf_path: str, prompt: str) -> str:
        """Extrai dados de um PDF usando o modelo LLM
        
        Args:
            pdf_path: Caminho para o arquivo PDF
            prompt: Prompt com instruções de extração
            
        Returns:
            str: Resposta do modelo (JSON com dados extraídos)
        """
        elements = self._structure_pdf(pdf_path)
        pdf_text = self._prepare_for_llm(elements)
        
        user_message = f"{prompt}\n\n{pdf_text}"

        print(user_message)
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "user", "content": user_message}
            ],
            response_format={"type": "json_object"},
            store=False,
            reasoning_effort="minimal"
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

        
        prompt = f"""Extraia em JSON do documento "{label}"
O Json deve conter cada um dos seguintes atributos:

{fields_list}
O conteudo esta com coordenadas exatas, portanto, extraia o conteudo de forma otimizada para cada campo.
Preste atenção em padrões de numeros de documentos, como CPF, CEP, CNPJ, etc.
Use null se ausente. Retorne só JSON.
{self._generate_json_template(schema)}"""

        return prompt
    
    def _generate_json_template(self, schema: Dict[str, str]) -> str:
        """Gera um template JSON compacto baseado no schema"""
        # Versão compacta para economizar tokens - JSON válido com chaves
        fields = ", ".join([f'"{k}": "..."' for k in schema.keys()])
        return f"{{{fields}}}"

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
