import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
import time
from functools import lru_cache
from typing import Dict, Any
import threading

try:
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.middleware import SlowAPIMiddleware
    HAS_SLOWAPI = True
except ImportError:
    HAS_SLOWAPI = False

# Try to import GZIPMiddleware (optional)
try:
    from starlette.middleware.gzip import GZIPMiddleware
    HAS_GZIP = True
except ImportError:
    try:
        from fastapi.middleware.gzip import GZIPMiddleware
        HAS_GZIP = True
    except ImportError:
        HAS_GZIP = False

from database import engine, Base
from rate_limiter import limiter
from task_queue import start_queue_worker
from routes import auth, workflows, agents, files, search, notifications, ws, observability

# Create database tables if they do not exist
Base.metadata.create_all(bind=engine)

# Session cache for faster authentication (thread-safe)
_session_cache: Dict[str, Any] = {}
_cache_lock = threading.RLock()
CACHE_TTL = 300  # 5 minutes

class SessionCacheManager:
    @staticmethod
    def get(key: str) -> Any:
        with _cache_lock:
            if key in _session_cache:
                entry = _session_cache[key]
                if time.time() - entry['timestamp'] < CACHE_TTL:
                    return entry['value']
                else:
                    del _session_cache[key]
            return None
    
    @staticmethod
    def set(key: str, value: Any):
        with _cache_lock:
            _session_cache[key] = {'value': value, 'timestamp': time.time()}
    
    @staticmethod
    def clear_expired():
        current_time = time.time()
        with _cache_lock:
            expired_keys = [k for k, v in _session_cache.items() 
                          if current_time - v['timestamp'] >= CACHE_TTL]
            for k in expired_keys:
                del _session_cache[k]

app = FastAPI(
    title="AI Workflow Automation & Research Platform API",
    description="High-performance backend for workflow orchestration and multi-agent research.",
    version="1.0.0"
)

# Rate limiting middleware
app.state.limiter = limiter
if HAS_SLOWAPI:
    app.add_middleware(SlowAPIMiddleware)
    app.add_exception_handler(429, _rate_limit_exceeded_handler)

# Observability counters
app.state.request_count = 0
app.state.error_count = 0
app.state.total_response_time = 0.0
app.state.avg_response_time_ms = 0.0

# === PERFORMANCE MIDDLEWARE ===

# 1. GZIP compression for responses (reduces bandwidth) - optional
if HAS_GZIP:
    app.add_middleware(GZIPMiddleware, minimum_size=1000)

# 2. CORS with optimized settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count", "X-Page-Size"],
    max_age=3600,  # Cache preflight for 1 hour
)

# 3. Request/Response buffering and timing middleware
@app.middleware("http")
async def add_response_headers_and_buffer(request: Request, call_next):
    """Add performance headers and buffer responses."""
    start_time = time.time()
    app.state.request_count += 1
    
    # Set request size limits for buffering
    request.scope["max_body_size"] = 104857600  # 100MB
    
    try:
        response = await call_next(request)
    except Exception as exc:
        app.state.error_count += 1
        raise exc
    finally:
        process_time = time.time() - start_time
        app.state.total_response_time += process_time
        app.state.avg_response_time_ms = (
            app.state.total_response_time / max(app.state.request_count, 1) * 1000
        )

    # Add performance headers
    response.headers["X-Process-Time"] = str(process_time)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "public, max-age=3600"
    
    return response

# 4. Connection keep-alive middleware for persistent connections
@app.middleware("http")
async def add_keepalive(request: Request, call_next):
    response = await call_next(request)
    response.headers["Connection"] = "keep-alive"
    response.headers["Keep-Alive"] = "timeout=65, max=100"
    return response

from fastapi.staticfiles import StaticFiles

# Mount Routers under v1 API prefix
app.include_router(auth.router, prefix="/api/v1")
app.include_router(workflows.router, prefix="/api/v1")
app.include_router(agents.router, prefix="/api/v1")
app.include_router(files.router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")
app.include_router(notifications.router, prefix="/api/v1")
app.include_router(ws.router, prefix="/api/v1")
app.include_router(observability.router, prefix="/api/v1")

@app.on_event("startup")
async def startup_tasks():
    await start_queue_worker()

# Mount static files for frontend (Must be mounted after API routes)
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend"))
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    workers = int(os.getenv("WORKERS", 4))
    
    # Optimized uvicorn settings for maximum throughput
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=os.getenv("ENV", "development") == "development",
        workers=workers,
        limit_concurrency=1000,
        limit_max_requests=10000,
        timeout_keep_alive=65,
        access_log=os.getenv("ENV", "development") == "development",
    )
