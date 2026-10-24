import asyncio
import json
import logging
import os
import random
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

# Keep allocated buffers alive so /eat really consumes memory.
_ALLOCATIONS: list[bytearray] = []


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        span_context = trace.get_current_span().get_span_context()
        trace_id = format(span_context.trace_id, "032x") if span_context.is_valid else None
        return json.dumps({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "level": record.levelname,
            "message": record.getMessage(),
            "trace_id": trace_id,
            "logger": record.name,
        }, ensure_ascii=False)


logging.basicConfig(level=logging.INFO, handlers=[logging.StreamHandler()])
logger = logging.getLogger("api")
logging.root.handlers[0].setFormatter(JSONFormatter())

provider = TracerProvider(resource=Resource.create({"service.name": "api"}))
otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
if otlp_endpoint:
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint)))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("api")

REQUESTS = Counter("api_requests_total", "Total number of HTTP requests", ["method", "endpoint", "status"])
ERRORS = Counter("api_errors_total", "Total number of HTTP 5xx responses", ["endpoint"])
DURATION = Histogram(
    "api_request_duration_seconds", "HTTP request duration in seconds",
    ["method", "endpoint"], buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10)
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("API service starting")
    yield
    logger.info("API service stopping")
    provider.force_flush()
    provider.shutdown()


app = FastAPI(title="MyDocker Lab API", lifespan=lifespan)


@app.middleware("http")
async def observe_requests(request: Request, call_next):
    path = request.url.path
    if path == "/metrics":
        return await call_next(request)
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception:
        logger.exception("Unhandled request exception")
        raise
    finally:
        elapsed = time.perf_counter() - started
        endpoint = path if path in {"/health", "/fail", "/slow", "/load", "/eat", "/burn"} else "other"
        REQUESTS.labels(request.method, endpoint, str(status_code)).inc()
        DURATION.labels(request.method, endpoint).observe(elapsed)
        if status_code >= 500:
            ERRORS.labels(endpoint).inc()
        logger.info("%s %s completed status=%s duration=%.4f", request.method, endpoint, status_code, elapsed)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/eat")
async def eat(mb: int):
    if mb < 1 or mb > 2048:
        raise HTTPException(
            status_code=400,
            detail="mb must be between 1 and 2048",
        )

    try:
        # Записываем данные в каждый мегабайт,
        # чтобы ОС действительно выделила физическую память.
        block = bytearray(mb * 1024 * 1024)

        for offset in range(0, len(block), 4096):
            block[offset] = 1

        _allocations.append(block)

    except MemoryError:
        raise HTTPException(
            status_code=500,
            detail="Memory allocation failed",
        )

    return {
        "allocated_mb": mb,
        "total_allocations": len(_allocations),
    }


@app.get("/burn")
async def burn():
    while True:
        pass


@app.get("/fail")
async def fail():
    span = trace.get_current_span()
    span.set_status(Status(StatusCode.ERROR, "Intentional test error"))
    span.set_attribute("error.type", "intentional_test_error")
    logger.error("Intentional test error on /fail")
    return JSONResponse(status_code=500, content={"error": "Intentional test error"})


@app.get("/slow")
async def slow():
    delay = random.uniform(1, 3)
    with tracer.start_as_current_span("slow-op") as span:
        span.set_attribute("slow.delay_seconds", delay)
        await asyncio.sleep(delay)
    return {"status": "ok", "delay_seconds": round(delay, 2)}


@app.get("/load")
async def load():
    count = 30
    url = os.getenv("SELF_URL", "http://127.0.0.1:8000")
    async with httpx.AsyncClient(base_url=url, timeout=10) as client:
        results = await asyncio.gather(*(client.get("/health") for _ in range(count)), return_exceptions=True)
    succeeded = sum(1 for r in results if isinstance(r, httpx.Response) and r.status_code == 200)
    return {"requests_sent": count, "successful": succeeded, "failed": count - succeeded}


@app.get("/metrics")
async def metrics():
    return PlainTextResponse(generate_latest().decode("utf-8"), media_type=CONTENT_TYPE_LATEST)


FastAPIInstrumentor.instrument_app(app)
