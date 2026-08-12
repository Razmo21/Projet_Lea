# Backend de Léa

Backend FastAPI local de Léa, relié au serveur de modèle local `llama-server`.

## Prérequis

- Python 3.12.2

## Installation

Depuis le dossier `backend` :

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Démarrage

Lance d’abord le serveur du modèle depuis la racine du projet :

```powershell
.\runtime\llama.cpp\llama-server.exe -m .\models\general\Huihui-Qwen3-4B-abliterated-v2-Q4_K_M.gguf -ngl 99 -c 4096 --host 127.0.0.1 --port 8080 --jinja --alias lea-general
```

Ensuite, depuis le dossier `backend` :

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Routes

- `GET /health` retourne `{ "status": "ok" }`.
- `POST /chat` reçoit `{ "question": "Bonjour Léa" }` et retourne la réponse du modèle local.
