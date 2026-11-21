"""
EXAMFLOW – FastAPI Application Entry Point
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.api.v1 import router as api_v1_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    import logging
    logging.basicConfig(level=settings.LOG_LEVEL)
    yield
    # Shutdown (close connections, etc.)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "EXAMFLOW – Online Exam Proctoring Result Engine\n"
        "PS-072: Negative Marking, Sectional Cut-offs, Shift Normalisation"
    ),
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    lifespan=lifespan,
)

# ------------------------------------------------------------------ #
# CORS
# ------------------------------------------------------------------ #
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------ #
# Exception handlers
# ------------------------------------------------------------------ #

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "Validation error", "detail": exc.errors(), "code": "VALIDATION_ERROR"},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    import logging
    logging.getLogger(__name__).exception("Unhandled exception")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Internal server error", "code": "INTERNAL_ERROR"},
    )

# ------------------------------------------------------------------ #
# Routers
# ------------------------------------------------------------------ #
app.include_router(api_v1_router, prefix="/api/v1")


# ------------------------------------------------------------------ #
# Health endpoint
# ------------------------------------------------------------------ #
@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "version": settings.APP_VERSION, "app": settings.APP_NAME}
