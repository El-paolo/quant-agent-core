"""POST /agent/summarize/ — fetch news and summarize with the configured LLM."""

from fastapi import APIRouter, HTTPException

from fina.agent.news import fetch_news_headlines
from fina.agent.summarizer import summarize_news
from fina.api.dependencies import AgentSettingsDep
from fina.api.schemas import AgentRequest, AgentResponse
from fina.core.exceptions import ConfigError, FetcherError

router = APIRouter(tags=["agent"])


@router.post("/summarize/", response_model=AgentResponse)
async def agent_summarize(
    request: AgentRequest,
    settings: AgentSettingsDep,
) -> AgentResponse:
    """
    Fetch recent news headlines for a ticker and return an LLM-generated summary.

    Requires NEWS_API_KEY in settings. LLM provider is determined by
    LLM_PROVIDER setting (default: ollama).

    HTTP status codes:
      503 — agent configuration missing (no API keys)
      502 — upstream service failed (NewsAPI or LLM provider)
      500 — unexpected internal error
    """
    try:
        headlines = fetch_news_headlines(request.ticker, settings)
        summary = summarize_news(
            request.ticker,
            headlines,
            settings,
            prompt=request.summary_prompt,
        )
    except ConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except FetcherError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="Agent summarization failed")

    return AgentResponse(
        ticker=request.ticker,
        summary=summary,
        headlines=[h["title"] for h in headlines],
    )
