"""
Unit tests for fina.data.fetcher

All yfinance calls are mocked — no real network requests are made.
Security-focused tests verify input sanitization for ticker symbols and dates.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from fina.core.exceptions import FetcherError
from fina.data.fetcher import (
    _parse_date,
    _sanitize_ticker,
    _sanitize_tickers,
    fetch_close_prices,
    fetch_universe,
)


# ---------------------------------------------------------------------------
# _sanitize_ticker (security boundary)
# ---------------------------------------------------------------------------


class TestSanitizeTicker:
    """Verify the allowlist regex rejects malicious or malformed inputs."""

    @pytest.mark.parametrize("ticker", ["AAPL", "BTC-USD", "EURUSD=X", "TLT", "MSFT"])
    def test_valid_tickers_accepted(self, ticker: str) -> None:
        assert _sanitize_ticker(ticker) == ticker.upper()

    def test_lowercases_are_normalized(self) -> None:
        assert _sanitize_ticker("aapl") == "AAPL"

    def test_strips_whitespace(self) -> None:
        assert _sanitize_ticker("  AAPL  ") == "AAPL"

    @pytest.mark.parametrize(
        "bad_ticker",
        [
            "",                          # empty
            " ",                         # whitespace only
            "A" * 21,                    # too long
            "AAPL; DROP TABLE prices",  # SQL-injection attempt
            "AAPL\nMSFT",               # newline injection
            "../../etc/passwd",          # path traversal attempt
            "AAPL|whoami",              # shell pipe injection
            "AAPL`id`",                 # backtick injection
            "<script>alert(1)</script>",# XSS attempt
        ],
    )
    def test_malicious_and_invalid_tickers_rejected(self, bad_ticker: str) -> None:
        with pytest.raises(FetcherError):
            _sanitize_ticker(bad_ticker)

    def test_non_string_raises(self) -> None:
        with pytest.raises(FetcherError, match="string"):
            _sanitize_ticker(123)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _parse_date (input validation)
# ---------------------------------------------------------------------------


class TestParseDate:
    def test_none_returns_none(self) -> None:
        assert _parse_date(None, "start") is None

    def test_valid_string_returns_iso(self) -> None:
        assert _parse_date("2023-01-15", "start") == "2023-01-15"

    def test_date_object_returns_iso(self) -> None:
        assert _parse_date(date(2023, 6, 1), "start") == "2023-06-01"

    def test_invalid_string_raises(self) -> None:
        with pytest.raises(FetcherError, match="ISO-8601"):
            _parse_date("15/01/2023", "start")

    def test_ambiguous_format_raises(self) -> None:
        with pytest.raises(FetcherError):
            _parse_date("01-15-2023", "start")  # MM-DD-YYYY — not ISO

    def test_non_date_type_raises(self) -> None:
        with pytest.raises(FetcherError):
            _parse_date(20230101, "start")  # type: ignore[arg-type]

    def test_out_of_range_date_raises(self) -> None:
        with pytest.raises(FetcherError, match="valid range"):
            _parse_date("1800-01-01", "start")


# ---------------------------------------------------------------------------
# fetch_close_prices — happy path (yfinance mocked)
# ---------------------------------------------------------------------------


def _make_mock_df(sample_prices: pd.Series) -> pd.DataFrame:
    """Build a minimal yfinance-style DataFrame from a price series."""
    return pd.DataFrame({"Close": sample_prices})


class TestFetchClosePricesHappyPath:
    def test_returns_series(self, sample_prices: pd.Series) -> None:
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _make_mock_df(sample_prices)
        with patch("fina.data.fetcher.yf.Ticker", return_value=mock_ticker):
            result = fetch_close_prices("AAPL", period="1y")
        assert isinstance(result, pd.Series)

    def test_series_is_named_after_ticker(self, sample_prices: pd.Series) -> None:
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _make_mock_df(sample_prices)
        with patch("fina.data.fetcher.yf.Ticker", return_value=mock_ticker):
            result = fetch_close_prices("AAPL", period="1y")
        assert result.name == "AAPL"

    def test_lowercase_ticker_normalized(self, sample_prices: pd.Series) -> None:
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _make_mock_df(sample_prices)
        with patch("fina.data.fetcher.yf.Ticker", return_value=mock_ticker):
            result = fetch_close_prices("aapl", period="1y")
        assert result.name == "AAPL"

    def test_no_nan_in_result(self, sample_prices: pd.Series) -> None:
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _make_mock_df(sample_prices)
        with patch("fina.data.fetcher.yf.Ticker", return_value=mock_ticker):
            result = fetch_close_prices("AAPL", period="1y")
        assert not result.isnull().any()

    def test_uses_date_range_when_start_provided(self, sample_prices: pd.Series) -> None:
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _make_mock_df(sample_prices)
        with patch("fina.data.fetcher.yf.Ticker", return_value=mock_ticker):
            fetch_close_prices("AAPL", start="2023-01-01")
        call_kwargs = mock_ticker.history.call_args.kwargs
        assert "start" in call_kwargs
        assert "period" not in call_kwargs

    def test_uses_period_when_no_start(self, sample_prices: pd.Series) -> None:
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _make_mock_df(sample_prices)
        with patch("fina.data.fetcher.yf.Ticker", return_value=mock_ticker):
            fetch_close_prices("AAPL", period="6mo")
        call_kwargs = mock_ticker.history.call_args.kwargs
        assert call_kwargs.get("period") == "6mo"

    def test_crypto_ticker_accepted(self, sample_prices: pd.Series) -> None:
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _make_mock_df(sample_prices)
        with patch("fina.data.fetcher.yf.Ticker", return_value=mock_ticker):
            result = fetch_close_prices("BTC-USD", period="1y")
        assert result.name == "BTC-USD"

    def test_fx_ticker_accepted(self, sample_prices: pd.Series) -> None:
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _make_mock_df(sample_prices)
        with patch("fina.data.fetcher.yf.Ticker", return_value=mock_ticker):
            result = fetch_close_prices("EURUSD=X", period="1y")
        assert result.name == "EURUSD=X"


# ---------------------------------------------------------------------------
# fetch_close_prices — error cases
# ---------------------------------------------------------------------------


class TestFetchClosePricesErrors:
    def test_empty_dataframe_raises(self) -> None:
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        with patch("fina.data.fetcher.yf.Ticker", return_value=mock_ticker):
            with pytest.raises(FetcherError, match="No price data"):
                fetch_close_prices("INVALID", period="1y")

    def test_missing_close_column_raises(self) -> None:
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame({"Open": [100.0, 101.0]})
        with patch("fina.data.fetcher.yf.Ticker", return_value=mock_ticker):
            with pytest.raises(FetcherError, match="Close"):
                fetch_close_prices("AAPL", period="1y")

    def test_yfinance_exception_wrapped(self) -> None:
        mock_ticker = MagicMock()
        mock_ticker.history.side_effect = RuntimeError("network error")
        with patch("fina.data.fetcher.yf.Ticker", return_value=mock_ticker):
            with pytest.raises(FetcherError, match="Failed to fetch"):
                fetch_close_prices("AAPL", period="1y")

    def test_invalid_ticker_raises_before_network_call(self) -> None:
        with patch("fina.data.fetcher.yf.Ticker") as mock_yf:
            with pytest.raises(FetcherError):
                fetch_close_prices("AAPL; DROP TABLE prices", period="1y")
            mock_yf.assert_not_called()

    def test_invalid_period_raises(self) -> None:
        with patch("fina.data.fetcher.yf.Ticker"):
            with pytest.raises(FetcherError, match="Invalid period"):
                fetch_close_prices("AAPL", period="999y")

    def test_start_after_end_raises(self) -> None:
        with patch("fina.data.fetcher.yf.Ticker"):
            with pytest.raises(FetcherError, match="strictly before"):
                fetch_close_prices("AAPL", start="2023-12-31", end="2023-01-01")

    def test_all_null_prices_raises(self, sample_prices: pd.Series) -> None:
        null_df = pd.DataFrame({"Close": [float("nan")] * 5})
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = null_df
        with patch("fina.data.fetcher.yf.Ticker", return_value=mock_ticker):
            with pytest.raises(FetcherError, match="null"):
                fetch_close_prices("AAPL", period="1y")


# ---------------------------------------------------------------------------
# _sanitize_tickers (list validation)
# ---------------------------------------------------------------------------


class TestSanitizeTickers:
    def test_valid_list(self) -> None:
        result = _sanitize_tickers(["AAPL", "MSFT", "GOOGL"])
        assert result == ["AAPL", "MSFT", "GOOGL"]

    def test_deduplicates(self) -> None:
        result = _sanitize_tickers(["AAPL", "aapl", "MSFT"])
        assert result == ["AAPL", "MSFT"]

    def test_normalizes_case(self) -> None:
        result = _sanitize_tickers(["aapl", "msft"])
        assert result == ["AAPL", "MSFT"]

    def test_empty_list_raises(self) -> None:
        with pytest.raises(FetcherError, match="empty"):
            _sanitize_tickers([])

    def test_non_list_raises(self) -> None:
        with pytest.raises(FetcherError, match="list"):
            _sanitize_tickers("AAPL")  # type: ignore[arg-type]

    def test_too_many_tickers_raises(self) -> None:
        with pytest.raises(FetcherError, match="too large"):
            _sanitize_tickers([f"T{i}" for i in range(51)])

    def test_invalid_ticker_in_list_raises(self) -> None:
        with pytest.raises(FetcherError):
            _sanitize_tickers(["AAPL", "BAD TICKER!"])


# ---------------------------------------------------------------------------
# fetch_universe (multi-ticker fetching)
# ---------------------------------------------------------------------------


class TestFetchUniverse:
    def test_returns_dataframe(self, sample_prices: pd.Series) -> None:
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _make_mock_df(sample_prices)
        with patch("fina.data.fetcher.yf.Ticker", return_value=mock_ticker):
            result = fetch_universe(["AAPL", "MSFT"])
        assert isinstance(result, pd.DataFrame)

    def test_columns_match_tickers(self, sample_prices: pd.Series) -> None:
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _make_mock_df(sample_prices)
        with patch("fina.data.fetcher.yf.Ticker", return_value=mock_ticker):
            result = fetch_universe(["AAPL", "MSFT", "GOOGL"])
        assert list(result.columns) == ["AAPL", "MSFT", "GOOGL"]

    def test_preserves_input_order(self, sample_prices: pd.Series) -> None:
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _make_mock_df(sample_prices)
        with patch("fina.data.fetcher.yf.Ticker", return_value=mock_ticker):
            result = fetch_universe(["GOOGL", "AAPL", "MSFT"])
        assert list(result.columns) == ["GOOGL", "AAPL", "MSFT"]

    def test_partial_failure_continues(self, sample_prices: pd.Series) -> None:
        """If one ticker fails, the rest should still be returned."""
        call_count = 0

        def side_effect(ticker, **kwargs):
            nonlocal call_count
            call_count += 1
            if ticker == "BAD":
                raise FetcherError("not found")
            return sample_prices.rename(ticker)

        with patch("fina.data.fetcher.fetch_close_prices", side_effect=side_effect):
            result = fetch_universe(["AAPL", "BAD", "MSFT"])
        assert "AAPL" in result.columns
        assert "MSFT" in result.columns
        assert "BAD" not in result.columns
        assert "BAD" in result.attrs["failed_tickers"]

    def test_all_fail_raises(self) -> None:
        with patch(
            "fina.data.fetcher.fetch_close_prices",
            side_effect=FetcherError("fail"),
        ):
            with pytest.raises(FetcherError, match="No tickers"):
                fetch_universe(["AAPL", "MSFT"])

    def test_warnings_in_attrs(self, sample_prices: pd.Series) -> None:
        def side_effect(ticker, **kwargs):
            if ticker == "BAD":
                raise FetcherError("not found")
            return sample_prices.rename(ticker)

        with patch("fina.data.fetcher.fetch_close_prices", side_effect=side_effect):
            result = fetch_universe(["AAPL", "BAD"])
        assert len(result.attrs["warnings"]) == 1

    def test_single_ticker(self, sample_prices: pd.Series) -> None:
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _make_mock_df(sample_prices)
        with patch("fina.data.fetcher.yf.Ticker", return_value=mock_ticker):
            result = fetch_universe(["AAPL"])
        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["AAPL"]

    def test_empty_list_raises(self) -> None:
        with pytest.raises(FetcherError, match="empty"):
            fetch_universe([])
