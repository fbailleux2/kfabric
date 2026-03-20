# Session Handoff KFabric

Cette note sert de mémoire de travail rapide pour reprendre `kfabric` sans
ré-explorer tout le dépôt.

## 1. Vue d'ensemble

- `kfabric` est une usine de corpus documentaire Python-first.
- Trois surfaces principales partagent le même coeur métier :
  - API REST FastAPI
  - UI web Jinja2/HTMX
  - surface MCP
- Point d'entrée API : `kfabric/api/app.py`
- Point d'entrée worker : `kfabric/main.py`
- Orchestrateur principal : `kfabric/services/orchestrator.py`
- Registry MCP / async tooling : `kfabric/mcp/registry.py`

## 2. Ce qui a été engagé dans cette session

- Passage réel en mode async broker-only.
- Parité MCP étendue avec plus d'outils métier.
- Tableau de bord web capable de suivre les runs async.
- Améliorations discovery / collecte / parsing / scoring.
- Connecteurs renforcés pour `arXiv` et `GitHub`.
- Console `/ops` ajoutée.
- Correction de plusieurs problèmes bloquants Docker/UI.

## 3. Etat actuel important

- La stack Docker fonctionne maintenant avec :
  - `postgres`
  - `redis`
  - `rabbitmq`
  - `qdrant`
  - `migrate`
  - `api`
  - `worker`
- Le mode async ne retombe plus sur un fallback local.
- Si le broker ne répond pas, le `ToolRun` passe en `failed`.
- Les services Docker parlent entre eux via :
  - `postgres`
  - `redis`
  - `rabbitmq`
  - `qdrant`
- Il ne faut pas laisser Compose hériter d'URLs `localhost` pour les
  communications inter-conteneurs.

## 4. Bugs bloquants corrigés

- `kfabric-migrate` ne trouvait pas `alembic.ini` dans l'image Docker.
  - Correction dans `kfabric/main.py`
- L'API ne trouvait pas les assets web (`web/static`, templates) une fois le
  paquet installé.
  - Correction via `kfabric/web/paths.py`
  - Packaging mis à jour dans `pyproject.toml`
- Le worker Celery plantait sur une API obsolète de `celery.bin.worker`.
  - Correction dans `kfabric/main.py`
- En test, Celery eager dépendait encore du backend Redis.
  - Correction dans `kfabric/workers/celery_app.py`
  - Reconfiguration explicite dans `tests/conftest.py`
- Le frontend web générait des erreurs CSP à cause d'Alpine.
  - Alpine retiré du layout
  - Le checkbox "Mode sécurisé" est maintenant statique
- `favicon.ico` renvoyait `404`.
  - Redirect vers `/static/favicon.svg`

## 5. Validation réellement faite

- Tests ciblés passés :
  - `tests/test_celery_app.py`
  - `tests/test_main.py`
  - `tests/test_web_paths.py`
  - `tests/test_mcp_contracts.py`
  - `tests/test_api_flow.py`
  - `tests/test_security.py`
- Validation réelle de la stack :
  - `docker-compose up -d`
  - `docker-compose ps`
  - readiness HTTP `200`
- Validation UI Playwright :
  - bootstrap du premier admin
  - création d'une requête
  - run `discover_documents` en async -> `succeeded`
  - clic `Collecter async` -> `succeeded`
- Validation frontend finale :
  - plus de `404` sur `/favicon.ico`
  - plus d'erreurs console Alpine/CSP sur `/auth` puis `/`

## 6. Commandes de relance utiles

Depuis la racine du repo :

```bash
docker-compose up -d
docker-compose ps
docker-compose logs -f api worker rabbitmq
```

Checks utiles :

```bash
curl -sv http://127.0.0.1:8001/api/v1/readiness
curl -sv http://127.0.0.1:8001/favicon.ico
```

Tests ciblés utiles :

```bash
./.venv/bin/pytest -q tests/test_celery_app.py tests/test_main.py tests/test_web_paths.py tests/test_mcp_contracts.py
./.venv/bin/pytest -q tests/test_api_flow.py tests/test_security.py
```

## 7. Fichiers clés à relire en priorité

- `README.md`
- `docs/v1-runbook.md`
- `docker-compose.yml`
- `kfabric/api/app.py`
- `kfabric/main.py`
- `kfabric/workers/celery_app.py`
- `kfabric/mcp/registry.py`
- `kfabric/web/router.py`
- `kfabric/web/templates/dashboard.html`
- `kfabric/services/discovery_engine.py`
- `kfabric/services/document_collector.py`
- `kfabric/services/document_parser.py`
- `kfabric/services/document_scoring.py`

## 8. Signaux importants à ne pas oublier

- Le repo est actuellement en worktree sale avec beaucoup de changements non
  commités.
- Le warning pytest sur `.pytest_cache` est connu et non bloquant.
- Le worker démarre correctement seulement si les URLs broker/backend dans
  Compose restent internes au réseau Docker.
- L'UI dépend de HTMX, mais Alpine a été retiré.
- La CSP HTML reste stricte et n'autorise pas `unsafe-eval`.

## 9. Prochaines pistes naturelles

- Étendre la couverture de tests sur les flux async web complets.
- Réduire le coût des rebuilds Docker si besoin.
- Revoir si `htmx.org` depuis `unpkg` doit être remplacé par un asset local pour
  durcir davantage la CSP et réduire la dépendance externe.
- Continuer l'industrialisation des connecteurs et du vrai pipeline d'indexation.
