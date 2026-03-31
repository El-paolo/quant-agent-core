"""
Anthropic LLM provider — Phase 2 placeholder.

To activate:
  1. `uv add anthropic`
  2. Set LLM_PROVIDER=anthropic and ANTHROPIC_API_KEY in .env
  3. Uncomment and implement the class below.

The OllamaProvider in ollama.py is the reference implementation.
AnthropicProvider must satisfy the same LLMProvider protocol.
"""

# from anthropic import Anthropic
# from fina.core.exceptions import FetcherError
#
#
# class AnthropicProvider:
#     def __init__(self, api_key: str, model: str = "claude-sonnet-4-6") -> None:
#         self._api_key = api_key
#         self._model = model
#
#     def chat(self, prompt: str) -> str:
#         try:
#             client = Anthropic(api_key=self._api_key)
#             message = client.messages.create(
#                 model=self._model,
#                 max_tokens=512,
#                 messages=[{"role": "user", "content": prompt}],
#             )
#             return message.content[0].text
#         except Exception as exc:
#             raise FetcherError(f"Anthropic API call failed: {exc}") from exc
#
#     def is_available(self) -> bool:
#         return bool(self._api_key)
