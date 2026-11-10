import logging
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any

from src.config import settings
from src.api.camera_routes import router as camera_router
from src.api.pipeline_routes import router as pipeline_router, media_router
from src.api.security import require_api_key
from src.api.gemini_routes import router as gemini_router
from src.core.scheduler import scheduler
from src.services.worker_manager import worker_manager

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("hoodyfarmkr-cctv")

app = FastAPI(
    title="hoodyfarmkr-cctv API",
    description="SmartLife CCTV (ONVIF) stream ingestion, OCI data pipeline & Gemini AI multimodal service",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"],
)

_auth = [Depends(require_api_key)]
app.include_router(camera_router, dependencies=_auth)
app.include_router(pipeline_router, dependencies=_auth)
app.include_router(gemini_router, dependencies=_auth)
app.include_router(media_router)

@app.on_event("startup")
def on_startup():
    logger.info(f"Starting {settings.APP_NAME} in environment: {settings.ENVIRONMENT}")
    if not settings.API_KEY:
        logger.warning("API_KEY is not set: API authentication is DISABLED (development only).")
    scheduler.start()
    try:
        worker_manager.start_all()
    except Exception as e:
        logger.warning(f"Failed to start workers on startup: {e}")

@app.on_event("shutdown")
def on_shutdown():
    logger.info(f"Stopping {settings.APP_NAME}")
    scheduler.stop()
    try:
        worker_manager.stop_all()
    except Exception as e:
        logger.warning(f"Failed to stop workers on shutdown: {e}")

@app.get("/health", tags=["Health"])
def health_check() -> Dict[str, Any]:
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
        "scheduler_running": scheduler.is_running
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=settings.PORT, reload=True)
