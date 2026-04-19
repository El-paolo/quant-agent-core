"""Agent routes — news summarization and contextual Q&A assistant."""

import asyncio

from fastapi import APIRouter, HTTPException

from fina.agent.news import fetch_news_headlines
from fina.agent.summarizer import summarize_news
from fina.agent.assistant import answer_question
from fina.api.dependencies import AgentSettingsDep
from fina.api.schemas import AgentRequest, AgentResponse, AskRequest, AskResponse
from fina.core.exceptions import ConfigError, FetcherError

router = APIRouter(tags=["agent"])


def _run_summarize(ticker: str, settings: object, prompt: str | None) -> tuple:
    """Synchronous helper — runs in a thread to avoid blocking the event loop."""
    headlines = fetch_news_headlines(ticker, settings)
    summary = summarize_news(ticker, headlines, settings, prompt=prompt)
    return headlines, summary


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
        headlines, summary = await asyncio.to_thread(
            _run_summarize, request.first_ticker, settings, request.summary_prompt,
        )
    except ConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except FetcherError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="Agent summarization failed")

    return AgentResponse(
        ticker=request.first_ticker,
        summary=summary,
        headlines=[h["title"] for h in headlines],
    )


@router.post("/ask/", response_model=AskResponse)
async def agent_ask(
    request: AskRequest,
    settings: AgentSettingsDep,
) -> AskResponse:
    """
    Answer a question about FINA's metrics, models, or analysis results.

    The optional context dict lets the frontend inject current analysis
    state (ticker, metrics, model results) so answers are specific.

    HTTP status codes:
      503 — agent configuration missing
      502 — LLM provider failed
      500 — unexpected internal error
    """
    try:
        answer = await asyncio.to_thread(
            answer_question, request.question, request.context, settings,
        )
    except ConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except FetcherError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="Assistant failed")

    return AskResponse(
        question=request.question,
        answer=answer,
        ticker=request.ticker,
    )
