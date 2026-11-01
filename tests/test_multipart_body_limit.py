"""Adversarial tests for request caps before multipart parser spooling."""

import asyncio

from rfq_assistant.api.body_limit import MultipartBodyLimitMiddleware


def _run_middleware(*, headers, messages, max_bytes=10):
    received_messages = iter(messages)
    response = []

    async def receive():
        return next(received_messages)

    async def send(message):
        response.append(message)

    async def app(_scope, app_receive, app_send):
        while True:
            message = await app_receive()
            if message.get("type") == "http.disconnect":
                return
            if not message.get("more_body", False):
                break
        await app_send({"type": "http.response.start", "status": 200, "headers": []})
        await app_send({"type": "http.response.body", "body": b"ok"})

    scope = {"type": "http", "method": "POST", "headers": headers}
    middleware = MultipartBodyLimitMiddleware(app, max_bytes=max_bytes)
    asyncio.run(middleware(scope, receive, send))
    return response


def _multipart_headers(*, content_length=None):
    headers = [(b"content-type", b"multipart/form-data; boundary=synthetic")]
    if content_length is not None:
        headers.append((b"content-length", str(content_length).encode("ascii")))
    return headers


def test_declared_oversized_multipart_is_rejected_without_reading_body():
    response = _run_middleware(
        headers=_multipart_headers(content_length=11),
        messages=[],
    )

    assert response[0]["status"] == 413
    assert b"body limit" in response[1]["body"]
    assert dict(response[0]["headers"])[b"cache-control"] == b"no-store"


def test_streamed_multipart_is_rejected_when_actual_bytes_exceed_limit():
    response = _run_middleware(
        headers=_multipart_headers(content_length=5),
        messages=[
            {"type": "http.request", "body": b"123456", "more_body": True},
            {"type": "http.request", "body": b"78901", "more_body": True},
        ],
    )

    assert response[0]["status"] == 413
    assert len(response) == 2


def test_multipart_body_at_limit_and_non_multipart_body_are_not_rejected():
    exact_limit = _run_middleware(
        headers=_multipart_headers(content_length=10),
        messages=[{"type": "http.request", "body": b"1234567890", "more_body": False}],
    )
    non_multipart = _run_middleware(
        headers=[(b"content-type", b"application/json"), (b"content-length", b"100")],
        messages=[{"type": "http.request", "body": b"{}", "more_body": False}],
    )

    assert exact_limit[0]["status"] == 200
    assert non_multipart[0]["status"] == 200
