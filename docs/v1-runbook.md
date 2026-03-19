# Runbook V1 KFabric

Ce runbook couvre le mode d'exploitation local le plus simple pour une V1
mono-noeud avec Docker Compose.

## Préparer l'environnement

1. Copier [`../.env.example`](../.env.example) vers `.env` si tu veux surcharger
   certains paramètres.
2. Définir au minimum une clé API si l'instance ne doit pas rester ouverte :

```bash
export KFABRIC_API_KEY="change-me"
```

## Démarrer la stack

```bash
make stack-up
```

Services principaux :

- API KFabric : `http://127.0.0.1:8001`
- Swagger : `http://127.0.0.1:8001/docs`
- RabbitMQ management : `http://127.0.0.1:15672`
- Qdrant : `http://127.0.0.1:6333`

## Vérifier la disponibilité

Liveness :

```bash
curl http://127.0.0.1:8001/api/v1/health
```

Readiness :

```bash
curl http://127.0.0.1:8001/api/v1/readiness
```

La readiness renvoie :

- `ready` si la base et le stockage sont disponibles et que les dépendances
  principales répondent
- `degraded` si le coeur est opérationnel mais qu'un service secondaire manque
- `not_ready` si la base ou le stockage ne sont pas exploitables

## Commandes utiles

Installation locale :

```bash
make install-extended
```

Tests :

```bash
make test
```

Logs applicatifs :

```bash
make stack-logs
```

Arrêt :

```bash
make stack-down
```

## Notes d'exploitation

- le service `migrate` applique Alembic avant que l'API ne soit considérée comme
  prête
- le volume `kfabric_storage` conserve les artefacts du corpus
- les identifiants par défaut de `docker-compose.yml` sont acceptables pour une
  V1 locale, mais doivent être remplacés hors environnement de démonstration
