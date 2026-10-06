"""Entity spans with GLiNER2.5 (fastino/gliner2.5-multi-v1) on the CPU.

About 230 ms per line on a Core Ultra 7 255U. The library's own
``quantize=True`` is about eight times slower on this CPU, so it stays
off. Labels can carry a description, which GLiNER reads as a hint.
"""

from __future__ import annotations

import threading
from typing import Any

MODEL_ID = "fastino/gliner2.5-multi-v1"


class Extractor:
    def __init__(self, model_id: str = MODEL_ID):
        from gliner2 import AutoExtractor

        self.name = model_id
        self._model = AutoExtractor.from_pretrained(model_id, map_location="cpu")
        self._lock = threading.Lock()

    def extract(
        self, texts: list[str], labels: dict[str, str], threshold: float
    ) -> list[dict[str, list[dict[str, Any]]]]:
        """Per text: label -> spans with text, start, end and confidence."""
        out: list[dict[str, list[dict[str, Any]]]] = []
        with self._lock:
            for text in texts:
                found = self._model.extract_entities(
                    text,
                    labels,
                    threshold=threshold,
                    include_confidence=True,
                    include_spans=True,
                )
                entities = found.get("entities", {}) if isinstance(found, dict) else {}
                out.append(
                    {
                        label: [
                            {
                                "text": span["text"],
                                "start": int(span["start"]),
                                "end": int(span["end"]),
                                "confidence": round(float(span["confidence"]), 3),
                            }
                            for span in spans
                            if isinstance(span, dict)
                        ]
                        for label, spans in entities.items()
                    }
                )
        return out
