"""Early ASGI request-body limits for multipart uploads."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

ASGIApp = Callable[[dict, Callable, Callable], Awaitable[None]]
_TOO_LARGE_BODY = b'{"detail":"Multipart request exceeds the configured body limit."}'


class _BodyLimitExceeded(Exception):
    """Internal signal raised before a parser can spool an oversized body."""


class MultipartBodyLimitMiddleware:
    """Reject oversized multipart bodies before framework form parsing begins.

    Counts streamed bytes as a fallback when Content-Length is absent or false.
    The middleware does not buffer request data and is safe for chunked bodies.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        if max_bytes < 1:
            raise ValueError("Multipart body limit must be positive.")
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope.get("type") != "http" or not self._is_multipart(scope):
            await self.app(scope, receive, send)
            return

        content_length = self._content_length(scope)
        if content_length is not None and content_length > self.max_bytes:
            await self._reject(send)
            return

        received = 0
        response_started = False

        async def bounded_receive():
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _BodyLimitExceeded
            return message

        async def track_send(message):
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, bounded_receive, track_send)
        except _BodyLimitExceeded:
            if not response_started:
                await self._reject(send)

    @staticmethod
    def _is_multipart(scope: dict) -> bool:
        content_type = next(
            (value for key, value in scope.get("headers", []) if key.lower() == b"content-type"),
            b"",
        )
        return content_type.split(b";", 1)[0].strip().lower() == b"multipart/form-data"

    @staticmethod
    def _content_length(scope: dict) -> int | None:
        value = next(
            (value for key, value in scope.get("headers", []) if key.lower() == b"content-length"),
            None,
        )
        if value is None:
            return None
        try:
            length = int(value)
        except ValueError:
            return None
        return length if length >= 0 else None

    @staticmethod
    async def _reject(send: Callable) -> None:
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(_TOO_LARGE_BODY)).encode("ascii")),
                (b"cache-control", b"no-store"),
            ],
        })
        await send({"type": "http.response.body", "body": _TOO_LARGE_BODY})
