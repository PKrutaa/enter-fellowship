import sys
from pathlib import Path
import json
import os

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.extraction.llm import LLM

DATASET_PATH = r"ai-fellowship-data/dataset.json"
PDF_PATH = r"ai-fellowship-data/files/"

def main():
    llm_client = LLM()

    with open(DATASET_PATH, "r") as f:
        dataset = json.load(f)
    for item in dataset:
        with open(os.path.join(PDF_PATH, item["pdf_path"]), "rb") as f:
            pdf_bytes = f.read()
        prompt = llm_client.generate_prompt(label=item["label"], schema=item["extraction_schema"])
        data = llm_client.extract_data(pdf_bytes=pdf_bytes, prompt=prompt)
        print(data)
        print("-" * 80)
        print(prompt)
        break

if __name__ == "__main__":
    main()