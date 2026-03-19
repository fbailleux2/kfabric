from __future__ import annotations

import re
from hashlib import sha256

from bs4 import BeautifulSoup

from kfabric.infra.models import CandidateDocument


def parse_document(raw_content: str, content_type: str, candidate: CandidateDocument) -> dict[str, object]:
    if "html" in content_type:
        soup = BeautifulSoup(raw_content, "html.parser")
        extracted_title = soup.title.string.strip() if soup.title and soup.title.string else candidate.title
        text = soup.get_text("\n", strip=True)
        headings = [tag.get_text(" ", strip=True) for tag in soup.find_all(["h1", "h2", "h3"])][:12]
        extraction_method = "beautifulsoup"
    else:
        extracted_title = candidate.title
        text = raw_content
        headings = _extract_markdown_headings(raw_content)
        extraction_method = "plain_text"

    normalized_text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return {
        "normalized_text": normalized_text,
        "normalized_hash": sha256(normalized_text.encode("utf-8")).hexdigest(),
        "extracted_title": extracted_title,
        "headings": headings,
        "text_length": len(normalized_text),
        "extraction_method": extraction_method,
    }


def _extract_markdown_headings(raw_content: str) -> list[str]:
    headings: list[str] = []
    for line in raw_content.splitlines():
        if line.startswith("#"):
            headings.append(line.lstrip("# ").strip())
    return headings[:12]

