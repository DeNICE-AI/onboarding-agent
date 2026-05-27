import requests
from typing import List, Dict, Any

class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434"):
        self._base_url = base_url

    def chat(self, messages: List[Dict[str, str]], model: str, temperature: float = 0.5) -> str:
        url = f"{self._base_url}/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "keep_alive": 0,
            "options": {
                "temperature": temperature
            }
        }
        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()
        return response.json().get("message", {}).get("content", "")

    def get_embeddings(self, texts: List[str], model: str) -> List[List[float]]:
        url = f"{self._base_url}/api/embed"
        payload = {
            "model": model,
            "input": texts,
            "keep_alive": 0
        }
        response = requests.post(url, json=payload, timeout=60)
        
        if response.status_code == 404:
            # Fallback to older /api/embeddings endpoint if /api/embed is not available
            # Note: /api/embeddings only accepts a single string prompt in older versions, 
            # but newer versions might support arrays. We will loop if needed.
            embeddings = []
            for text in texts:
                res = requests.post(
                    f"{self._base_url}/api/embeddings", 
                    json={"model": model, "prompt": text, "keep_alive": 0},
                    timeout=60
                )
                res.raise_for_status()
                embeddings.append(res.json().get("embedding", []))
            return embeddings

        response.raise_for_status()
        return response.json().get("embeddings", [])
