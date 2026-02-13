"""Lightweight in-process API usage tracking for scheduler runs."""
from collections import defaultdict
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import datetime
from functools import wraps
from typing import Callable, Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


@dataclass
class _ApiUsageScope:
    job_name: str
    started_at: datetime = field(default_factory=datetime.utcnow)
    total_calls: int = 0
    calls_by_provider: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    calls_by_provider_ticker: Dict[Tuple[str, str], int] = field(default_factory=lambda: defaultdict(int))
    calls_by_provider_endpoint: Dict[Tuple[str, str], int] = field(default_factory=lambda: defaultdict(int))
    calls_by_provider_status: Dict[Tuple[str, str], int] = field(default_factory=lambda: defaultdict(int))


_current_scope: ContextVar[Optional[_ApiUsageScope]] = ContextVar("api_usage_scope", default=None)


def _normalize_ticker(ticker: Optional[str]) -> str:
    if not ticker:
        return "UNKNOWN"
    return ticker.strip().upper()


def _normalize_endpoint(endpoint: str, ticker: str) -> str:
    endpoint_norm = endpoint or "unknown"
    if ticker != "UNKNOWN":
        endpoint_norm = endpoint_norm.replace(ticker, "{ticker}")
    return endpoint_norm


def begin_api_usage_scope(job_name: str) -> Token:
    """Start a scoped API usage tracker for one scheduler run."""
    scope = _ApiUsageScope(job_name=job_name)
    return _current_scope.set(scope)


def _emit_scope_summary(scope: _ApiUsageScope) -> None:
    elapsed = (datetime.utcnow() - scope.started_at).total_seconds()
    marketdata_calls = scope.calls_by_provider.get("marketdata", 0)
    marketdata_tickers = {
        ticker
        for (provider, ticker), count in scope.calls_by_provider_ticker.items()
        if provider == "marketdata" and count > 0
    }

    logger.info(
        "API_USAGE_SUMMARY job=%s duration_sec=%.2f total_calls=%d marketdata_calls=%d marketdata_unique_tickers=%d",
        scope.job_name,
        elapsed,
        scope.total_calls,
        marketdata_calls,
        len(marketdata_tickers)
    )

    # Provider-level status summary (for quick failure/rate-limit scans)
    for (provider, status), count in sorted(scope.calls_by_provider_status.items()):
        logger.info(
            "API_USAGE_STATUS job=%s provider=%s status=%s calls=%d",
            scope.job_name,
            provider,
            status,
            count
        )

    # Ticker-level summary, especially useful for marketdata budget analysis
    ticker_rows = sorted(
        scope.calls_by_provider_ticker.items(),
        key=lambda item: (item[0][0], -item[1], item[0][1])
    )
    for (provider, ticker), count in ticker_rows:
        logger.info(
            "API_USAGE_TICKER job=%s provider=%s ticker=%s calls=%d",
            scope.job_name,
            provider,
            ticker,
            count
        )

    # Endpoint summary for identifying expensive call patterns
    endpoint_rows = sorted(
        scope.calls_by_provider_endpoint.items(),
        key=lambda item: (item[0][0], -item[1], item[0][1])
    )
    for (provider, endpoint), count in endpoint_rows:
        logger.info(
            "API_USAGE_ENDPOINT job=%s provider=%s endpoint=%s calls=%d",
            scope.job_name,
            provider,
            endpoint,
            count
        )


def end_api_usage_scope(token: Token) -> None:
    """Finish a scoped tracker and emit a parse-friendly summary."""
    scope = _current_scope.get()
    _current_scope.reset(token)
    if scope is not None:
        _emit_scope_summary(scope)


def record_api_call(provider: str, endpoint: str, ticker: Optional[str] = None, status: str = "ok") -> None:
    """Record one provider call into the current scope, if one is active."""
    scope = _current_scope.get()
    if scope is None:
        return

    provider_norm = (provider or "unknown").strip().lower()
    ticker_norm = _normalize_ticker(ticker)
    endpoint_norm = _normalize_endpoint(endpoint, ticker_norm)
    status_norm = (status or "unknown").strip().lower()

    scope.total_calls += 1
    scope.calls_by_provider[provider_norm] += 1
    scope.calls_by_provider_ticker[(provider_norm, ticker_norm)] += 1
    scope.calls_by_provider_endpoint[(provider_norm, endpoint_norm)] += 1
    scope.calls_by_provider_status[(provider_norm, status_norm)] += 1


def with_api_usage_scope(job_name: str) -> Callable:
    """Decorator that wraps a scheduler function in one API-usage tracking scope."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            token = begin_api_usage_scope(job_name)
            try:
                return func(*args, **kwargs)
            finally:
                end_api_usage_scope(token)
        return wrapper
    return decorator
