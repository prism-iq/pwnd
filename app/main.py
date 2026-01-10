"""FastAPI application entry point"""
import logging
import time
from contextlib import asynccontextmanager
from collections import defaultdict
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pathlib import Path

from app.routes import router
from app.routes_auth import router as auth_router
from app.routes_chat import router as chat_router
from app.db import init_databases, close_pool
from app.config import API_HOST, API_PORT

# =============================================================================
# SECURITY: Rate Limiting
# =============================================================================

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        # Clean old requests
        self.requests[client_ip] = [
            t for t in self.requests[client_ip]
            if now - t < 60
        ]

        # Check rate limit
        if len(self.requests[client_ip]) >= self.requests_per_minute:
            return JSONResponse(
                status_code=429,
                content={"error": "Rate limit exceeded. Try again later."}
            )

        self.requests[client_ip].append(now)
        return await call_next(request)

# =============================================================================
# SECURITY: Security Headers
# =============================================================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "connect-src 'self'; "
            "font-src 'self'; "
            "frame-ancestors 'none'"
        )
        return response

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app")

# Initialize databases
init_databases()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Startup: initialize worker pool
    try:
        from app.workers import init_workers
        await init_workers()
        log.info("Worker pool initialized")
    except Exception as e:
        log.warning("Worker pool not started: %s", e)

    yield

    # Shutdown: cleanup workers and database pool
    try:
        from app.workers import shutdown_workers
        await shutdown_workers()
        log.info("Worker pool shutdown")
    except Exception as e:
        log.debug("Worker shutdown error: %s", e)

    # Close database connection pool
    close_pool()


app = FastAPI(
    title="OSINT Investigation Framework",
    description="Forensic intelligence platform with graph analysis",
    version="2.0.0",
    lifespan=lifespan
)

# Security middleware (order matters - first added = last executed)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware, requests_per_minute=100)

# CORS - production + localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://pwnd.icu",
        "https://www.pwnd.icu",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)

# Include API routes
app.include_router(router)
app.include_router(auth_router)
app.include_router(chat_router)

# Serve static files
from app.config import STATIC_DIR
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=API_HOST, port=API_PORT)
