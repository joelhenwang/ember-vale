"""HTTP face of the local models. Runs natively on Windows: Docker's WSL2
VM cannot reach the integrated GPU, so the API container calls this
service at host.docker.internal instead of loading models itself.

    uv run python -m local_models.server --port 8110

Environment:
    LOCAL_MODELS_EMBED_DIR   OpenVINO IR folder (default models/embeddinggemma-300m-int8)
    LOCAL_MODELS_DEVICE      AUTO (the CPU), CPU+GPU (batches on the iGPU), CPU or GPU
    LOCAL_MODELS_EXTRACT     1 to load GLiNER2.5 for /extract, 0 to skip it
"""

from __future__ import annotations

import argparse
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from local_models.embedder import Embedder
from local_models.extractor import Extractor

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("local_models")


class EmbedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    texts: list[str] = Field(min_length=1, max_length=256)
    kind: Literal["query", "document"] = "document"


class EmbedResponse(BaseModel):
    vectors: list[list[float]]
    model: str
    dimension: int
    device: str
    ms: int


class ExtractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    texts: list[str] = Field(min_length=1, max_length=64)
    #: label -> short description (GLiNER reads the description as a hint).
    labels: dict[str, str] = Field(min_length=1, max_length=16)
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)


class ExtractResponse(BaseModel):
    results: list[dict[str, list[dict[str, Any]]]]
    model: str
    ms: int


class Models:
    """Loaded in the background so /health answers while models warm up."""

    def __init__(self) -> None:
        self.embedder: Embedder | None = None
        self.extractor: Extractor | None = None
        self.errors: dict[str, str] = {}
        self.loading = True

    def load(self, embed_dir: Path, device: str, extract: bool) -> None:
        try:
            self.embedder = Embedder(embed_dir, device, cache_dir=ROOT / "ov_cache")
            log.info("embedder ready on %s", self.embedder.devices)
        except Exception as exc:  # report through /health, keep serving
            self.errors["embed"] = str(exc)[:300]
            log.exception("embedder failed to load")
        if extract:
            try:
                self.extractor = Extractor()
                log.info("extractor ready")
            except Exception as exc:
                self.errors["extract"] = str(exc)[:300]
                log.exception("extractor failed to load")
        self.loading = False


def create_app(
    embed_dir: Path | None = None, device: str | None = None, extract: bool | None = None
) -> FastAPI:
    models = Models()
    embed_dir = embed_dir or Path(
        os.environ.get("LOCAL_MODELS_EMBED_DIR", ROOT / "models" / "embeddinggemma-300m-int8")
    )
    device = device or os.environ.get("LOCAL_MODELS_DEVICE", "AUTO")
    if extract is None:
        extract = os.environ.get("LOCAL_MODELS_EXTRACT", "1") != "0"

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        threading.Thread(
            target=models.load, args=(embed_dir, device, extract), daemon=True
        ).start()
        yield

    app = FastAPI(title="Ember Vale local models", lifespan=lifespan)
    app.state.models = models

    @app.get("/health")
    def health() -> dict[str, Any]:
        embedder, extractor = models.embedder, models.extractor
        return {
            "loading": models.loading,
            "embed": None
            if embedder is None
            else {
                "model": embedder.name,
                "dimension": embedder.dimension,
                "devices": embedder.devices,
                "compile_seconds": embedder.compile_seconds,
            },
            "extract": None if extractor is None else {"model": extractor.name},
            "errors": models.errors,
        }

    @app.post("/embed")
    async def embed(body: EmbedRequest) -> EmbedResponse:
        embedder = models.embedder
        if embedder is None:
            raise HTTPException(503, "embedding model not loaded")
        if any(not text.strip() or len(text) > 4000 for text in body.texts):
            raise HTTPException(422, "texts must be non-empty and at most 4000 characters")
        started = time.perf_counter()
        vectors = await run_in_threadpool(embedder.embed, body.texts, body.kind)
        return EmbedResponse(
            vectors=[[round(float(x), 6) for x in row] for row in vectors],
            model=embedder.name,
            dimension=embedder.dimension,
            device=embedder.pick(len(body.texts)),
            ms=int((time.perf_counter() - started) * 1000),
        )

    @app.post("/extract")
    async def extract_entities(body: ExtractRequest) -> ExtractResponse:
        extractor = models.extractor
        if extractor is None:
            raise HTTPException(503, "extraction model not loaded")
        if any(not text.strip() or len(text) > 4000 for text in body.texts):
            raise HTTPException(422, "texts must be non-empty and at most 4000 characters")
        started = time.perf_counter()
        results = await run_in_threadpool(
            extractor.extract, body.texts, body.labels, body.threshold
        )
        return ExtractResponse(
            results=results,
            model=extractor.name,
            ms=int((time.perf_counter() - started) * 1000),
        )

    return app


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8110)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
