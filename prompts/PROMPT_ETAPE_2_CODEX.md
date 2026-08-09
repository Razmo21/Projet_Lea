# Prompt — Étape 2 du Projet Léa

Lis intégralement les fichiers suivants avant toute modification :

- `AGENTS.md`
- `README.md`
- `TODO.md`
- `docs/DECISIONS.md`

Nous commençons uniquement l’étape 2 du Projet Léa.

## Objectif

Créer un backend Python minimal avec FastAPI.

Ce backend doit être complètement indépendant du frontend pour l’instant.

Ne modifie pas l’interface React actuelle.

## Structure attendue

Crée un dossier :

`backend/`

Avec une structure simple, par exemple :

```text
backend/
├── app/
│   ├── __init__.py
│   └── main.py
├── requirements.txt
└── README.md
```

Tu peux adapter légèrement cette structure si nécessaire, mais reste minimal.

## Environnement Python

Le projet utilise Python 3.12.2.

Crée si nécessaire un environnement virtuel local dans :

`backend/.venv`

Il doit rester ignoré par Git.

Installe uniquement les dépendances nécessaires à cette étape.

Utilise FastAPI et Uvicorn.

N’ajoute aucune autre bibliothèque inutile.

## Routes à créer

### 1. GET `/health`

Cette route doit répondre en JSON :

```json
{
  "status": "ok"
}
```

Elle sert uniquement à vérifier que le backend fonctionne.

### 2. POST `/test-response`

Cette route reçoit une question sous forme JSON :

```json
{
  "question": "Bonjour"
}
```

Elle doit retourner une réponse fictive :

```json
{
  "answer": "Léa n'est pas encore connectée à son modèle."
}
```

La question reçue peut être validée simplement avec Pydantic/FastAPI.

Aucun modèle d’IA ne doit être appelé.

## Avant de coder

Explique brièvement :

1. ce que tu vas créer ;
2. les fichiers concernés ;
3. les dépendances que tu vas installer ;
4. les commandes que tu comptes utiliser.

Puis réalise uniquement cette étape.

## Vérifications obligatoires

Après avoir terminé :

1. démarre le backend localement ;
2. vérifie que `GET /health` répond bien HTTP 200 avec `{"status":"ok"}` ;
3. vérifie que `POST /test-response` fonctionne avec une question de test ;
4. confirme qu’aucune modification n’a été faite au frontend ;
5. liste les fichiers créés ou modifiés ;
6. indique les commandes utilisées ;
7. signale toute erreur ou avertissement restant ;
8. arrête le serveur de test si tu l’as lancé ;
9. arrête-toi et attends la validation de l’utilisateur.

## Interdictions absolues pour cette étape

Ne fais PAS :

- de connexion entre React et FastAPI ;
- de modification du frontend ;
- de modèle d’IA ;
- de llama.cpp ;
- de téléchargement de modèle ;
- de mémoire ;
- de SQLite ;
- de base de données ;
- de RAG ;
- d’accès à `IA_WORKSPACE` ;
- d’accès Internet depuis Léa ;
- de système de profils ;
- de Tauri ;
- de Docker ;
- d’authentification ;
- de télémétrie ;
- de fonctionnalité future.

N’entame pas l’étape 3.

## Critères de validation

L’étape 2 est terminée uniquement si :

- le backend se trouve dans `backend/` ;
- l’environnement Python est fonctionnel ;
- FastAPI démarre sans erreur ;
- `/health` retourne HTTP 200 ;
- `/test-response` retourne la réponse fictive attendue ;
- le frontend n’a pas été modifié ;
- aucune fonctionnalité supplémentaire n’a été ajoutée.

Une fois ces critères atteints, arrête-toi.
