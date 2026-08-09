# Backend de Léa

Backend FastAPI local minimal et indépendant du frontend.

## Prérequis

- Python 3.12.2

## Installation

Depuis le dossier `backend` :

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Démarrage

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Routes

- `GET /health` retourne `{ "status": "ok" }`.
- `POST /test-response` reçoit `{ "question": "Bonjour" }` et retourne une réponse fictive.
