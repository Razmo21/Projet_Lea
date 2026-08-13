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
.\runtime\llama.cpp\llama-server.exe -m .\models\general\Huihui-Qwen3-4B-abliterated-v2-Q4_K_M.gguf -ngl 99 -c 4096 --host 127.0.0.1 --port 8080 --jinja --alias lea-general --reasoning on --reasoning-budget 512
```

Ensuite, depuis le dossier `backend` :

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Routes

- `GET /health` retourne `{ "status": "ok" }`.
- `POST /chat` accepte toujours la forme simple `{ "question": "Bonjour Léa" }`
  et retourne `{ "answer": "..." }`.
- Pour le contexte temporaire de la page en cours, la même route accepte aussi
  une propriété optionnelle `history` composée uniquement de paires complètes
  `user` / `assistant` :

  ```json
  {
    "question": "Comment s'appelle mon chien ?",
    "history": [
      { "role": "user", "content": "Mon chien s'appelle Rex." },
      { "role": "assistant", "content": "D'accord." }
    ]
  }
  ```

Le backend refuse les rôles autres que `user` et `assistant`, les paires
incomplètes ou mal ordonnées, les champs inconnus, les contenus vides ou NUL,
et les messages trop grands. Il ne conserve aucune conversation entre deux
requêtes.

Avec la fenêtre de contexte `-c 4096`, le backend réserve 1 024 tokens pour la
réponse finale, 512 pour le raisonnement et 512 pour les instructions et le
template. Faute de tokenizer llama.cpp directement exploitable ici, il utilise
une borne haute volontairement prudente d’un octet UTF-8 par token, plus un
coût fixe par message, pour les 2 048 tokens d’entrée restants. Il garde la
question actuelle et autant de paires récentes complètes que possible, puis
retire les paires les plus anciennes.

## Raisonnement équilibré

Le serveur du modèle utilise `--reasoning on --reasoning-budget 512`. Le
template local renvoie actuellement la pensée interne entre balises dans le
contenu technique du modèle ; le backend les retire de façon ciblée et ne
renvoie que la réponse finale. Aucune pensée interne ni balise de raisonnement
n’est exposée à l’interface.
