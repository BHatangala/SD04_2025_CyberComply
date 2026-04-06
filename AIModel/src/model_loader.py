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
        # Fallback chain: tried in order when a provider returns HTTP 500.
        self.model_fallback_chain = [
            "deepseek/deepseek-r1-distill-qwen-32b",
            "openrouter/free",
        ]
        # Tracks models confirmed down this session — skipped on all subsequent batches
        self._dead_models: set = set()
        print(f"DeepSeek R1 Distill Qwen 32B configured via OpenRouter (free). Fallback chain active.")

    def generate_response(self, prompt: str, max_length: int = 1024, temperature: float = 0.6, retries: int = 3) -> str:
        # Walk the fallback chain. A 500/404 (provider down) marks the model as dead
        # for the rest of this session and moves on — dead models are skipped instantly
        # on all future calls without wasting a network round-trip.
        for model in self.model_fallback_chain:
            if model in self._dead_models:
                print(f"[INFO] Skipping {model} (confirmed down this session)")
                continue
            print(f"[INFO] Trying model: {model}")
            try:
                return self._call_model(model, prompt, max_length, temperature, retries)
            except _ProviderDownError:
                print(f"[WARN] Model {model} returned 500 (provider down). Marking dead for this session.")
                self._dead_models.add(model)
                continue

        raise RuntimeError("All models in fallback chain exhausted.")

    def _call_model(self, model: str, prompt: str, max_length: int, temperature: float, retries: int) -> str:
        payload = {
            "model": model,
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

                # 500 = upstream provider down; 404 = no endpoints for this model
                if response.status_code in (500, 404):
                    raise _ProviderDownError(f"{response.status_code} from {model}: {response.text[:200]}")

                print(f"[DEBUG] Raw response preview: {response.text[:300]}")
                response.raise_for_status()
                result = response.json()

                if isinstance(result, dict) and "choices" in result:
                    content = result["choices"][0]["message"]["content"]
                    if not content:
                        # Empty body on a 200 — treat as transient, retry
                        print(f"[DEBUG] Empty response body on attempt {attempt}. Retrying...")
                        time.sleep(3)
                        continue
                    print(f"[DEBUG] Success — Response length: {len(content)} chars")
                    print(f"[DEBUG] Response content: {content[:300]}")
                    return content

                if isinstance(result, dict) and "error" in result:
                    print(f"[DEBUG] OpenRouter error: {result['error']}")
                    # Treat upstream faults (code 500 inside the JSON body) as provider-down too
                    if isinstance(result["error"], dict) and result["error"].get("code") == 500:
                        raise _ProviderDownError(f"Upstream fault from {model}")
                    return ""

                return str(result)

            except _ProviderDownError:
                raise  # Bubble up to generate_response so fallback triggers

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


class _ProviderDownError(Exception):
    """Raised internally when a model returns HTTP 500/404 so generate_response can try the next fallback."""
    pass


_model_instance = None

def get_model():
    global _model_instance
    if _model_instance is None:
        _model_instance = DeepSeekLoader()
    return _model_instance