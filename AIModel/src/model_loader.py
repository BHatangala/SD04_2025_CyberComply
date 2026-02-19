import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

class DeepSeekLoader:
    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not found in .env file.")

        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:5000", # Required for OpenRouter rankings
            "X-Title": "CyberComply AI App",
        }
        # R1 Distill Qwen 32B: free, less congested than full R1, 
        # outperforms o1-mini, ideal for legal compliance reasoning
        self.model = "deepseek/deepseek-r1-distill-qwen-32b"
        print(f"DeepSeek R1 Distill Qwen 32B configured via OpenRouter (free).")

    def generate_response(self, prompt: str, max_length: int = 1024, temperature: float = 0.6, retries: int = 3) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_length,
            "temperature": temperature
        }

        for attempt in range(1, retries + 1):
            try:
                print(f"[DEBUG] Attempt {attempt}/{retries} — Sending request to OpenRouter...")
                print(f"[DEBUG] Prompt length: {len(prompt)} characters")

                response = requests.post(
                    self.api_url,
                    headers=self.headers,
                    json=payload,
                    timeout=120
                )

                print(f"[DEBUG] Response status: {response.status_code}")

                # Handle rate limiting with exponential backoff
                if response.status_code == 429:
                    wait_time = 2 ** attempt  # 2s, 4s, 8s
                    print(f"[DEBUG] Rate limited (429). Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    continue

                print(f"[DEBUG] Raw response preview: {response.text[:300]}")
                response.raise_for_status()
                result = response.json()

                if isinstance(result, dict) and "choices" in result:
                    content = result["choices"][0]["message"]["content"]
                    print(f"[DEBUG] Success — Response length: {len(content)} chars")
                    print(f"[DEBUG] Response content: {content[:300]}")
                    return content

                if isinstance(result, dict) and "error" in result:
                    print(f"[DEBUG] OpenRouter error: {result['error']}")
                    return ""

                return str(result)

            except requests.exceptions.Timeout:
                print(f"[DEBUG] Attempt {attempt} timed out after 120s.")
                if attempt < retries:
                    print(f"[DEBUG] Retrying in 5 seconds...")
                    time.sleep(5)
                else:
                    raise

            except requests.exceptions.RequestException as e:
                # Don't retry on non-429 HTTP errors
                print(f"[DEBUG] Request failed: {e}")
                raise

        raise RuntimeError("All retry attempts exhausted.")


_model_instance = None

def get_model():
    global _model_instance
    if _model_instance is None:
        _model_instance = DeepSeekLoader()
    return _model_instance