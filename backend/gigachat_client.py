import os
import time
import uuid
import requests

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class GigaChatClient:
    def __init__(self, client_id: str, client_secret: str, model: str = "GigaChat", verify: bool = False) -> None:
        """
        :param client_id: Client ID от GigaChat
        :param client_secret: Client Secret от GigaChat
        :param model: Модель для чата (например, GigaChat, GigaChat-Pro)
        :param verify: Проверять ли SSL сертификаты
        """
        self._client_id = client_id
        self._client_secret = client_secret
        self._model = model
        self._verify = verify
        self._access_token = None
        self._token_expiry = 0.0
        self._base_url = "https://gigachat.devices.sberbank.ru/api/v1"

    def _refresh_token(self) -> str:
        import base64
        url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        auth_payload = f"{self._client_id}:{self._client_secret}".encode("utf-8")
        headers = {
            "Authorization": f"Basic {base64.b64encode(auth_payload).decode('utf-8')}",
            "Content-Type": "application/x-www-form-urlencoded",
            "RqUID": str(uuid.uuid4()),
        }
        # Обычно для физ. лиц используется GIGACHAT_API_PERS, для юр. лиц GIGACHAT_API_CORP
        # Можно сделать это конфигурируемым, но оставим PERS по умолчанию
        scope = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
        response = requests.post(
            url,
            data=f"scope={scope}",
            headers=headers,
            timeout=30,
            verify=self._verify,
        )
        response.raise_for_status()
        payload = response.json()
        self._access_token = payload["access_token"]
        expires_in = payload.get("expires_in", 1800)
        self._token_expiry = time.time() + expires_in - 30
        return self._access_token

    def _get_token(self) -> str:
        if not self._access_token or time.time() >= self._token_expiry:
            return self._refresh_token()
        return self._access_token

    def chat(self, messages: list[dict], temperature: float = 0.5) -> str:
        url = f"{self._base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self._get_token()}"}
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
        }
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=60,
            verify=self._verify,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Превращает текст в векторы чисел"""
        url = f"{self._base_url}/embeddings"
        headers = {"Authorization": f"Bearer {self._get_token()}"}
        
        payload = {
            "model": "Embeddings",
            "input": texts 
        }
        
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=30,
            verify=self._verify,
        )
        response.raise_for_status()
        
        data = response.json().get("data", [])
        # Возвращаем список векторов
        return [item["embedding"] for item in data]
