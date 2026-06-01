import os
from typing import List, Dict, Any
from qdrant_client import QdrantClient

def load_qdrant_client(rag_dir: str) -> QdrantClient:
    if not os.path.exists(rag_dir):
        raise RuntimeError(
            "Qdrant directory not found. "
            "Run `python backend/build_index.py` first to build the RAG index."
        )
    return QdrantClient(path=rag_dir)

def search_similar(
    client: QdrantClient,
    collection_name: str,
    query_vec: list,
    k: int = 3,
) -> List[Dict[str, Any]]:
    
    if not client.collection_exists(collection_name):
        return []

    results = client.query_points(
        collection_name=collection_name,
        query=query_vec,
        limit=k
    )
    
    result_items = []
    for hit in results.points:
        item = hit.payload.copy() if hit.payload else {}
        item["score"] = hit.score
        result_items.append(item)
        
    return result_items
