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


def test_discovery_extracts_eurlex_specific_results(monkeypatch):
    query = Query(
        theme="Cosmetiques",
        question="Quels textes europeens s'appliquent ?",
        keywords=["cosmetique", "europe"],
        preferred_domains=["eur-lex.europa.eu"],
        language="fr",
        expansion_text="cosmetique europe textes officiels",
    )
    settings = AppSettings(remote_discovery_enabled=True)

    def fake_get(*args, **kwargs):
        html = """
        <html>
          <body>
            <div class="SearchResult">
              <h2 class="SearchResult-title">
                <a href="/legal-content/FR/TXT/?uri=CELEX:32009R1223">Reglement cosmetique 1223/2009</a>
              </h2>
              <div class="SearchResult-content">Texte consolide sur les obligations de mise sur le marche.</div>
              <a href="/legal-content/FR/TXT/PDF/?uri=CELEX:32009R1223">PDF</a>
            </div>
          </body>
        </html>
        """
        return httpx.Response(200, headers={"content-type": "text/html"}, text=html)

    monkeypatch.setattr(httpx, "get", fake_get)

    candidates = discover_candidates(query, settings=settings)

    assert len(candidates) == 1
    assert candidates[0]["source_url"] == "https://eur-lex.europa.eu/legal-content/FR/TXT/PDF/?uri=CELEX:32009R1223"
    assert candidates[0]["document_type"] == "pdf"
    assert candidates[0]["title"] == "Reglement cosmetique 1223/2009"
    assert candidates[0]["domain"] == "eur-lex.europa.eu"


def test_discovery_extracts_datagouv_specific_results(monkeypatch):
    query = Query(
        theme="Substances cosmetiques",
        question="Quelles donnees publiques suivre ?",
        keywords=["cosmetique", "donnees"],
        preferred_domains=["data.gouv.fr"],
        language="fr",
        expansion_text="substances cosmetiques donnees publiques",
    )
    settings = AppSettings(remote_discovery_enabled=True)

    def fake_get(*args, **kwargs):
        html = """
        <html>
          <body>
            <article class="card">
              <h2 class="fr-card__title">
                <a href="/fr/datasets/base-ingredients-cosmetiques/">Base ingredients cosmetiques</a>
              </h2>
              <p class="fr-card__desc">Jeu de donnees public sur les ingredients, metadonnees et references.</p>
            </article>
          </body>
        </html>
        """
        return httpx.Response(200, headers={"content-type": "text/html"}, text=html)

    monkeypatch.setattr(httpx, "get", fake_get)

    candidates = discover_candidates(query, settings=settings)

    assert len(candidates) == 1
    assert candidates[0]["source_url"] == "https://www.data.gouv.fr/fr/datasets/base-ingredients-cosmetiques/"
    assert candidates[0]["document_type"] == "web"
    assert candidates[0]["title"] == "Base ingredients cosmetiques"
    assert "metadonnees" in candidates[0]["snippet"]


def test_discovery_extracts_hal_specific_results(monkeypatch):
    query = Query(
        theme="Evaluation toxicologique",
        question="Quels travaux scientifiques recuperer ?",
        keywords=["toxicologie", "evaluation"],
        preferred_domains=["hal.science"],
        language="fr",
        expansion_text="evaluation toxicologique travaux scientifiques",
    )
    settings = AppSettings(remote_discovery_enabled=True)

    def fake_get(*args, **kwargs):
        html = """
        <html>
          <body>
            <article class="result-item">
              <h2 class="result-title"><a href="/hal-04777777v1">Evaluation toxicologique appliquee</a></h2>
              <div class="result-authors">A. Martin, C. Dupont</div>
              <div class="abstract">Resume scientifique sur les methodes de qualification et de preuve.</div>
              <a href="/hal-04777777v1/document">PDF</a>
            </article>
          </body>
        </html>
        """
        return httpx.Response(200, headers={"content-type": "text/html"}, text=html)

    monkeypatch.setattr(httpx, "get", fake_get)

    candidates = discover_candidates(query, settings=settings)

    assert len(candidates) == 1
    assert candidates[0]["source_url"] == "https://hal.science/hal-04777777v1/document"
    assert candidates[0]["document_type"] == "pdf"
    assert candidates[0]["title"] == "Evaluation toxicologique appliquee"
    assert "Resume scientifique" in candidates[0]["snippet"]


def test_discovery_extracts_legifrance_specific_results(monkeypatch):
    query = Query(
        theme="Savon artisanal",
        question="Quels textes francais s'appliquent ?",
        keywords=["savon", "france"],
        preferred_domains=["legifrance.gouv.fr"],
        language="fr",
        expansion_text="savon artisanal textes francais",
    )
    settings = AppSettings(remote_discovery_enabled=True)

    def fake_get(*args, **kwargs):
        html = """
        <html>
          <body>
            <div class="search-results__item">
              <h2><a href="/jorf/id/JORFTEXT000000111111">Arrete relatif a la fabrication artisanale</a></h2>
              <p class="search-results__content">Texte reglementaire sur la fabrication, l'etiquetage et la tracabilite.</p>
            </div>
          </body>
        </html>
        """
        return httpx.Response(200, headers={"content-type": "text/html"}, text=html)

    monkeypatch.setattr(httpx, "get", fake_get)

    candidates = discover_candidates(query, settings=settings)

    assert len(candidates) == 1
    assert candidates[0]["source_url"] == "https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000000111111"
    assert candidates[0]["document_type"] == "web"
    assert candidates[0]["title"] == "Arrete relatif a la fabrication artisanale"
    assert "tracabilite" in candidates[0]["snippet"]


def test_discovery_extracts_servicepublic_specific_results(monkeypatch):
    query = Query(
        theme="Formalites cosmetiques",
        question="Quelles demarches administratives suivre ?",
        keywords=["cosmetique", "demarches"],
        preferred_domains=["service-public.fr"],
        language="fr",
        expansion_text="formalites cosmetiques demarches administratives",
    )
    settings = AppSettings(remote_discovery_enabled=True)

    def fake_get(*args, **kwargs):
        html = """
        <html>
          <body>
            <article class="fr-card">
              <h2 class="fr-card__title">
                <a href="/particuliers/vosdroits/F35732">Demarches pour la mise sur le marche</a>
              </h2>
              <p class="fr-card__desc">Guide administratif sur les obligations, formulaires et pieces a conserver.</p>
            </article>
          </body>
        </html>
        """
        return httpx.Response(200, headers={"content-type": "text/html"}, text=html)

    monkeypatch.setattr(httpx, "get", fake_get)

    candidates = discover_candidates(query, settings=settings)

    assert len(candidates) == 1
    assert candidates[0]["source_url"] == "https://www.service-public.fr/particuliers/vosdroits/F35732"
    assert candidates[0]["document_type"] == "web"
    assert candidates[0]["title"] == "Demarches pour la mise sur le marche"
    assert "formulaires" in candidates[0]["snippet"]


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


def test_parse_document_extracts_eurlex_specific_html():
    candidate = CandidateDocument(
        source_url="https://eur-lex.europa.eu/legal-content/FR/TXT/?uri=CELEX:32009R1223",
        title="Titre fallback",
        snippet="",
        domain="eur-lex.europa.eu",
        document_type="web",
        language="fr",
        discovery_rank=1,
        discovery_source="test",
    )
    raw_html = """
    <html>
      <body>
        <main>
          <h1 class="eli-main-title">Reglement cosmetique 1223/2009</h1>
          <dl class="eli-data">
            <dt>CELEX</dt><dd>32009R1223</dd>
            <dt>Date</dt><dd>30/11/2009</dd>
          </dl>
          <div id="text">
            <h2>Article 1</h2>
            <p>Le present reglement fixe les regles de mise sur le marche.</p>
          </div>
        </main>
      </body>
    </html>
    """

    parsed = parse_document(raw_html, "text/html", candidate)

    assert parsed["extraction_method"] == "eurlex_html"
    assert "CELEX: 32009R1223" in parsed["normalized_text"]
    assert "Article 1" in parsed["normalized_text"]
    assert parsed["extracted_title"] == "Reglement cosmetique 1223/2009"


def test_parse_document_extracts_datagouv_specific_html():
    candidate = CandidateDocument(
        source_url="https://www.data.gouv.fr/fr/datasets/base-ingredients-cosmetiques/",
        title="Titre fallback",
        snippet="",
        domain="data.gouv.fr",
        document_type="web",
        language="fr",
        discovery_rank=1,
        discovery_source="test",
    )
    raw_html = """
    <html>
      <body>
        <main>
          <h1>Base ingredients cosmetiques</h1>
          <p class="fr-text--lead">Jeu de donnees de reference sur les ingredients.</p>
          <section class="resource-card"><a href="/fr/datasets/r/fiche-technique.pdf">Fiche technique PDF</a></section>
        </main>
      </body>
    </html>
    """

    parsed = parse_document(raw_html, "text/html", candidate)

    assert parsed["extraction_method"] == "datagouv_html"
    assert "Jeu de donnees de reference" in parsed["normalized_text"]
    assert "Ressources : Fiche technique PDF" in parsed["normalized_text"]
    assert parsed["extracted_title"] == "Base ingredients cosmetiques"


def test_parse_document_extracts_hal_specific_html():
    candidate = CandidateDocument(
        source_url="https://hal.science/hal-04777777v1",
        title="Titre fallback",
        snippet="",
        domain="hal.science",
        document_type="web",
        language="fr",
        discovery_rank=1,
        discovery_source="test",
    )
    raw_html = """
    <html>
      <body>
        <main class="Page-content">
          <h1 class="Page-title">Evaluation toxicologique appliquee</h1>
          <div class="authors">A. Martin, C. Dupont</div>
          <div class="abstract">Analyse des criteres de preuve et du protocole experimental.</div>
        </main>
      </body>
    </html>
    """

    parsed = parse_document(raw_html, "text/html", candidate)

    assert parsed["extraction_method"] == "hal_html"
    assert "Auteurs : A. Martin, C. Dupont" in parsed["normalized_text"]
    assert "Resume : Analyse des criteres de preuve" in parsed["normalized_text"]
    assert parsed["extracted_title"] == "Evaluation toxicologique appliquee"


def test_parse_document_extracts_legifrance_specific_html():
    candidate = CandidateDocument(
        source_url="https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000000111111",
        title="Titre fallback",
        snippet="",
        domain="legifrance.gouv.fr",
        document_type="web",
        language="fr",
        discovery_rank=1,
        discovery_source="test",
    )
    raw_html = """
    <html>
      <body>
        <main>
          <h1 class="title-page">Arrete relatif a la fabrication artisanale</h1>
          <dl class="metadata">
            <dt>NOR</dt><dd>ECOI0000001A</dd>
            <dt>Date</dt><dd>12/03/2024</dd>
          </dl>
          <div class="article-body">
            Le texte fixe les regles d'etiquetage, de securite et de conservation des preuves.
          </div>
        </main>
      </body>
    </html>
    """

    parsed = parse_document(raw_html, "text/html", candidate)

    assert parsed["extraction_method"] == "legifrance_html"
    assert "NOR: ECOI0000001A" in parsed["normalized_text"]
    assert "regles d'etiquetage" in parsed["normalized_text"]
    assert parsed["extracted_title"] == "Arrete relatif a la fabrication artisanale"


def test_parse_document_extracts_servicepublic_specific_html():
    candidate = CandidateDocument(
        source_url="https://www.service-public.fr/particuliers/vosdroits/F35732",
        title="Titre fallback",
        snippet="",
        domain="service-public.fr",
        document_type="web",
        language="fr",
        discovery_rank=1,
        discovery_source="test",
    )
    raw_html = """
    <html>
      <body>
        <main class="sp-content">
          <h1 class="page-title">Demarches pour la mise sur le marche</h1>
          <p class="introduction">Cette fiche precise les obligations administratives et les justificatifs attendus.</p>
          <div class="fr-callout"><a href="/simulateur/calcul">Acceder au simulateur</a></div>
        </main>
      </body>
    </html>
    """

    parsed = parse_document(raw_html, "text/html", candidate)

    assert parsed["extraction_method"] == "servicepublic_html"
    assert "obligations administratives" in parsed["normalized_text"]
    assert "Ressources utiles : Acceder au simulateur" in parsed["normalized_text"]
    assert parsed["extracted_title"] == "Demarches pour la mise sur le marche"


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
