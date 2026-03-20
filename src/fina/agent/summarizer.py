"""
News summarizer — builds a prompt and calls the configured LLM provider.

The summarizer is provider-agnostic: it only knows the LLMProvider protocol.
Which concrete provider is used depends solely on Settings.llm_provider.

Adding a new provider (e.g. OpenAI, Gemini) requires:
  1. Creating providers/<name>.py implementing LLMProvider
  2. Adding an elif branch in get_provider()
  3. No changes here or anywhere else.
"""

from fina.agent.providers.base import LLMProvider
from fina.core.config import Settings
from fina.core.exceptions import ConfigError


def get_provider(settings: Settings) -> LLMProvider:
    """
    Instantiate and return the LLM provider configured in settings.

    Args:
        settings: Application settings with llm_provider and related fields.

    Returns:
        An object satisfying the LLMProvider protocol.

    Raises:
        ConfigError: If llm_provider is unknown or required keys are missing.
    """
    if settings.llm_provider == "ollama":
        from fina.agent.providers.ollama import OllamaProvider
        return OllamaProvider(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
        )

    if settings.llm_provider == "anthropic":
        # Phase 2: uncomment AnthropicProvider in providers/anthropic.py first
        raise ConfigError(
            "AnthropicProvider is not yet implemented. "
            "See src/fina/agent/providers/anthropic.py for instructions."
        )

    raise ConfigError(
        f"Unknown LLM provider '{settings.llm_provider}'. "
        "Valid options: ollama, anthropic."
    )


def summarize_news(
    ticker: str,
    headlines: list[dict],
    settings: Settings,
    *,
    prompt: str | None = None,
) -> str:
    """
    Summarize news headlines for an asset using the configured LLM provider.

    Args:
        ticker:    Asset ticker symbol (used for context in the prompt).
        headlines: List of article dicts from fetch_news_headlines.
        settings:  Application settings — llm_provider must be configured.
        prompt:    Optional custom instruction. Defaults to a financial
                   analysis prompt that asks for key themes and sentiment.

    Returns:
        Plain-text summary string. Returns a graceful "no news" message
        when headlines is empty (no LLM call is made).

    Raises:
        ConfigError:  If the provider is unknown or required keys are missing.
        FetcherError: If the LLM provider call fails.
    """
    settings.validate_for_agent()

    if not headlines:
        return f"No recent news found for {ticker}."

    headline_text = "\n".join(
        f"- {h['title']} ({h['publishedAt'][:10] if h['publishedAt'] else 'n/a'})"
        for h in headlines
    )

    user_prompt = prompt or (
        f"You are a financial analyst. Summarize the following recent news "
        f"headlines about {ticker}. Focus on key themes, market sentiment, "
        f"and any material events. Be concise (3-5 sentences).\n\n"
        f"Headlines:\n{headline_text}"
    )

    provider = get_provider(settings)
    return provider.chat(user_prompt)
