from __future__ import annotations

import base64
import json
from dataclasses import dataclass


BINARY_PAYLOAD_PREFIX = "__KFABRIC_BINARY__:"


@dataclass(frozen=True)
class BinaryPayload:
    media_type: str
    data: bytes
    source_url: str | None = None
    title: str | None = None


def pack_binary_payload(
    data: bytes,
    media_type: str,
    *,
    source_url: str | None = None,
    title: str | None = None,
) -> str:
    payload = {
        "media_type": media_type,
        "payload_b64": base64.b64encode(data).decode("ascii"),
        "source_url": source_url,
        "title": title,
    }
    return BINARY_PAYLOAD_PREFIX + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def unpack_binary_payload(raw_content: str) -> BinaryPayload | None:
    if not raw_content.startswith(BINARY_PAYLOAD_PREFIX):
        return None

    payload = json.loads(raw_content[len(BINARY_PAYLOAD_PREFIX) :])
    return BinaryPayload(
        media_type=str(payload.get("media_type") or "application/octet-stream"),
        data=base64.b64decode(payload["payload_b64"]),
        source_url=payload.get("source_url"),
        title=payload.get("title"),
    )
