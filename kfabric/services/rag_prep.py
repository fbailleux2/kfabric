from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from kfabric.config import AppSettings


def prepare_index_artifact(corpus_id: str, corpus_markdown: str, settings: AppSettings) -> dict[str, object]:
    chunks = chunk_text(corpus_markdown)
    vectors = [pseudo_embedding(chunk) for chunk in chunks]
    index_dir = settings.storage_path / "indexes"
    index_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = index_dir / f"{corpus_id}.json"
    artifact_path.write_text(json.dumps({"chunks": chunks, "vectors": vectors}, ensure_ascii=True, indent=2), encoding="utf-8")
    return {
        "chunk_count": len(chunks),
        "vector_dimensions": len(vectors[0]) if vectors else 0,
        "artifact_path": str(artifact_path),
    }


def chunk_text(text: str, chunk_size: int = 420, overlap: int = 60) -> list[str]:
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = max(0, end - overlap)
    return chunks


def pseudo_embedding(text: str, dimensions: int = 16) -> list[float]:
    digest = sha256(text.encode("utf-8")).digest()
    values = []
    for index in range(dimensions):
        byte = digest[index]
        values.append(round((byte / 255.0) * 2 - 1, 4))
    return values

