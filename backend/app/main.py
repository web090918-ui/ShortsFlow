import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.downloads import router as downloads_router
from app.logging_config import configure_logging
from app.processing_jobs import router as processing_jobs_router
from app.sources import router as sources_router

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(sources_router)
app.include_router(downloads_router)
app.include_router(processing_jobs_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unhandled exception while processing %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
