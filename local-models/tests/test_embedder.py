"""Embedder checks against the real exported model (skipped when it is absent)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from local_models.embedder import Embedder

MODEL = Path(__file__).resolve().parent.parent / "models" / "embeddinggemma-300m-int8"
pytestmark = pytest.mark.skipif(not MODEL.exists(), reason="model not exported")

SHORT = "Ash waits"
LONG = (
    "Wren replies to Ash: a much longer sentence about the cart wheel stuck in the "
    "mud by the mill, and who will brace it while the other heaves"
)


@pytest.fixture(scope="module")
def auto() -> Embedder:
    return Embedder(MODEL, "CPU+GPU")


@pytest.fixture(scope="module")
def cpu() -> Embedder:
    return Embedder(MODEL, "CPU")


def test_short_rows_in_a_padded_batch_stay_faithful(auto: Embedder, cpu: Embedder) -> None:
    # A batch this size runs on the GPU when there is one; fp16 used to
    # return all-zero vectors for the short rows.
    texts = [SHORT, SHORT, *[LONG] * 30]
    batch = auto.embed(texts, "document")
    alone = cpu.embed([SHORT, LONG], "document")
    norms = np.linalg.norm(batch, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-4)
    assert float(batch[0] @ alone[0]) > 0.99
    assert float(batch[-1] @ alone[1]) > 0.99


def test_order_is_kept_when_batches_sort_by_length(auto: Embedder) -> None:
    texts = [LONG, SHORT, "The silver locket", LONG + " again"] * 3
    batch = auto.embed(texts, "document")
    one_by_one = np.vstack([auto.embed([t], "document") for t in texts])
    assert np.allclose(np.sum(batch * one_by_one, axis=1), 1.0, atol=1e-2)


def test_queries_and_documents_differ(auto: Embedder) -> None:
    query = auto.embed(["Where is the purse?"], "query")[0]
    document = auto.embed(["Where is the purse?"], "document")[0]
    assert float(query @ document) < 0.999
