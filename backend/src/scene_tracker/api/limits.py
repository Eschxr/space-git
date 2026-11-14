"""Bound multipart request bytes before the parser can spool unlimited files."""

from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


class UploadLimitMiddleware:
    def __init__(self, app, max_bytes):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            length = self.max_bytes + 1
        if length > self.max_bytes:
            response = JSONResponse(
                status_code=413,
                content={
                    "error": {"code": "upload_too_large", "message": "Request byte limit exceeded"}
                },
            )
            return await response(scope, receive, send)
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > self.max_bytes:
                raise HTTPException(413, "Request byte limit exceeded")
            return message

        await self.app(scope, limited_receive, send)
