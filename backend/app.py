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
    history: List[Dict[str, str]] = []

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

    search_query = req.message
    last_user_msgs = [m["content"] for m in req.history if m["role"] == "user"]
    if last_user_msgs:
        search_query = f"{last_user_msgs[-1]} {req.message}"

    query_vec = embed_text([search_query])
    
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
        "Ты ИИ-ассистент ИТ-поддержки SOLV. Твоя задача — отвечать на текущий вопрос пользователя, используя ТОЛЬКО предоставленный 'Контекст базы знаний'.\n"
        "ПРАВИЛА:\n"
        "1. ИСПОЛЬЗУЙ ТОЛЬКО КОНТЕКСТ. Если в 'Контексте базы знаний' нет прямого ответа на вопрос, ответь строго одной фразой: 'Нет информации'.\n"
        "2. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать знания из интернета, придумывать факты, домысливать или давать общие советы (например, 'обратитесь в поддержку'), если этого нет в контексте.\n"
        "3. Тебе будет передана 'История предыдущих сообщений'. Используй ее ТОЛЬКО для того, чтобы понять, о чем идет речь в текущем вопросе (например, если пользователь пишет 'как его установить', история поможет понять, что речь о конкретном приложении). Отвечай только на 'Текущий вопрос'.\n"
        "4. Если пользователь просто здоровается (например, 'Привет' или 'Здравствуйте'), вежливо поздоровайся в ответ и предложи помощь.\n"
        "5. Если в контексте описаны шаги, передай их в виде короткой пошаговой инструкции."
    )

    history_text = ""
    if req.history:
        history_text = "История предыдущих сообщений для понимания контекста:\n"
        for m in req.history:
            role = "Пользователь" if m["role"] == "user" else "Ассистент"
            history_text += f"{role}: {m['content']}\n"
        history_text += "\n"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"{history_text}Текущий вопрос: {req.message}\n\nКонтекст базы знаний:\n{context_text}"}
    ]

    LLM_MODEL = os.getenv("LLM_MODEL", "gemma4:e4b")
    answer = client.chat(messages=messages, model=LLM_MODEL, temperature=req.temperature)
    
    RELEVANCE_THRESHOLD = float(os.getenv("RELEVANCE_THRESHOLD", "0.5"))
    max_score = max([item.get("score", 0.0) for item in similar_items]) if similar_items else 0.0

    suggest_ticket = False
    is_no_info = answer.strip().lower().replace(".", "") == "нет информации"

    if max_score < RELEVANCE_THRESHOLD or is_no_info:
        # Проверяем, не является ли сообщение простым приветствием
        user_msg = req.message.lower().strip()
        is_greeting = len(user_msg.split()) <= 3 and any(
            g in user_msg for g in ["привет", "здравствуй", "добрый", "хай", "hello"]
        )
        
        # Если это не простое приветствие, а порог не пройден или нейросеть явно ответила "Нет информации"
        if not is_greeting:
            suggest_ticket = True
            answer = "Я не знаю ответ на этот вопрос. Пожалуйста, создайте обращение в службу поддержки."

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
