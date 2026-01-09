"""FastAPI application entry point"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from app.routes import router
from app.routes_auth import router as auth_router
from app.db import init_databases
from app.config import API_HOST, API_PORT

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
        log.warning(f"Worker pool not started: {e}")

    yield

    # Shutdown: cleanup workers
    try:
        from app.workers import shutdown_workers
        await shutdown_workers()
        log.info("Worker pool shutdown")
    except:
        pass


app = FastAPI(
    title="OSINT Investigation Framework",
    description="Forensic intelligence platform with graph analysis",
    version="2.0.0",
    lifespan=lifespan
)

# CORS - production + localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://pwnd.icu",
        "http://localhost",
        "http://127.0.0.1",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router)
app.include_router(auth_router)

# Serve static files
static_dir = Path("/opt/rag/static")
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=API_HOST, port=API_PORT)
