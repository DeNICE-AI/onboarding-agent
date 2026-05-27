import os
import json
import requests
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

from qdrant_client import QdrantClient
from .ollama_client import OllamaClient
from .rag_index import load_qdrant_client, search_similar

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
client = OllamaClient(base_url=OLLAMA_BASE_URL)

N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "http://localhost:5678/webhook/ticket")

app = FastAPI(title="SOLV FAQ RAG Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
RAG_DIR = os.path.join(os.path.dirname(__file__), "..", "rag")
COLLECTION_NAME = "solv_faq"

@app.get("/")
async def serve_frontend():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

class ChatRequest(BaseModel):
    message: str
    top_k: int = 3
    temperature: float = 0.7

class ChatResponse(BaseModel):
    answer: str
    context: List[Dict[str, Any]]
    suggest_ticket: bool

class TicketRequest(BaseModel):
    subject: str
    message: str

def embed_text(texts: List[str]) -> list:
    vectors = client.get_embeddings(texts, model="bge-m3")
    return vectors[0]

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message is empty")

    query_vec = embed_text([req.message])
    
    try:
        qdrant = load_qdrant_client(RAG_DIR)
        similar_items = search_similar(qdrant, COLLECTION_NAME, query_vec, k=req.top_k)
    except Exception as e:
        print(f"Error loading Qdrant: {e}")
        similar_items = []

    context_text = "\n\n".join(
        [f"Source: {item.get('title', item.get('source'))}\nContent: {item.get('text')}" for item in similar_items]
    )

    system_prompt = (
        "Ты ИИ-ассистент службы технической поддержки SOLV компании ГК ТОФС. "
        "Твоя задача — профессионально помогать сотрудникам по вопросам ИТ, используя ТОЛЬКО предоставленный контекст базы знаний. "
        "Если пользователь просто здоровается (например, 'Привет' или 'Здравствуйте'), вежливо поздоровайся в ответ и предложи задать вопрос по ИТ. "
        "КРИТИЧНОЕ ПРАВИЛО: Если вопрос пользователя касается ИТ-проблемы или рабочей задачи, но в контексте НЕТ точной информации для ответа, ты ДОЛЖЕН ответить строго этой фразой: "
        "'Я не знаю ответ на этот вопрос. Пожалуйста, создайте обращение в службу поддержки.' "
        "Никогда не придумывай информацию от себя и не используй знания вне предоставленного текста."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Вопрос: {req.message}\n\nКонтекст базы знаний:\n{context_text}"},
    ]

    answer = client.chat(messages=messages, model="gemma4:e4b", temperature=req.temperature)
    
    suggest_ticket = False
    if "я не знаю" in answer.lower() or "создайте обращение" in answer.lower():
        suggest_ticket = True

    return ChatResponse(answer=answer, context=similar_items, suggest_ticket=suggest_ticket)

@app.post("/api/ticket")
async def create_ticket(req: TicketRequest):
    try:
        response = requests.post(
            N8N_WEBHOOK_URL,
            json={"subject": req.subject, "message": req.message},
            timeout=10
        )
        response.raise_for_status()
        return {"status": "success", "detail": "Ticket sent to n8n successfully"}
    except Exception as e:
        print(f"Error sending ticket to n8n: {e}")
        raise HTTPException(status_code=500, detail="Failed to send ticket. Is n8n running?")

@app.get("/health")
async def health():
    return {"status": "ok"}
