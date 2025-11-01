import sys
from pathlib import Path
import json
import os
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.extraction.llm import LLM

DATASET_PATH = r"ai-fellowship-data/dataset.json"
PDF_PATH = r"ai-fellowship-data/files/"

def main():
    start_time = time.time()
    llm_client = LLM()

    with open(DATASET_PATH, "r") as f:
        dataset = json.load(f)
    for item in dataset:
        with open(os.path.join(PDF_PATH, item["pdf_path"]), "rb") as f:
            pdf_bytes = f.read()
        prompt = llm_client.generate_prompt(label=item["label"], schema=item["extraction_schema"])
        data = llm_client.extract_data(pdf_bytes=pdf_bytes, prompt=prompt)
        print("=" * 80)
        print(f"Label: {item['label']}")
        print(f"PDF: {item['pdf_path']}")
        print("=" * 80)
        print("EXTRACTED DATA:")
        print(data)
        print("=" * 80)
        print(prompt)
        break
    end_time = time.time()
    print(f"Time taken: {end_time - start_time:.2f} seconds")
if __name__ == "__main__":
    main()