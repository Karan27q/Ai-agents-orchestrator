from fastapi import APIRouter
from fastapi import Request

router = APIRouter(prefix="/observability", tags=["observability"])

@router.get("/health")
def health_check():
    return {"status": "ok", "message": "Backend service is healthy."}

@router.get("/metrics")
def metrics(request: Request):
    app = request.app
    return {
        "request_count": getattr(app.state, "request_count", 0),
        "error_count": getattr(app.state, "error_count", 0),
        "avg_response_time_ms": getattr(app.state, "avg_response_time_ms", 0.0),
    }
