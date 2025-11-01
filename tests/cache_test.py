import os
import sys
from pathlib import Path
import json

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.cache.cache_key import CacheKeyGenerator

PDF_PATH = r"ai-fellowship-data/files/"
DATASET_PATH = r"ai-fellowship-data/dataset.json"

def main():
    with open(DATASET_PATH, "r") as f:
        dataset = json.load(f)
    for item in dataset:
        with open(os.path.join(PDF_PATH, item["pdf_path"]), "rb") as f:
            pdf_bytes = f.read()
        key1 = CacheKeyGenerator.generate_full_key(pdf_bytes, item["label"], item["extraction_schema"])
        print(CacheKeyGenerator.parse_key(key1))
        key2 = CacheKeyGenerator.generate_full_key(pdf_bytes, item["label"], item["extraction_schema"])
        print(CacheKeyGenerator.parse_key(key2))
        if key1 != key2:
            print("Error: full key and pdf key are different")
        else:
            print("Success: full key and pdf key are the same")
            print(f"Key1: {key1}")
            print(f"Key2: {key2}")

if __name__ == "__main__":
    main()