"""
Orchestration pipeline — stub.

Full implementation arrives in build step #12.
This stub exists so api/routes/analysis.py can be tested immediately.
"""


def run_analysis(
    ticker: str,
    period: str = "1y",
    metrics: list[str] | None = None,
) -> dict:
    """Stub: replaced with real implementation in step #12."""
    return {}
