import os
import sys
from pathlib import Path
import json

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.extraction.cache_manager import CacheManager

PDF_PATH = r"ai-fellowship-data/files/"
DATASET_PATH = r"ai-fellowship-data/dataset.json"

def main():
    cache_store = CacheManager()
    with open(DATASET_PATH, "r") as f:
        dataset = json.load(f)
    for item in dataset:
        with open(os.path.join(PDF_PATH, item["pdf_path"]), "rb") as f:
            pdf_bytes = f.read()
        key = cache_store.generate_key(pdf_bytes, item["label"], item["extraction_schema"])
        print(key)

if __name__ == "__main__":
    main()