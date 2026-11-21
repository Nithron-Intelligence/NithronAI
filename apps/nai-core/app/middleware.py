"""
nAI Core Middleware
Request logging, rate limiting, and request ID tracking
"""

import ipaddress
import json
import time
import uuid
from collections.abc import Callable

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from .config import get_settings
from .utils.logging import get_logger, log_request, request_id_var

logger = get_logger(__name__)

RATE_LIMIT_EXEMPT_PATHS = {"/health"}


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for request logging and timing."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = str(uuid.uuid4())[:8]
        request_id_var.set(request_id)
        start_time = time.perf_counter()

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start_time) * 1000
        log_request(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            request_id=request_id,
        )
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"
        return response


def _parse_networks(entries: list[str]) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    networks = []
    for entry in entries:
        try:
            networks.append(ipaddress.ip_network(entry.strip(), strict=False))
        except ValueError:
            logger.warning(f"Ignoring invalid trusted proxy entry: {entry!r}")
    return networks


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple in-memory, per-process sliding-window rate limiter.

    The client is identified by its socket address. ``X-Forwarded-For`` is only honoured
    when the direct peer is listed in ``NAI_TRUSTED_PROXIES``; otherwise anyone could
    spoof the header to dodge the limit.
    """

    SWEEP_EVERY = 1000

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.settings = get_settings()
        self._trusted = _parse_networks(self.settings.trusted_proxies)
        self._requests: dict[str, list[float]] = {}
        self._calls = 0

    def _is_trusted(self, host: str) -> bool:
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return False
        return any(ip in net for net in self._trusted)

    def _get_client_key(self, request: Request) -> str:
        peer = request.client.host if request.client else "unknown"
        if not self._trusted or not self._is_trusted(peer):
            return peer
        forwarded = request.headers.get("X-Forwarded-For", "")
        # Walk from the right: the first hop that isn't one of our proxies is the client.
        for hop in reversed([h.strip() for h in forwarded.split(",") if h.strip()]):
            if not self._is_trusted(hop):
                return hop
        return peer

    def _sweep(self, now: float) -> None:
        window_start = now - self.settings.rate_limit_window_seconds
        for key in list(self._requests):
            recent = [t for t in self._requests[key] if t > window_start]
            if recent:
                self._requests[key] = recent
            else:
                del self._requests[key]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self.settings.rate_limit_enabled or request.url.path in RATE_LIMIT_EXEMPT_PATHS:
            return await call_next(request)

        now = time.time()
        self._calls += 1
        if self._calls % self.SWEEP_EVERY == 0:
            self._sweep(now)

        client_key = self._get_client_key(request)
        window_start = now - self.settings.rate_limit_window_seconds
        recent = [t for t in self._requests.get(client_key, []) if t > window_start]
        limit = self.settings.rate_limit_requests

        if len(recent) >= limit:
            self._requests[client_key] = recent
            logger.warning(f"Rate limit exceeded for {client_key}")
            return Response(
                content=json.dumps({"detail": "Too many requests. Please slow down."}),
                status_code=429,
                media_type="application/json",
                headers={
                    "Retry-After": str(self.settings.rate_limit_window_seconds),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        recent.append(now)
        self._requests[client_key] = recent
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - len(recent)))
        return response


def setup_middleware(app: FastAPI) -> None:
    """Configure all middleware for the application (last added = outermost)."""
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
