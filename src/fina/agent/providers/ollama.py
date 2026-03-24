"""
Ollama LLM provider — calls the local Ollama server via httpx.

Uses the native Ollama /api/chat endpoint with stream=false.
No API key required; Ollama must be running at the configured base_url.

Security notes:
  - base_url and model are validated before use.
  - No user-supplied strings are passed to shell commands or eval().
  - Timeout is bounded to prevent indefinite hangs.
"""

import httpx

from fina.core.exceptions import FetcherError

_DEFAULT_TIMEOUT = 60.0  # seconds — local models can be slow on first token
_MAX_TOKENS = 1024
_DEFAULT_BASE_URL = "http://localhost:11434"

class OllamaProvider:
    """
    LLM provider backed by a local Ollama instance.

    Args:
        base_url: Ollama server URL (default: http://localhost:11434).
        model:    Model name as shown in `ollama list`.
        timeout:  Request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str = _DEFAULT_BASE_URL,
        model: str = "llama3.2:3b",
        timeout: float = _DEFAULT_TIMEOUT,
        system_prompt: str = "",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._system_prompt = system_prompt

    # ------------------------------------------------------------------
    # LLMProvider protocol implementation
    # ------------------------------------------------------------------

    def chat(self, prompt: str) -> str:
        """
        Send a prompt to the local Ollama model and return the response.

        Args:
            prompt: User message text.

        Returns:
            Model response as a plain string.

        Raises:
            FetcherError: On HTTP errors, timeout, or unexpected response format.
        """
        messages = []
        if self._system_prompt:
            messages.append({"role": "system", "content": self._system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {"num_predict": _MAX_TOKENS},
        }

        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    f"{self._base_url}/api/chat",
                    json=payload,
                )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise FetcherError(
                f"Ollama HTTP error {exc.response.status_code}: {exc}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise FetcherError(
                f"Ollama request timed out after {self._timeout}s: {exc}"
            ) from exc
        except httpx.RequestError as exc:
            raise FetcherError(
                f"Ollama request failed — is Ollama running at {self._base_url}? {exc}"
            ) from exc

        data = response.json()

        try:
            content: str = data["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise FetcherError(
                f"Unexpected Ollama response format: {data}"
            ) from exc

        return content.strip()

    def is_available(self) -> bool:
        """Return True if the Ollama server is reachable."""
        try:
            with httpx.Client(timeout=3.0) as client:
                r = client.get(f"{self._base_url}/api/tags")
            return r.status_code == 200
        except Exception:
            return False
