# Local models

Embeddings and entity extraction that run on this machine, so recall and
grounding need no paid API call. The service runs natively on Windows:
Docker's WSL2 VM cannot reach the Intel GPU or NPU, so the API container
calls it at `host.docker.internal`.

| Endpoint | Model | Where it runs | Speed (Core Ultra 7 255U) |
|---|---|---|---|
| `POST /embed` | embeddinggemma-300m, OpenVINO int8 | CPU (iGPU opt-in) | ~22 ms per query, ~1.1 s per 32 documents |
| `POST /extract` | GLiNER2.5 multi (fastino/gliner2.5-multi-v1) | CPU (PyTorch) | ~160 ms per line in batches of 8 |
| `GET /health` | — | — | — |

## Set up once

```sh
cd local-models
uv sync
uv run --extra export python -m local_models.export   # ~1.2 GB download, writes models/
```

The export uses the ungated `unsloth/embeddinggemma-300m` mirror (same
weights as `google/embeddinggemma-300m`, Gemma licence). GLiNER2.5
(Apache-2.0) downloads on first start.

## Run

```sh
uv run python -m local_models.server --port 8110
```

Then set `WORLDSIM_LOCAL_MODELS__URL=http://host.docker.internal:8110`
in the repo `.env` and rebuild the API (`docker compose up -d --build api`).
The API works with it in the background, never inside a beat:

- It embeds new observations and memories, so decision context is ranked by relevance.
- It reads new speech, attempts, intentions and rumours with GLiNER, so the director learns which places people talk about that aren't on the map. GLiNER drops the noun list's false friends ("keep an eye", "forge mark") and adds names the list can't build ("the wheelwright's shop", "the north road").

If the service stops, decisions fall back to recency and salience, and the director falls back to the noun list.

| Variable | Default | Meaning |
|---|---|---|
| `LOCAL_MODELS_DEVICE` | `AUTO` | `AUTO` (the CPU), `CPU+GPU` (batches on the iGPU), `CPU` or `GPU` |
| `LOCAL_MODELS_EMBED_DIR` | `models/embeddinggemma-300m-int8` | OpenVINO IR folder |
| `LOCAL_MODELS_EXTRACT` | `1` | `0` skips loading GLiNER |

The server listens on 127.0.0.1 only; Docker Desktop still reaches it
through `host.docker.internal`.

## Why these choices (measured 2026-10-06)

Against full-precision PyTorch on 400 real observation lines:

| Variant | 1 query | 32 documents | Top-5 agreement |
|---|---|---|---|
| fp32 PyTorch, CPU | 102 ms | 3.3 s | — |
| int8, CPU | 22 ms | 1.1 s | 0.97 |
| int8, GPU | 28 ms | 0.47 s | 0.97 |
| int8, NPU | 29 ms | 0.93 s | 0.80 |
| int4, any | 22–34 ms | 0.45–1.2 s | 0.88–0.93 |

- The iGPU is opt-in. Its fp16 numbers above hide a fault: short rows padded beside long ones came back as all-zero vectors. In fp32 it is only about 20% faster than the CPU (541 ms against 659 ms for a mixed batch of 32). Under load the driver also failed with `CL_OUT_OF_RESOURCES`, and the GPU stayed broken until restart. Indexing adds a few rows per beat, so the CPU is plenty. With `CPU+GPU`, any GPU failure drops the GPU and the CPU finishes the batch.
- The NPU needs fixed input shapes, so every text pads to full length. That makes it slower and less faithful here.
- int4 loses quality for no speed gain.
- GLiNER's own `quantize=True` is about 8× slower on this CPU.
