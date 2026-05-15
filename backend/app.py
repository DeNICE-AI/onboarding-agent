import os
from typing import List, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

import faiss
import numpy as np
from .gigachat_client import GigaChatClient

from .rag_index import load_index, search_similar


load_dotenv()

GIGACHAT_CLIENT_ID = os.getenv("GIGACHAT_CLIENT_ID")
GIGACHAT_CLIENT_SECRET = os.getenv("GIGACHAT_CLIENT_SECRET")
if not GIGACHAT_CLIENT_ID or not GIGACHAT_CLIENT_SECRET:
    raise RuntimeError("GIGACHAT_CLIENT_ID or GIGACHAT_CLIENT_SECRET is not set. Please set it in your environment or in a .env file.")

client = GigaChatClient(client_id=GIGACHAT_CLIENT_ID, client_secret=GIGACHAT_CLIENT_SECRET, verify=False)

app = FastAPI(title="FAQ RAG Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

@app.get("/")
async def serve_frontend():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))



class ChatRequest(BaseModel):
    message: str
    top_k: int = 3


class ChatResponse(BaseModel):
    answer: str
    context: List[Dict[str, Any]]


INDEX_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "faiss_index.bin")
META_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "faqs_metadata.npy")

faiss_index, metadata = load_index(INDEX_PATH, META_PATH)


def embed_text(texts: List[str]) -> np.ndarray:
    vectors = client.get_embeddings(texts)
    return np.array(vectors, dtype="float32")


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message is empty")

    query_vec = embed_text([req.message])
    similar_items = search_similar(faiss_index, metadata, query_vec, k=req.top_k)

    context_text = "\n\n".join(
        [f"Q: {item['question']}\nA: {item['answer']}" for item in similar_items]
    )

    system_prompt = (
        "Ты ИИ-ассистент для онбординга новых сотрудников компании. Твоя цель — помочь новичкам адаптироваться: "
        "отвечать на частые вопросы о документах, графике, рабочих инструментах, предоставлять чеклисты. "
        "Стиль общения: доброжелательный, структурированный, корпоративный. "
        "Ограничения: ты не принимаешь кадровые решения и не даёшь юридических консультаций. Если вопрос сложный или выходит за рамки твоей компетенции, "
        "чётко направляй запрос к профильным специалистам (HR, IT-отдел). "
        "Используй предоставленный контекст для формирования ответа."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Вопрос пользователя: {req.message}\n\nКонтекст FAQ:\n{context_text}"},
    ]

    answer = client.chat(messages=messages, temperature=0.2)

    return ChatResponse(answer=answer, context=similar_items)


@app.get("/health")
async def health():
    return {"status": "ok"}


