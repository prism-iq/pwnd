"""FastAPI application entry point"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from app.routes import router
from app.routes_auth import router as auth_router
from app.db import init_databases
from app.config import API_HOST, API_PORT

# Initialize databases on startup
init_databases()

app = FastAPI(
    title="L Investigation Framework",
    description="Investigation framework with graph database and LLM analysis",
    version="1.0.0"
)

# CORS (restrictive - only localhost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1", "http://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
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
