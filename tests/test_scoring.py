from __future__ import annotations

from kfabric.config import AppSettings
from kfabric.services.document_scoring import score_document
from kfabric.services.fragment_salvage import salvage_fragments


def test_scoring_and_salvage_are_coherent():
    settings = AppSettings()
    text = (
        "Reglement europeen 2024 applicable aux savons artisanaux. "
        "Le document mentionne REF-2024-KFABRIC et un taux de conformite de 87%. "
        "Il fournit aussi une definition: l'etiquetage INCI reste obligatoire."
    )
    score = score_document(text, "europa.eu", ["savons", "artisanaux", "conformite"], ["Contexte"], settings)
    fragments = salvage_fragments(text, ["savons", "artisanaux", "conformite"], settings)

    assert score["global_score"] >= settings.salvage_threshold
    assert len(fragments) >= 1
    assert any(fragment["fragment_type"] in {"date", "reference", "number"} for fragment in fragments)
