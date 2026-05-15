import httpx

class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "qwen2.5:7b-instruct"): 
        self.base_url = base_url
        self.model = model
        self.client = httpx.Client(timeout=60.0)

    def chat(self, messages: list[dict]) -> str:
        payload = {
            "model": self.model, 
            "messages": messages,
            "stream": False
        }

        try:
            response = self.client.post(
                f"{self.base_url}/api/chat", 
                json=payload
            )
            response.raise_for_status()

            data = response.json()
            return data["message"]["content"]
            
        except httpx.ConnectError: 
            raise ConnectionError("Ollama is not running. Start it with: ollama serve")
        except httpx.HTTPStatusError as e: 
            raise RuntimeError(f"Ollama error: {e.response.status_code}")
        except KeyError:
            raise RuntimeError("Unexpected response format from Ollama")


    def is_available(self) -> bool: 
        try: 
            response = self.client.get(f"{self.base_url}/api/tags")
            return response.status_code == 200
        except httpx.ConnectError: 
            return False