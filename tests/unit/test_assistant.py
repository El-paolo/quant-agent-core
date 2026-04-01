"""
Unit tests for fina.agent.assistant — contextual Q&A assistant.

LLM calls are mocked via litellm — no real Ollama needed.
"""

from unittest.mock import patch, MagicMock

import pytest

from fina.agent.assistant import answer_question, _build_context_block
from fina.core.config import Settings
from fina.core.exceptions import FetcherError


def _settings() -> Settings:
    return Settings(
        llm_provider="ollama",
        ollama_model="mistral",
        ollama_base_url="http://localhost:11434",
    )


class TestBuildContextBlock:
    def test_none_context(self) -> None:
        result = _build_context_block(None)
        assert "No hay análisis" in result

    def test_empty_dict(self) -> None:
        result = _build_context_block({})
        assert "No hay análisis" in result

    def test_ticker_included(self) -> None:
        result = _build_context_block({"ticker": "AAPL"})
        assert "AAPL" in result

    def test_metrics_included(self) -> None:
        ctx = {"ticker": "AAPL", "sharpe": "1.25", "rsi": "65.3"}
        result = _build_context_block(ctx)
        assert "Sharpe" in result
        assert "1.25" in result
        assert "RSI" in result

    def test_models_included(self) -> None:
        ctx = {
            "garch_persistence": "0.9500",
            "hmm_regime": "Baja volatilidad",
            "arima_order": [0, 0, 0],
        }
        result = _build_context_block(ctx)
        assert "GARCH" in result
        assert "0.9500" in result
        assert "Baja volatilidad" in result
        assert "ARIMA" in result
        assert "0,0,0" in result

    def test_comparison_verdict_included(self) -> None:
        ctx = {"comparison_verdict": "Retornos no predecibles"}
        result = _build_context_block(ctx)
        assert "Retornos no predecibles" in result


class TestAnswerQuestion:
    @patch("fina.agent.assistant.litellm")
    def test_returns_answer_string(self, mock_litellm) -> None:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "El Sharpe de 0.5 está por debajo de 1."
        mock_litellm.completion.return_value = mock_response

        answer = answer_question("¿Es bueno un Sharpe de 0.5?", None, _settings())
        assert "Sharpe" in answer
        assert mock_litellm.completion.called

    @patch("fina.agent.assistant.litellm")
    def test_uses_ollama_model(self, mock_litellm) -> None:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Respuesta."
        mock_litellm.completion.return_value = mock_response

        answer_question("test", None, _settings())
        call_kwargs = mock_litellm.completion.call_args.kwargs
        assert call_kwargs["model"] == "ollama/mistral"
        assert call_kwargs["api_base"] == "http://localhost:11434"

    @patch("fina.agent.assistant.litellm")
    def test_context_injected_in_prompt(self, mock_litellm) -> None:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Respuesta."
        mock_litellm.completion.return_value = mock_response

        ctx = {"ticker": "TSLA", "sharpe": "2.10"}
        answer_question("¿Cómo va?", ctx, _settings())

        messages = mock_litellm.completion.call_args.kwargs["messages"]
        user_msg = messages[1]["content"]
        assert "TSLA" in user_msg
        assert "2.10" in user_msg

    @patch("fina.agent.assistant.litellm")
    def test_system_prompt_present(self, mock_litellm) -> None:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Respuesta."
        mock_litellm.completion.return_value = mock_response

        answer_question("test", None, _settings())

        messages = mock_litellm.completion.call_args.kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert "FINA" in messages[0]["content"]

    @patch("fina.agent.assistant.litellm")
    def test_llm_failure_raises_fetcher_error(self, mock_litellm) -> None:
        mock_litellm.completion.side_effect = Exception("Connection refused")

        with pytest.raises(FetcherError, match="Assistant LLM call failed"):
            answer_question("test", None, _settings())

    @patch("fina.agent.assistant.litellm")
    def test_max_tokens_limited(self, mock_litellm) -> None:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Respuesta."
        mock_litellm.completion.return_value = mock_response

        answer_question("test", None, _settings())
        assert mock_litellm.completion.call_args.kwargs["max_tokens"] == 512

    @patch("fina.agent.assistant.litellm")
    def test_no_context_still_works(self, mock_litellm) -> None:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "FINA es una plataforma."
        mock_litellm.completion.return_value = mock_response

        answer = answer_question("¿Qué es FINA?", None, _settings())
        assert len(answer) > 0
