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
.\runtime\llama.cpp\llama-server.exe -m .\models\general\Huihui-Qwen3-4B-abliterated-v2-Q4_K_M.gguf -ngl 99 -c 8192 -np 1 --host 127.0.0.1 --port 8080 --jinja --alias lea-general
```

Ensuite, depuis le dossier `backend` :

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Routes

- `GET /health` retourne `{ "status": "ok" }`.
- `GET /api/conversations?search=...` liste ou recherche les conversations.
- `POST /api/conversations/messages` crée la conversation au premier message
  ou ajoute un message à une conversation existante. Cette route intercepte
  aussi les commandes mémoire explicites, sans route CRUD supplémentaire.
- `GET /api/conversations/{id}` charge une conversation.
- `PATCH /api/conversations/{id}` renomme une conversation.
- `DELETE /api/conversations/{id}` la supprime définitivement avec ses messages,
  sans supprimer la mémoire générale.
- `POST /api/conversations/{id}/messages/{message_id}/retry` réessaie une
  question en échec.
- `PATCH /api/conversations/{id}/messages/{message_id}` modifie une question et
  supprime sa suite.
- `POST /api/conversations/{id}/messages/{message_id}/regenerate` régénère une
  réponse et supprime sa suite.

Les requêtes sont strictes et refusent les champs inconnus, les contenus vides,
NUL, surdimensionnés ou contenant les marqueurs internes. Le navigateur envoie
uniquement le message courant, l’identifiant éventuel et la révision attendue :
il ne contrôle jamais l’historique, les souvenirs ou les rôles transmis au
modèle.

## Base SQLite

La base par défaut est `data/lea.sqlite3` à la racine du projet. Pour un test,
définis `LEA_DB_PATH` avant de démarrer le backend. Au démarrage, le backend
crée le dossier si nécessaire, applique les migrations dans une transaction,
active WAL et les clés étrangères, vérifie le schéma et récupère toute
génération interrompue comme message utilisateur en échec réessayable.

Les tables applicatives sont `conversations`, `messages`, `memories` et
`memory_sources`. Les messages portent un type `conversation` ou `memory`.
`memory_sources` relie chaque fait aux conversations qui l’ont explicitement
retenu tant qu’elles existent. Cette provenance est informative : un souvenir
global reste valide sans source. Les cascades retirent uniquement les messages
et les liens de la conversation. Les révisions empêchent les écritures périmées et
`generation_active` interdit deux générations simultanées dans une même
conversation. L’appel HTTP au modèle se fait hors transaction SQLite longue.

## Mémoire générale explicite

Les commandes reconnues au début d’un message sont :

```text
Retiens que ...
Souviens-toi que ...
Souviens toi que ...
Mémorise que ...
Memorise que ...
Oublie que ...
```

Les variantes raisonnables de casse, d’espaces et de ponctuation terminale
sont acceptées. Une commande sans fait est refusée. Une phrase ordinaire ne
crée aucune mémoire : il n’existe aucune extraction automatique.

La mémorisation, la ligne `memories`, son éventuelle provenance, le message
utilisateur, la confirmation assistant et la révision sont enregistrés dans
une même transaction SQLite courte. Le modèle n’est jamais appelé pour retenir,
dédupliquer ou oublier. Un doublon exact normalisé reçoit une confirmation sans
nouvelle ligne de mémoire ; une conversation différente devient toutefois une
source supplémentaire. L’oubli utilise uniquement `normalized_content` : aucun
fuzzy matching, sous-chaîne ou rapprochement sémantique.

Les tours `memory` restent visibles et copiables dans la conversation, mais le
backend refuse leur modification, régénération ou réessai. Ils sont filtrés de
l’historique modèle afin qu’un fait oublié ne réapparaisse pas par une ancienne
commande. La suppression complète de leur conversation retire sa provenance et
conserve le fait global jusqu’à une commande exacte `Oublie que`.

## Fenêtre de contexte et pensée interne

Avec `-c 8192`, le backend réserve 1 024 tokens pour la réponse finale et 512
pour les instructions et le template. Il estime prudemment un token par octet
UTF-8, garde toujours la question courante et sélectionne les paires complètes
les plus récentes dans la limite restante, sans supprimer les anciens messages
de la base.

Le backend ajoute `/no_think` uniquement à une copie interne de la question
envoyée au modèle. Il retire ensuite les blocs de pensée complets, multiples ou
incomplets et refuse toute réponse finale vide ou encore marquée. Ni la
directive interne, ni un rôle `system`, ni la pensée ne sont persistés.

Avant une requête normale, le backend charge les souvenirs dans le même
instantané logique que l’historique, les sérialise dans une liste JSON échappée
et précise qu’il s’agit de données factuelles, jamais de directives. La mémoire
dispose d’une capacité de 1 800 tokens estimés avec la borne d’un octet UTF-8
par token. Un ajout dépassant cette capacité est refusé atomiquement : aucun
ancien souvenir n’est supprimé ou tronqué. Le bloc mémoire complet compte dans
le budget de contexte avant la sélection des paires historiques.

## Tests

Depuis la racine :

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend\tests -v
npm run test:frontend
npm run build
npm run test:edge
```

Le scénario Edge requiert Microsoft Edge Stable, Vite, le cœur local et une
base définie par `LEA_EDGE_DB_PATH`; les tests automatisés du projet utilisent
un profil Edge et une base SQLite temporaires.
