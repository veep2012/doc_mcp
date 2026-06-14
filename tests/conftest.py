import hashlib
import re
from pathlib import Path

import pytest

import docmcp.vector_index as vector_index


REPO_ROOT = Path(__file__).resolve().parents[1]


class _FakeTextEmbedding:
    def __init__(self, model_name: str):
        self.model_name = model_name

    def embed(self, texts):
        return [self._embed_text(text) for text in texts]

    @staticmethod
    def _embed_text(text: str) -> list[float]:
        dimensions = 8
        vector = [0.0] * dimensions
        tokens = re.findall(r"[A-Za-z0-9_]+", text.lower())
        if not tokens:
            vector[0] = 1.0
            return vector

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            primary = int.from_bytes(digest[:4], "little") % dimensions
            secondary = int.from_bytes(digest[4:8], "little") % dimensions
            sign = -1.0 if digest[8] & 1 else 1.0
            weight = 1.0 + (digest[9] / 255.0)
            vector[primary] += sign * weight
            vector[secondary] += (weight / 2.0) * (-sign)

        norm = sum(component * component for component in vector) ** 0.5
        if norm == 0:
            vector[0] = 1.0
            return vector
        return [component / norm for component in vector]


@pytest.fixture(autouse=True)
def _fake_fastembed_backend(monkeypatch):
    monkeypatch.setattr(
        vector_index,
        "_load_text_embedding_backend",
        lambda model_name: _FakeTextEmbedding(model_name),
    )
