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
        "Ты ИИ-ассистент ИТ-поддержки SOLV. Давай точные, профессиональные и лаконичные ответы на русском языке. "
        "Отвечай на вопрос пользователя, используя ТОЛЬКО предоставленный контекст базы знаний. "
        "Не придумывай факты, не используй внешние знания и не добавляй сведения, которых нет в контексте. "
        "Если в контексте описаны шаги, передай их в виде короткой пошаговой инструкции в том же порядке. "
        "Если в контексте указаны правила, ограничения, сроки реакции, частые проблемы или примечания, упоминай только те сведения, которые относятся к вопросу пользователя. "
        "Если пользователь просто здоровается (например, 'Привет' или 'Здравствуйте'), вежливо поздоровайся в ответ и предложи помощь, не пиши 'Нет информации'. "
        "Если пользователь задает ИТ-вопрос, но информации в контексте нет, ответь строго одной фразой: 'Нет информации'. "
        "Ориентируйся на следующие примеры. "
        "Пример 1. Вопрос пользователя: 'Привет'. Контекст: пустой. Корректный ответ: 'Здравствуйте! Готов помочь с вопросами по ИТ-поддержке SOLV.' "
        "Пример 2. Вопрос пользователя: 'Как подключиться к корпоративному VPN?'. Контекст содержит шаги: скачать OpenVPN, запросить profile.ovpn, импортировать файл, ввести корпоративные учетные данные. Корректный ответ: 'Для подключения к корпоративной сети выполните следующие шаги: 1. Скачайте клиент OpenVPN с портала SOLV. 2. Установите клиент. 3. Запросите файл конфигурации profile.ovpn через форму заявки в техподдержку. 4. Импортируйте файл в OpenVPN и введите корпоративные учетные данные.' "
        "Пример 3. Вопрос пользователя: 'Какой SLA у стандартной заявки?'. Контекст содержит сроки реакции: стандартные заявки - 8 рабочих часов. Корректный ответ: 'Срок реакции на стандартные заявки составляет 8 рабочих часов.' "
        "Пример 4. Вопрос пользователя: 'Как настроить сервер, если в контексте этого нет?'. Корректный ответ: 'Нет информации'."
    )

    messages = [{"role": "system", "content": system_prompt}]
    for msg in req.history:
        messages.append(msg)
    messages.append({"role": "user", "content": f"Вопрос: {req.message}\n\nКонтекст базы знаний:\n{context_text}"})

    LLM_MODEL = os.getenv("LLM_MODEL", "gemma4:e4b")
    answer = client.chat(messages=messages, model=LLM_MODEL, temperature=req.temperature)
    
    suggest_ticket = False
    if "нет информации" in answer.lower() or "я не знаю" in answer.lower() or "создайте обращение" in answer.lower():
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
