import os
from typing import List
import csv

import faiss
import numpy as np
from dotenv import load_dotenv
from .gigachat_client import GigaChatClient

from .rag_index import load_faq_data


load_dotenv()

GIGACHAT_CLIENT_ID = os.getenv("GIGACHAT_CLIENT_ID")
GIGACHAT_CLIENT_SECRET = os.getenv("GIGACHAT_CLIENT_SECRET")
if not GIGACHAT_CLIENT_ID or not GIGACHAT_CLIENT_SECRET:
    raise RuntimeError("GIGACHAT_CLIENT_ID or GIGACHAT_CLIENT_SECRET is not set. Please set it in your environment or in a .env file.")

client = GigaChatClient(client_id=GIGACHAT_CLIENT_ID, client_secret=GIGACHAT_CLIENT_SECRET, verify=False)

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DATA_PATH = os.path.join(DATA_DIR, "knowledge_base.csv")
INDEX_PATH = os.path.join(DATA_DIR, "faiss_index.bin")
META_PATH = os.path.join(DATA_DIR, "faqs_metadata.npy")


def embed_texts(texts: List[str]) -> np.ndarray:
    vectors = client.get_embeddings(texts)
    return np.array(vectors, dtype="float32")


def load_txt_documents(directory: str):
    """
    Загружает все .txt-файлы из папки и приводит их к формату FAQ.
    question — заголовок (первая непустая строка или имя файла),
    answer — остальной текст файла.
    """
    docs = []
    if not os.path.isdir(directory):
        return docs

    for name in os.listdir(directory):
        if not name.lower().endswith(".txt"):
            continue
        path = os.path.join(directory, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
        except OSError:
            continue

        if not content:
            continue

        lines = content.splitlines()
        # первая непустая строка как "заголовок"
        title = next((line.strip() for line in lines if line.strip()), name)
        body_lines = lines[1:] if len(lines) > 1 else []
        body = "\n".join(body_lines).strip() or content

        docs.append(
            {
                "question": title,
                "answer": body,
                "source": name,
            }
        )

    return docs


def main():
    items = []

    # 1) FAQ из CSV (если файл есть)
    if os.path.exists(DATA_PATH):
        try:
            with open(DATA_PATH, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                faqs = [{"question": row["question"], "answer": row["answer"], "source": "knowledge_base.csv"} for row in reader]
                items.extend(faqs)
                print(f"Loaded {len(faqs)} items from knowledge_base.csv")
        except Exception as e:
            print(f"Error reading CSV: {e}")

    # 2) Документы из .txt-файлов
    txt_docs = load_txt_documents(DATA_DIR)
    items.extend(txt_docs)
    print(f"Loaded {len(txt_docs)} TXT documents from {DATA_DIR}")

    if not items:
        raise RuntimeError("No data found to build index (no faqs.json and no txt files).")

    texts = [f"{item['question']}\n{item['answer']}" for item in items]

    print(f"Embedding {len(texts)} items...")
    embeddings = embed_texts(texts)

    dim = embeddings.shape[1]
    index = faiss.IndexFlatL2(dim)
    index.add(embeddings)

    os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)
    faiss.write_index(index, INDEX_PATH)

    # Save metadata (questions + answers + optional source)
    meta = np.array(
        [
            {
                "question": item["question"],
                "answer": item["answer"],
                "source": item.get("source", "faqs.json"),
            }
            for item in items
        ],
        dtype=object,
    )
    np.save(META_PATH, meta)

    print(f"Index built and saved to {INDEX_PATH}")


if __name__ == "__main__":
    main()

