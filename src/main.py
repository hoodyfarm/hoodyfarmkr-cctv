import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any

from src.config import settings
from src.api.camera_routes import router as camera_router
from src.api.pipeline_routes import router as pipeline_router
from src.api.gemini_routes import router as gemini_router
from src.core.scheduler import scheduler

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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(camera_router)
app.include_router(pipeline_router)
app.include_router(gemini_router)

@app.on_event("startup")
def on_startup():
    logger.info(f"Starting {settings.APP_NAME} in environment: {settings.ENVIRONMENT}")
    scheduler.start()

@app.on_event("shutdown")
def on_shutdown():
    logger.info(f"Stopping {settings.APP_NAME}")
    scheduler.stop()

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
