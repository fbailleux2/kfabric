from __future__ import annotations

from pathlib import Path


def test_full_api_flow(client):
    create_response = client.post(
        "/api/v1/queries",
        json={
            "theme": "Reglementation savon artisanal",
            "question": "Quelles obligations recentes faut-il suivre en Europe ?",
            "keywords": ["savon", "europe", "conformite"],
            "preferred_domains": ["europa.eu", "data.gouv.fr"],
        },
    )
    assert create_response.status_code == 200
    query_id = create_response.json()["id"]

    discover_response = client.post(f"/api/v1/queries/{query_id}:discover")
    assert discover_response.status_code == 200
    candidates = discover_response.json()
    assert len(candidates) >= 2

    collect_response = client.post(f"/api/v1/candidates/{candidates[0]['id']}:collect")
    assert collect_response.status_code == 200
    collected_document_id = collect_response.json()["collected_document_id"]

    analyze_response = client.post(f"/api/v1/documents/{collected_document_id}:analyze")
    assert analyze_response.status_code == 200
    analyze_payload = analyze_response.json()
    assert analyze_payload["global_score"] >= 0

    fragments_response = client.get(f"/api/v1/fragments?query_id={query_id}")
    assert fragments_response.status_code == 200
    fragments = fragments_response.json()
    assert len(fragments) >= 1

    consolidate_response = client.post("/api/v1/fragments:consolidate", json={"query_id": query_id})
    assert consolidate_response.status_code == 200
    assert len(consolidate_response.json()) >= 1

    synthesis_response = client.post("/api/v1/syntheses", json={"query_id": query_id})
    assert synthesis_response.status_code == 200
    synthesis_id = synthesis_response.json()["id"]
    assert synthesis_id.startswith("syn_")

    corpus_response = client.post(f"/api/v1/queries/{query_id}:build-corpus")
    assert corpus_response.status_code == 200
    corpus_id = corpus_response.json()["id"]
    assert "Resume executif" in corpus_response.json()["corpus_markdown"]
    assert "Dossier principal" in corpus_response.json()["corpus_markdown"]

    export_markdown_response = client.get(f"/api/v1/corpora/{corpus_id}:export?format=markdown")
    assert export_markdown_response.status_code == 200
    assert export_markdown_response.headers["content-type"].startswith("text/markdown")
    assert "KFabric Corpus" in export_markdown_response.text

    export_html_response = client.get(f"/api/v1/corpora/{corpus_id}:export?format=html")
    assert export_html_response.status_code == 200
    assert export_html_response.headers["content-type"].startswith("text/html")
    assert "<html" in export_html_response.text.lower()

    prepare_index_response = client.post(f"/api/v1/corpora/{corpus_id}:prepare-index")
    assert prepare_index_response.status_code == 200
    artifact_path = Path(prepare_index_response.json()["artifact_path"])
    assert artifact_path.exists()

    read_corpus_response = client.get(f"/api/v1/corpora/{corpus_id}")
    assert read_corpus_response.status_code == 200
    assert read_corpus_response.json()["index_ready"] is True


def test_web_views_render(client):
    home = client.get("/")
    assert home.status_code == 200
    assert "KFabric" in home.text

    response = client.post(
        "/web/queries",
        data={
            "theme": "Corpus cosmetique",
            "question": "Quels textes prioriser ?",
            "keywords": "cosmetique, europe",
            "preferred_domains": "europa.eu, data.gouv.fr",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    dashboard = client.get(response.headers["location"])
    assert dashboard.status_code == 200
    assert "Documents candidats" in dashboard.text


def test_web_corpus_export_views(client):
    create_response = client.post(
        "/api/v1/queries",
        json={
            "theme": "Corpus demonstration",
            "question": "Quels documents retenir ?",
            "keywords": ["corpus", "demo"],
            "preferred_domains": ["europa.eu"],
        },
    )
    query_id = create_response.json()["id"]

    discover_response = client.post(f"/api/v1/queries/{query_id}:discover")
    candidate = discover_response.json()[0]
    collected_id = client.post(f"/api/v1/candidates/{candidate['id']}:collect").json()["collected_document_id"]
    client.post(f"/api/v1/documents/{collected_id}:analyze")
    corpus_id = client.post(f"/api/v1/queries/{query_id}:build-corpus").json()["id"]

    html_response = client.get(f"/web/corpora/{corpus_id}/export.html")
    assert html_response.status_code == 200
    assert "Export corpus KFabric" in html_response.text

    markdown_response = client.get(f"/web/corpora/{corpus_id}/export.md")
    assert markdown_response.status_code == 200
    assert markdown_response.headers["content-type"].startswith("text/markdown")
    assert "KFabric Corpus" in markdown_response.text
