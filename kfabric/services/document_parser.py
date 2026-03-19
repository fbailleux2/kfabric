from __future__ import annotations

import io
import re
from hashlib import sha256

from bs4 import BeautifulSoup

from kfabric.infra.models import CandidateDocument
from kfabric.services.content_payloads import BinaryPayload, unpack_binary_payload

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover - optional dependency
    PdfReader = None

try:
    import trafilatura
except Exception:  # pragma: no cover - optional dependency
    trafilatura = None

try:
    from readability import Document as ReadabilityDocument
except Exception:  # pragma: no cover - optional dependency
    ReadabilityDocument = None


def parse_document(raw_content: str, content_type: str, candidate: CandidateDocument) -> dict[str, object]:
    binary_payload = unpack_binary_payload(raw_content)
    if binary_payload:
        extracted_title, text, headings, extraction_method = _parse_binary_payload(binary_payload, candidate)
    elif "html" in content_type or _looks_like_html(raw_content):
        extracted_title, text, headings, extraction_method = _parse_html_document(raw_content, candidate)
    else:
        extracted_title, text, headings, extraction_method = _parse_text_document(raw_content, candidate)

    normalized_text = _normalize_text(text)
    if not normalized_text:
        normalized_text = candidate.snippet or candidate.title
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


def _parse_binary_payload(
    payload: BinaryPayload,
    candidate: CandidateDocument,
) -> tuple[str, str, list[str], str]:
    if "pdf" in payload.media_type:
        return _parse_pdf_document(payload.data, candidate, payload.title)
    text = payload.data.decode("utf-8", errors="ignore")
    return candidate.title, text, _extract_markdown_headings(text), "binary_text"


def _parse_pdf_document(
    raw_pdf: bytes,
    candidate: CandidateDocument,
    payload_title: str | None,
) -> tuple[str, str, list[str], str]:
    extracted_title = payload_title or candidate.title
    if PdfReader is not None:
        try:
            reader = PdfReader(io.BytesIO(raw_pdf))
            metadata_title = _extract_pdf_metadata_title(reader)
            if metadata_title:
                extracted_title = metadata_title
            text = "\n\n".join((page.extract_text() or "").strip() for page in reader.pages).strip()
            if text:
                return extracted_title, text, _extract_candidate_headings(text), "pypdf"
        except Exception:
            pass

    literal_text = _extract_pdf_literal_text(raw_pdf)
    return extracted_title, literal_text or candidate.snippet or candidate.title, _extract_candidate_headings(literal_text), "pdf_literal_fallback"


def _extract_pdf_metadata_title(reader: PdfReader) -> str | None:
    metadata = reader.metadata
    if metadata is None:
        return None
    if hasattr(metadata, "title") and metadata.title:
        return str(metadata.title)
    if isinstance(metadata, dict):
        title = metadata.get("/Title") or metadata.get("title")
        if title:
            return str(title)
    return None


def _extract_pdf_literal_text(raw_pdf: bytes) -> str:
    decoded = raw_pdf.decode("latin-1", errors="ignore")
    literal_matches = re.findall(r"\(((?:\\.|[^\\()]){3,})\)\s*T[Jj]", decoded)
    if not literal_matches:
        literal_matches = re.findall(r"\(((?:\\.|[^\\()]){3,})\)", decoded)

    cleaned_fragments: list[str] = []
    for match in literal_matches:
        fragment = match.strip()
        fragment = (
            fragment.replace(r"\(", "(")
            .replace(r"\)", ")")
            .replace(r"\n", "\n")
            .replace(r"\r", "")
            .replace(r"\t", "\t")
            .replace(r"\\", "\\")
        )
        fragment = re.sub(r"\s{2,}", " ", fragment).strip()
        if fragment and fragment not in cleaned_fragments:
            cleaned_fragments.append(fragment)
    return "\n".join(cleaned_fragments[:24])


def _parse_html_document(raw_content: str, candidate: CandidateDocument) -> tuple[str, str, list[str], str]:
    soup = BeautifulSoup(raw_content, "html.parser")
    extracted_title = soup.title.string.strip() if soup.title and soup.title.string else candidate.title
    headings = _extract_html_headings(soup)

    if trafilatura is not None:
        try:
            extracted = trafilatura.extract(
                raw_content,
                include_comments=False,
                include_links=False,
                include_images=False,
                favor_precision=True,
                target_language=candidate.language or None,
            )
            if extracted:
                return extracted_title, extracted, headings or _extract_candidate_headings(extracted), "trafilatura"
        except Exception:
            pass

    if ReadabilityDocument is not None:
        try:
            readable = ReadabilityDocument(raw_content)
            summary = readable.summary()
            readable_soup = BeautifulSoup(summary, "html.parser")
            readable_text = readable_soup.get_text("\n", strip=True)
            if readable.short_title():
                extracted_title = readable.short_title()
            if readable_text:
                return extracted_title, readable_text, headings or _extract_candidate_headings(readable_text), "readability"
        except Exception:
            pass

    for tag in soup.select("script, style, noscript, svg, form, nav, footer"):
        tag.decompose()
    scope = soup.select_one("article, main, [role='main'], .article, .content, #content") or soup.body or soup
    text = scope.get_text("\n", strip=True)
    return extracted_title, text, headings or _extract_candidate_headings(text), "beautifulsoup"


def _parse_text_document(raw_content: str, candidate: CandidateDocument) -> tuple[str, str, list[str], str]:
    return candidate.title, raw_content, _extract_markdown_headings(raw_content) or _extract_candidate_headings(raw_content), "plain_text"


def _extract_html_headings(soup: BeautifulSoup) -> list[str]:
    headings: list[str] = []
    for tag in soup.find_all(["h1", "h2", "h3"]):
        text = tag.get_text(" ", strip=True)
        if text and text not in headings:
            headings.append(text)
    return headings[:12]


def _extract_candidate_headings(raw_content: str) -> list[str]:
    headings: list[str] = []
    for line in raw_content.splitlines():
        cleaned = line.strip(" -*\t")
        if not cleaned:
            continue
        if cleaned.endswith(":"):
            headings.append(cleaned.rstrip(":"))
        elif cleaned.isupper() and len(cleaned) <= 80:
            headings.append(cleaned.title())
        elif len(cleaned.split()) <= 8 and 8 <= len(cleaned) <= 80 and cleaned[:1].isupper():
            headings.append(cleaned)
        if len(headings) >= 12:
            break
    deduplicated: list[str] = []
    for heading in headings:
        if heading not in deduplicated:
            deduplicated.append(heading)
    return deduplicated[:12]


def _normalize_text(text: str) -> str:
    normalized_lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    filtered_lines = [line for line in normalized_lines if line]
    normalized_text = "\n".join(filtered_lines)
    return re.sub(r"\n{3,}", "\n\n", normalized_text).strip()


def _looks_like_html(raw_content: str) -> bool:
    sample = raw_content[:512].lower()
    return "<html" in sample or "<body" in sample or "<article" in sample or "<main" in sample
