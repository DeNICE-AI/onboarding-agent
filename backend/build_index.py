import os
import uuid
from typing import List

from dotenv import load_dotenv
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct

from backend.gigachat_client import GigaChatClient

load_dotenv()

GIGACHAT_CLIENT_ID = os.getenv("GIGACHAT_CLIENT_ID")
GIGACHAT_CLIENT_SECRET = os.getenv("GIGACHAT_CLIENT_SECRET")
if not GIGACHAT_CLIENT_ID or not GIGACHAT_CLIENT_SECRET:
    raise RuntimeError("GIGACHAT_CLIENT_ID or GIGACHAT_CLIENT_SECRET is not set.")

client = GigaChatClient(client_id=GIGACHAT_CLIENT_ID, client_secret=GIGACHAT_CLIENT_SECRET, verify=False)

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
RAG_DIR = os.path.join(BASE_DIR, "rag")
COLLECTION_NAME = "solv_faq"

def get_markdown_files(directory: str) -> List[str]:
    files = []
    if not os.path.exists(directory):
        return files
    for name in os.listdir(directory):
        if name.lower().endswith(".md"):
            files.append(os.path.join(directory, name))
    return files

def main():
    md_files = get_markdown_files(DATA_DIR)
    if not md_files:
        print(f"No .md files found in {DATA_DIR}")
        return

    # Настраиваем разбиение Markdown по заголовкам
    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
    ]
    markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
    
    # Дополнительно разбиваем длинные куски
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=100
    )

    documents = []
    for file_path in md_files:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        filename = os.path.basename(file_path)
        md_header_splits = markdown_splitter.split_text(content)
        splits = text_splitter.split_documents(md_header_splits)
        
        for split in splits:
            # Собираем заголовки из метаданных для контекста
            headers = []
            for h in ["Header 1", "Header 2", "Header 3"]:
                if h in split.metadata:
                    headers.append(split.metadata[h])
            
            title = " - ".join(headers) if headers else filename
            
            documents.append({
                "id": str(uuid.uuid4()),
                "text": split.page_content,
                "title": title,
                "source": filename
            })

    print(f"Total chunks created: {len(documents)}")

    # Эмбеддинг (отправляем батчами чтобы не превысить лимиты)
    print("Embedding texts...")
    texts = [doc["text"] for doc in documents]
    embeddings = []
    batch_size = 10 # GigaChat обычно хорошо справляется с небольшими батчами
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        batch_embeddings = client.get_embeddings(batch)
        embeddings.extend(batch_embeddings)
        print(f"Embedded {min(i+batch_size, len(texts))}/{len(texts)}")

    if not embeddings:
        print("No embeddings generated. Exiting.")
        return

    # Подключение к локальному Qdrant
    os.makedirs(RAG_DIR, exist_ok=True)
    qdrant = QdrantClient(path=RAG_DIR)

    # Пересоздаем коллекцию
    if qdrant.collection_exists(collection_name=COLLECTION_NAME):
        qdrant.delete_collection(collection_name=COLLECTION_NAME)

    # Размерность эмбеддингов (нужно узнать из первого вектора)
    vector_size = len(embeddings[0])
    
    qdrant.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )

    # Запись в Qdrant
    points = []
    for i, doc in enumerate(documents):
        points.append(
            PointStruct(
                id=doc["id"],
                vector=embeddings[i],
                payload={
                    "text": doc["text"],
                    "title": doc["title"],
                    "source": doc["source"]
                }
            )
        )
    
    qdrant.upsert(
        collection_name=COLLECTION_NAME,
        points=points
    )

    print(f"Successfully indexed {len(documents)} chunks into Qdrant at {RAG_DIR}")

if __name__ == "__main__":
    main()

