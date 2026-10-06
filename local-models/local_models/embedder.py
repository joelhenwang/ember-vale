"""Sentence embeddings from an OpenVINO IR export of embeddinggemma.

"AUTO" (the default) is the CPU: about 22 ms per query on a Core Ultra
7 255U, plenty for the few rows a beat adds. "CPU+GPU" also compiles
for the integrated GPU and sends batches there. That is opt-in: fp16 on
the iGPU zeroed short rows in padded batches, fp32 is only ~20% faster
than the CPU, and the driver can fail with CL_OUT_OF_RESOURCES; after
any GPU failure the GPU is dropped and the CPU finishes the work. The
NPU is left out: it needs static shapes, so every text pads to full
length, and it came out slower and less faithful (top-5 0.80 vs 0.97).
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np

Kind = Literal["query", "document"]
log = logging.getLogger("local_models.embedder")

#: embeddinggemma's task prompts; queries and documents embed differently.
PREFIXES: dict[str, str] = {
    "query": "task: search result | query: ",
    "document": "title: none | text: ",
}
MAX_LENGTH = 256
BATCH = 32
#: r2: GPU in fp32 (fp16 zeroed short rows in padded batches).
REVISION = 2
#: Batches at or above this size go to the GPU when both are loaded.
GPU_FROM = 4


@dataclass
class _Compiled:
    device: str
    request: object
    output: object
    lock: threading.Lock


class Embedder:
    def __init__(self, model_dir: Path, device: str = "AUTO", cache_dir: Path | None = None):
        import openvino as ov
        from transformers import AutoTokenizer

        self.model_dir = model_dir
        #: Vectors are filed under this name; bump REVISION when output changes.
        self.name = f"{model_dir.name}-r{REVISION}"
        core = ov.Core()
        available = set(core.available_devices)
        model = core.read_model(model_dir / "openvino_model.xml")
        self._tokenizer = AutoTokenizer.from_pretrained(model_dir)
        self._inputs = [port.get_any_name() for port in model.inputs]
        choice = device.upper()
        wanted = {"AUTO": ["CPU"], "CPU+GPU": ["CPU", "GPU"]}.get(choice, [choice])
        config = {"CACHE_DIR": str(cache_dir)} if cache_dir else {}
        self._compiled: dict[str, _Compiled] = {}
        self.compile_seconds: dict[str, float] = {}
        for name in wanted:
            if name not in available:
                if choice == "CPU+GPU" and name == "GPU":
                    continue
                raise RuntimeError(f"device {name} not available (have {sorted(available)})")
            started = time.perf_counter()
            # fp16 on the iGPU zeroes short rows padded beside long ones;
            # fp32 keeps every row faithful.
            extra = {"INFERENCE_PRECISION_HINT": "f32"} if name == "GPU" else {}
            compiled = core.compile_model(model, name, {**config, **extra})
            self.compile_seconds[name] = round(time.perf_counter() - started, 1)
            output = compiled.outputs[0]
            for port in compiled.outputs:
                if "sentence_embedding" in port.get_names():
                    output = port
            self._compiled[name] = _Compiled(
                name, compiled.create_infer_request(), output, threading.Lock()
            )
        if not self._compiled:
            raise RuntimeError("no device could load the embedding model")
        self.dimension = int(self.embed(["dimension probe"], "query").shape[1])

    @property
    def devices(self) -> list[str]:
        return list(self._compiled)

    def pick(self, count: int) -> str:
        """Device for a call of ``count`` texts."""
        if count >= GPU_FROM and "GPU" in self._compiled:
            return "GPU"
        return "CPU" if "CPU" in self._compiled else next(iter(self._compiled))

    def embed(self, texts: list[str], kind: Kind) -> np.ndarray:
        """Unit-length vectors, one row per text, in the order given."""
        device = self.pick(len(texts))
        prefixed = [PREFIXES[kind] + text for text in texts]
        # Similar lengths share a batch, so little padding is computed.
        order = sorted(range(len(prefixed)), key=lambda i: len(prefixed[i]))
        vectors = np.zeros((len(prefixed), 0), dtype=np.float32)
        for start in range(0, len(order), BATCH):
            picked = order[start : start + BATCH]
            chunk = self._infer_or_fall_back(device, [prefixed[i] for i in picked])
            if vectors.shape[1] == 0:
                vectors = np.zeros((len(prefixed), chunk.shape[1]), dtype=np.float32)
            vectors[picked] = chunk
        norms = np.linalg.norm(vectors, axis=1)
        broken = [i for i, n in enumerate(norms) if not np.isfinite(n) or n < 1e-6]
        if broken and device != "CPU" and "CPU" in self._compiled:
            # Never hand out an empty vector: redo those rows on the CPU.
            vectors[broken] = self._infer("CPU", [prefixed[i] for i in broken])
            norms = np.linalg.norm(vectors, axis=1)
        if any(not np.isfinite(n) or n < 1e-6 for n in norms):
            raise RuntimeError("embedding model returned an empty vector")
        return vectors / norms[:, None]

    def _infer_or_fall_back(self, device: str, chunk: list[str]) -> np.ndarray:
        try:
            return self._infer(device, chunk)
        except RuntimeError:
            if device == "CPU" or "CPU" not in self._compiled:
                raise
            # A GPU error can leave the driver unusable: stop using it.
            log.exception("embedding on %s failed; using the CPU from now on", device)
            self._compiled.pop(device, None)
            return self._infer("CPU", chunk)

    def _infer(self, device: str, chunk: list[str]) -> np.ndarray:
        target = self._compiled[device]
        tokens = self._tokenizer(
            chunk, padding=True, truncation=True, max_length=MAX_LENGTH, return_tensors="np"
        )
        feed = {name: tokens[name] for name in self._inputs if name in tokens}
        with target.lock:
            result = target.request.infer(feed)  # type: ignore[attr-defined]
            return np.nan_to_num(np.array(result[target.output], dtype=np.float32))
