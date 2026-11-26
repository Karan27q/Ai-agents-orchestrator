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

# Try to import GZipMiddleware (optional)
try:
    from starlette.middleware.gzip import GZipMiddleware
    HAS_GZIP = True
except ImportError:
    try:
        from fastapi.middleware.gzip import GZipMiddleware
        HAS_GZIP = True
    except ImportError:
        HAS_GZIP = False

from database import engine, Base
from rate_limiter import limiter
from task_queue import start_queue_workers
from routes import auth, workflows, agents, files, search, notifications, ws, observability, tasks, iam

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
    app.add_middleware(GZipMiddleware, minimum_size=1000)

# 2. CORS. A wildcard origin cannot be combined with credentials, so wildcards
#    are only used when credentials are explicitly not required.
_cors_env = os.getenv("CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000,http://localhost:3000,http://127.0.0.1:3000")
_cors_origins = [origin.strip() for origin in _cors_env.split(",") if origin.strip()]
_allow_credentials = True
if "*" in _cors_origins:
    _allow_credentials = False
    if os.getenv("ENV", "development") != "development":
        print("[CORS] WARNING: wildcard origin configured; credentials disabled.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_credentials,
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

    path = request.url.path
    if path.startswith("/api/"):
        # Authenticated API payloads must never be cached by shared proxies.
        response.headers["Cache-Control"] = "no-store"
    elif path.startswith("/assets/"):
        # Vite emits content-hashed filenames, so these are safe to pin.
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        # index.html must be revalidated so new builds are picked up.
        response.headers["Cache-Control"] = "no-cache"

    # Content-Security-Policy for the bundled SPA. Docs endpoints are skipped
    # because Swagger/ReDoc rely on inline scripts and a CDN bundle.
    docs_paths = {"/docs", "/redoc", "/docs/oauth2-redirect"}
    content_type = response.headers.get("content-type", "")
    if path not in docs_paths and content_type.startswith("text/html"):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'"
        )

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
app.include_router(tasks.router, prefix="/api/v1")
app.include_router(iam.router, prefix="/api/v1")

@app.on_event("startup")
async def startup_tasks():
    # Start persistent task queue workers
    await start_queue_workers()
    
    # Warm up FAISS vector index
    from database import SessionLocal
    import vector_store
    db = SessionLocal()
    try:
        vector_store.warm_faiss_index(db)
    finally:
        db.close()

# Mount static files for frontend (Must be mounted after API routes).
# Prefer the Vite build output; fall back to the source tree for local dev.
frontend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend"))
dist_dir = os.path.join(frontend_root, "dist")
if os.getenv("FRONTEND_DIR"):
    frontend_dir = os.getenv("FRONTEND_DIR")
elif os.path.isdir(dist_dir):
    frontend_dir = dist_dir
else:
    frontend_dir = frontend_root
    print("[FRONTEND] frontend/dist not found; run `npm run build` in frontend/ for the production bundle.")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    # Keep one worker by default: the FAISS index, LLM/user/session caches and
    # the WebSocket registry are in-process, so extra workers each get their
    # own copy and search/notification results become inconsistent.
    workers = int(os.getenv("WORKERS", 1))
    
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
