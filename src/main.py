from contextlib import asynccontextmanager
import logging
from typing import Dict, Any

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from src.config import settings
from src.api.camera_routes import router as camera_router
from src.api.pipeline_routes import router as pipeline_router, media_router
from src.api.security import require_api_key
from src.api.gemini_routes import router as gemini_router
from src.core.observability import (
    render_prometheus_metrics,
    set_correlation_id,
)
from src.core.scheduler import scheduler
from src.services.worker_manager import worker_manager

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("hoodyfarmkr-cctv")


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} in environment: {settings.ENVIRONMENT}")
    if not settings.API_KEY:
        logger.warning("API_KEY is not set: API authentication is DISABLED (development only).")
    scheduler.start()
    try:
        worker_manager.start_all()
    except Exception as e:
        logger.warning(f"Failed to start workers on startup: {e}")
    yield
    logger.info(f"Stopping {settings.APP_NAME}")
    scheduler.stop()
    try:
        worker_manager.stop_all()
    except Exception as e:
        logger.warning(f"Failed to stop workers on shutdown: {e}")


app = FastAPI(
    title="hoodyfarmkr-cctv API",
    description="SmartLife CCTV (ONVIF) stream ingestion, OCI data pipeline & Gemini AI multimodal service",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "X-Correlation-ID", "Content-Type"],
)


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    incoming_cid = request.headers.get("X-Correlation-ID")
    cid = set_correlation_id(incoming_cid)
    response: Response = await call_next(request)
    response.headers["X-Correlation-ID"] = cid
    return response


_auth = [Depends(require_api_key)]
app.include_router(camera_router, dependencies=_auth)
app.include_router(pipeline_router, dependencies=_auth)
app.include_router(gemini_router, dependencies=_auth)
app.include_router(media_router)


@app.get("/health", tags=["Health"])
def health_check() -> Dict[str, Any]:
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
        "farm_id": settings.FARM_ID,
        "scheduler_running": scheduler.is_running,
        "pipeline": worker_manager.get_health_summary(),
    }


@app.get("/metrics", response_class=PlainTextResponse, tags=["Observability"], dependencies=_auth)
def prometheus_metrics() -> str:
    telemetry = worker_manager.get_telemetry()
    return render_prometheus_metrics(telemetry, app_name=settings.APP_NAME)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=settings.PORT, reload=True)
