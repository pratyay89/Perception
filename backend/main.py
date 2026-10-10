from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

from app.auth.route import router as auth_router
from app.config import settings
from app.database import IS_SQLITE, engine, init_models
from app.evaluations.route import router as evaluations_router
from app.leaderboard.route import router as leaderboard_router
from app.papers.route import router as papers_router
from app.submissions.route import router as submissions_router
from app.utils.evaluator import EvaluationService
from app.utils.logging import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_models()
    logger.info(
        "Perception backend started",
        environment=settings.ENVIRONMENT,
        database="sqlite" if IS_SQLITE else "postgresql",
        llm_model=settings.GROQ_MODEL,
        llm_configured=EvaluationService.is_configured(),
    )
    if not EvaluationService.is_configured():
        logger.warning("GROQ_API_KEY is not set: everything works except AI evaluation")
    yield

    # shutdown
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
    openapi_url="/openapi.json" if settings.is_development else None,
    docs_url="/docs" if settings.is_development else None,
    redoc_url=None,
    debug=settings.is_development,
)

# The API uses bearer tokens, not cookies, so credentials are not needed and
# the list of allowed origins comes from configuration.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _printable(value):
    """Make a value safe to put in a JSON response."""
    if isinstance(value, str):
        return value.encode("utf-8", "replace").decode("utf-8")
    return value if isinstance(value, int) else str(value)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """Report what is wrong with a request without echoing it back.

    The default handler includes the rejected input in the response. That
    would return passwords to the browser, and it crashes on text that cannot
    be encoded.
    """
    errors = [
        {
            "type": _printable(error.get("type", "value_error")),
            "loc": [_printable(part) for part in error.get("loc", ())],
            "msg": _printable(error.get("msg", "Invalid value")),
        }
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(DBAPIError)
async def database_error_handler(request: Request, exc: DBAPIError):
    """Safety net: a value the database refuses is the client's mistake.

    Request schemas already reject such input; this catches anything they miss
    (PostgreSQL error class 22, "data exception") instead of answering 500.
    """
    code = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
    if isinstance(code, str) and code.startswith("22"):
        return JSONResponse(
            status_code=400, content={"detail": "The request contains invalid data"}
        )
    logger.exception("Database error", path=request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(auth_router)
app.include_router(papers_router)
app.include_router(submissions_router)
app.include_router(evaluations_router)
app.include_router(leaderboard_router)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": settings.VERSION,
        "llm_configured": EvaluationService.is_configured(),
        "llm_model": settings.GROQ_MODEL,
    }
