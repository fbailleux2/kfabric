from __future__ import annotations

from hashlib import sha256

import httpx

from kfabric.config import AppSettings
from kfabric.infra.models import CandidateDocument, Query
from kfabric.services.content_payloads import BINARY_PAYLOAD_PREFIX, unpack_binary_payload
from kfabric.services.discovery_engine import discover_candidates
from kfabric.services.document_collector import collect_document
from kfabric.services.document_parser import parse_document


SIMPLE_PDF_BYTES = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R>>endobj\n"
    b"4 0 obj<</Length 79>>stream\n"
    b"BT /F1 12 Tf 72 720 Td (Reglementation savon 2024) Tj T* "
    b"(Directive cosmetique europeenne) Tj ET\n"
    b"endstream\nendobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF"
)


def test_discovery_targets_institutional_domains():
    query = Query(
        theme="Reglementation savon artisanal",
        question="Quelles obligations recentes faut-il suivre en Europe ?",
        keywords=["savon", "europe", "conformite"],
        preferred_domains=["europa.eu", "service-public.fr", "data.gouv.fr"],
        language="fr",
        expansion_text="reglementation savon artisanal europe conformite",
    )

    candidates = discover_candidates(query)

    assert [candidate["domain"] for candidate in candidates] == [
        "europa.eu",
        "service-public.fr",
        "data.gouv.fr",
    ]
    assert candidates[0]["source_url"].startswith("https://europa.eu/search/?query=")
    assert candidates[1]["source_url"].startswith("https://www.service-public.fr/particuliers/recherche?keyword=")
    assert candidates[2]["source_url"].startswith("https://www.data.gouv.fr/fr/search/?q=")
    assert all(candidate["discovery_source"] == "targeted_domain_search" for candidate in candidates)


def test_discovery_uses_remote_connector_when_enabled(monkeypatch):
    query = Query(
        theme="Reglementation savon artisanal",
        question="Quelles obligations recentes faut-il suivre en Europe ?",
        keywords=["savon", "europe", "conformite"],
        preferred_domains=["europa.eu"],
        language="fr",
        expansion_text="reglementation savon artisanal europe conformite",
    )
    settings = AppSettings(remote_discovery_enabled=True)

    def fake_get(*args, **kwargs):
        html = """
        <html>
          <body>
            <main>
              <article class="search-result">
                <h2><a href="/documents/reglementation-savon-2024.pdf">Reglementation savon 2024</a></h2>
                <p>Directive europeenne et obligations de tracabilite pour les artisans.</p>
              </article>
              <article class="search-result">
                <h2><a href="https://europa.eu/factsheets/etiquetage-savon">Etiquetage savon artisanal</a></h2>
                <p>Fiche de synthese sur l'etiquetage et les exigences documentaires.</p>
              </article>
            </main>
          </body>
        </html>
        """
        return httpx.Response(200, headers={"content-type": "text/html"}, text=html)

    monkeypatch.setattr(httpx, "get", fake_get)

    candidates = discover_candidates(query, settings=settings)

    assert len(candidates) == 2
    assert candidates[0]["discovery_source"] == "remote_search_connector"
    assert candidates[0]["source_url"] == "https://europa.eu/documents/reglementation-savon-2024.pdf"
    assert candidates[0]["document_type"] == "pdf"
    assert candidates[0]["title"] == "Reglementation savon 2024"
    assert "tracabilite" in candidates[0]["snippet"]


def test_collect_document_preserves_pdf_payload(monkeypatch):
    candidate = CandidateDocument(
        source_url="https://example.org/demo.pdf",
        title="Demo PDF",
        snippet="",
        domain="example.org",
        document_type="pdf",
        language="fr",
        discovery_rank=1,
        discovery_source="test",
    )
    query = Query(theme="Savon", question="Question", keywords=[], language="fr")
    settings = AppSettings(remote_collection_enabled=True)

    def fake_get(*args, **kwargs):
        return httpx.Response(200, headers={"content-type": "application/pdf"}, content=SIMPLE_PDF_BYTES)

    monkeypatch.setattr(httpx, "get", fake_get)

    payload = collect_document(candidate, query, settings)

    assert payload["content_type"] == "application/pdf"
    assert payload["collection_method"] == "httpx_pdf"
    assert payload["raw_hash"] == sha256(SIMPLE_PDF_BYTES).hexdigest()
    assert payload["raw_content"].startswith(BINARY_PAYLOAD_PREFIX)
    binary_payload = unpack_binary_payload(payload["raw_content"])
    assert binary_payload is not None
    assert binary_payload.data == SIMPLE_PDF_BYTES


def test_parse_document_extracts_html_content():
    candidate = CandidateDocument(
        source_url="https://europa.eu/search/?query=savon",
        title="Titre fallback",
        snippet="",
        domain="europa.eu",
        document_type="web",
        language="fr",
        discovery_rank=1,
        discovery_source="test",
    )
    raw_html = """
    <html>
      <head><title>Reglementation savon en Europe</title></head>
      <body>
        <main>
          <h1>Obligations 2024</h1>
          <p>Les fabricants doivent verifier la tracabilite des ingredients.</p>
          <h2>Etiquetage</h2>
          <p>Le dossier documentaire doit conserver les references officielles.</p>
        </main>
      </body>
    </html>
    """

    parsed = parse_document(raw_html, "text/html", candidate)

    assert parsed["extracted_title"] == "Reglementation savon en Europe"
    assert "Obligations 2024" in parsed["normalized_text"]
    assert "Etiquetage" in parsed["headings"]
    assert parsed["extraction_method"] in {"beautifulsoup", "readability", "trafilatura"}


def test_parse_document_extracts_pdf_text():
    candidate = CandidateDocument(
        source_url="https://example.org/demo.pdf",
        title="PDF fallback",
        snippet="",
        domain="example.org",
        document_type="pdf",
        language="fr",
        discovery_rank=1,
        discovery_source="test",
    )

    # We intentionally build the payload with the helper in production tests elsewhere;
    # this test keeps the parser resilient even if the payload was persisted externally.
    from kfabric.services.content_payloads import pack_binary_payload

    parsed = parse_document(pack_binary_payload(SIMPLE_PDF_BYTES, "application/pdf", title="PDF demo"), "application/pdf", candidate)

    assert "Reglementation savon 2024" in parsed["normalized_text"]
    assert "Directive cosmetique europeenne" in parsed["normalized_text"]
    assert parsed["extraction_method"] in {"pypdf", "pdf_literal_fallback"}
