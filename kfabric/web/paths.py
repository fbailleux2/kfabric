from __future__ import annotations

from pathlib import Path


def resolve_web_path(*parts: str) -> Path:
    relative_path = Path(*parts)
    candidates = [
        Path(__file__).resolve().parent / relative_path,
        Path.cwd() / "kfabric" / "web" / relative_path,
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    return candidates[0].resolve()
