import json
from fastapi import FastAPI, Request, Response
import httpx

app = FastAPI(title="API Gateway Proxy")
TARGET_BASE = "http://localhost:8000/api/v1"

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy(path: str, request: Request):
    url = f"{TARGET_BASE}/{path}"
    headers = dict(request.headers)
    headers.pop("host", None)

    body = await request.body()
    async with httpx.AsyncClient() as client:
        try:
            response = await client.request(
                request.method,
                url,
                headers=headers,
                content=body,
                params=request.query_params,
                follow_redirects=True,
                timeout=30.0,
            )
        except httpx.RequestError as exc:
            return Response(
                content=json.dumps({"detail": f"Gateway request failed: {exc}"}),
                status_code=502,
                media_type="application/json"
            )

    forwarded_headers = {
        key: value
        for key, value in response.headers.items()
        if key.lower() not in {
            "content-length",
            "connection",
            "keep-alive",
            "proxy-authenticate",
            "proxy-authorization",
            "te",
            "trailers",
            "transfer-encoding",
            "upgrade",
        }
    }

    if response.status_code >= 400 and "application/json" not in response.headers.get("content-type", ""):
        return Response(
            content=json.dumps({
                "detail": response.text.strip()[:200],
                "status_code": response.status_code,
            }),
            status_code=response.status_code,
            media_type="application/json",
        )

    return Response(
        content=response.content,
        status_code=response.status_code,
        headers=forwarded_headers,
        media_type=response.headers.get("content-type")
    )
