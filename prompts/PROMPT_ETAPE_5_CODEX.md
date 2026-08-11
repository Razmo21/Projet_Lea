# Prompt — Étape 5 du Projet Léa

Lis intégralement avant toute modification :

- `AGENTS.md`
- `README.md`
- `TODO.md`
- `docs/DECISIONS.md`
- `prompts/PROMPT_ETAPE_1_CODEX.md`
- `prompts/PROMPT_ETAPE_2_CODEX.md`
- `prompts/PROMPT_ETAPE_3_CODEX.md`
- `prompts/PROMPT_ETAPE_4_CODEX.md`

Nous commençons uniquement l’étape 5 du Projet Léa.

# Règle de suivi du projet

À chaque étape, mets à jour `TODO.md` afin qu’il reflète clairement :

- les étapes déjà terminées ;
- l’étape actuellement en cours ;
- la prochaine étape prévue, sans commencer son implémentation.

Pour cette étape :

- Étapes 1 à 4 : terminées.
- Étape 5 : connexion complète Frontend → FastAPI → modèle local.
- Étape 6 prévue : simplifier et fiabiliser le démarrage/arrêt local de Léa (frontend + backend + moteur IA), sans ajouter de mémoire ni de nouvelle fonctionnalité.

Si l’étape 5 est validée par les tests, marque-la comme terminée dans `TODO.md`, mais n’entame pas l’étape 6.

---

# Objectif

Connecter pour la première fois l’interface actuelle de Léa au vrai modèle local :

`Qwen3-4B-Q4_K_M.gguf`

Le flux final doit être :

```text
Utilisateur
    ↓
Frontend React
    ↓
FastAPI
    ↓
llama-server local
    ↓
Qwen3-4B
    ↓
FastAPI
    ↓
Frontend
    ↓
Réponse réelle affichée
```

À la fin de cette étape, l’utilisateur doit pouvoir écrire une question dans la page de Léa et recevoir une vraie réponse générée localement par Qwen.

---

# Principe important

NE PAS lancer `llama-cli.exe` à chaque question.

Le modèle doit rester chargé pendant l’utilisation grâce à :

`llama-server.exe`

FastAPI communiquera avec ce serveur uniquement en local.

Cela évite de recharger les ~2,5 Go du modèle à chaque message et permet plusieurs questions successives avec de bonnes performances.

Pour cette étape, le serveur du modèle peut être lancé manuellement dans un terminal séparé.

Ne crée pas encore de système automatique de démarrage/arrêt : ce sera l’étape suivante.

---

# Éléments existants à réutiliser

Modèle :

```text
models/general/Qwen3-4B-Q4_K_M.gguf
```

Runtime llama.cpp :

```text
runtime/llama.cpp/
```

Vérifie que le runtime contient :

```text
llama-server.exe
```

Si `llama-server.exe` n’est pas présent, ARRÊTE-TOI et explique le problème.

Ne télécharge pas une nouvelle version de llama.cpp si ce n’est pas nécessaire.

Backend existant :

```text
backend/
```

Frontend React existant à la racine du projet.

---

# Serveur local du modèle

Utilise `llama-server.exe`.

Il doit écouter uniquement sur :

```text
127.0.0.1:8080
```

Il ne doit PAS écouter sur `0.0.0.0`.

Commande de base attendue, à adapter uniquement si le build installé exige une petite variation :

```powershell
.\runtime\llama.cpp\llama-server.exe `
  -m .\models\general\Qwen3-4B-Q4_K_M.gguf `
  -ngl 99 `
  -c 4096 `
  --host 127.0.0.1 `
  --port 8080 `
  --jinja `
  --alias lea-general
```

Conserve l’utilisation GPU actuelle.

Ne réduis pas `-ngl` : les tests de l’étape 4 ont validé le fonctionnement avec toutes les couches sur la RTX A1000.

Ne modifie pas les limites de puissance NVIDIA.

---

# Vérification du serveur modèle

Avant de modifier FastAPI :

1. lance `llama-server.exe`;
2. attends que le modèle soit complètement chargé;
3. vérifie que son API locale répond;
4. utilise de préférence un endpoint documenté tel que :

```text
GET http://127.0.0.1:8080/v1/models
```

5. effectue un petit appel direct à l’API de chat afin de confirmer qu’une vraie réponse est générée.

Si le serveur modèle ne fonctionne pas correctement, corrige uniquement ce problème avant de poursuivre.

---

# Backend FastAPI

Modifie le backend minimal existant afin qu’il transmette les questions au serveur local du modèle.

Utilise l’API compatible OpenAI de `llama-server` :

```text
POST http://127.0.0.1:8080/v1/chat/completions
```

FastAPI ne doit communiquer qu’avec `127.0.0.1`.

Aucun appel Internet.

---

# Dépendance HTTP

Tu peux ajouter :

```text
httpx
```

dans `backend/requirements.txt` si nécessaire.

N’ajoute aucune autre dépendance non nécessaire.

Utilise de préférence un client HTTP asynchrone adapté à FastAPI.

---

# Route de chat

Remplace la logique fictive de l’étape précédente par une vraie route :

```text
POST /chat
```

Entrée :

```json
{
  "question": "Bonjour Léa"
}
```

Sortie :

```json
{
  "answer": "..."
}
```

où `answer` contient uniquement la réponse finale produite par Qwen.

La route `/health` existante doit continuer à fonctionner.

L’ancienne route `/test-response` peut être supprimée si elle n’est plus utilisée.

Ne conserve pas inutilement deux routes faisant la même chose.

---

# Requête envoyée à Qwen

Envoie au modèle un échange minimal de type chat.

Utilise un petit message système généraliste, par exemple :

```text
Tu es Léa, un assistant généraliste local. Réponds dans la langue de l’utilisateur, de façon claire, utile et directe.
```

N’ajoute pas encore :

- de personnalité complexe ;
- de règles spécialisées ;
- de mémoire ;
- de profil métier ;
- de connaissances injectées ;
- de RAG.

Pour cette étape, désactive le raisonnement visible de Qwen.

La méthode la plus simple déjà validée avec ce modèle est d’ajouter discrètement :

```text
/no_think
```

à la question transmise au modèle.

Le texte `/no_think` ne doit pas être ajouté visuellement dans le champ de l’utilisateur ni affiché dans la réponse.

Si le serveur supporte proprement une option de template permettant de désactiver le thinking avec ce modèle, tu peux l’utiliser à la place, mais reste simple et vérifie réellement le résultat.

La réponse retournée au frontend ne doit pas contenir :

```text
[Start thinking]
[End thinking]
<think>
</think>
```

ni le raisonnement interne du modèle.

---

# Paramètres de génération

Reste simple.

Pour cette étape :

- `stream`: false ;
- limite de génération raisonnable, par exemple autour de 512 tokens ;
- contexte serveur : 4096 ;
- ne lance aucun benchmark ;
- ne cherche pas à optimiser la température, top-p, top-k ou autres paramètres sauf nécessité réelle.

Utilise les valeurs par défaut raisonnables de Qwen/llama.cpp.

---

# Gestion des erreurs

La gestion doit rester minimale et claire.

Si `llama-server` n’est pas lancé ou ne répond pas :

FastAPI doit retourner une erreur appropriée, idéalement HTTP 503, avec un message clair.

Le frontend doit afficher un message compréhensible, par exemple :

```text
Le modèle local de Léa n’est pas disponible.
```

Ne crée pas de système complexe de retry, queue, watchdog ou redémarrage automatique.

Ce sera traité plus tard uniquement si nécessaire.

---

# Frontend

Modifie uniquement ce qui est nécessaire pour remplacer l’appel à :

```text
/test-response
```

par :

```text
/chat
```

Le frontend doit :

1. envoyer la question saisie ;
2. attendre la vraie réponse du modèle ;
3. afficher cette réponse ;
4. empêcher idéalement plusieurs envois simultanés pendant qu’une réponse est en cours ;
5. conserver une gestion d’erreur simple.

Tu peux afficher temporairement un texte simple comme :

```text
Léa réfléchit...
```

pendant l’attente.

Ne refais pas le design.

Ne crée pas encore de système de messages multiples ou d’historique de conversation.

Une question → une réponse affichée reste suffisante pour cette étape.

---

# Absence volontaire de mémoire

Chaque requête doit être indépendante.

Par exemple :

1. utilisateur : `Mon prénom est Stan.`
2. réponse du modèle.
3. nouvelle requête : `Quel est mon prénom ?`

Il n’est PAS nécessaire que Qwen s’en souvienne à cette étape.

Ne crée aucun historique côté backend ou frontend.

La mémoire viendra dans une étape future.

---

# Sécurité réseau minimale

Les trois composants doivent rester locaux :

```text
Frontend : localhost/127.0.0.1:5173
FastAPI  : 127.0.0.1:8000
Qwen     : 127.0.0.1:8080
```

Ne rends aucun service accessible publiquement sur le réseau.

Conserve le CORS local déjà configuré pour le frontend.

---

# AGENTS.md

Si `AGENTS.md` mentionne encore une ancienne étape comme étape actuelle :

- mets uniquement cette information à jour pour indiquer l’étape 5 ;
- préserve les règles générales du projet ;
- ne supprime pas le principe « une seule brique à la fois ».

Les interdictions propres aux anciennes étapes ne doivent pas bloquer cette étape explicitement demandée.

---

# Avant de coder

Explique brièvement :

1. quels fichiers tu vas modifier ;
2. comment `llama-server` sera lancé ;
3. comment FastAPI communiquera avec lui ;
4. pourquoi le modèle restera chargé entre les requêtes ;
5. quelle dépendance backend sera ajoutée ;
6. comment tu empêcheras l’affichage du thinking ;
7. comment tu testeras le flux complet.

Puis réalise uniquement l’étape 5.

---

# Tests obligatoires

## Test 1 — llama-server seul

Lance le serveur modèle et confirme :

- Qwen3-4B se charge ;
- CUDA est utilisé ;
- les couches sont offloadées sur le GPU ;
- l’API locale répond ;
- une question directe produit une vraie réponse.

## Test 2 — backend seul

Avec `llama-server` actif :

- démarre FastAPI ;
- appelle `POST /chat` directement ;
- vérifie HTTP 200 ;
- vérifie que la réponse provient réellement de Qwen ;
- vérifie qu’elle ne contient pas de thinking visible.

## Test 3 — flux complet

Lance :

1. `llama-server`;
2. FastAPI;
3. Vite.

Depuis la page de Léa, envoie par exemple :

```text
Réponds en une phrase : quelle est la capitale du Canada ?
```

La réponse doit être générée réellement par Qwen et mentionner Ottawa.

## Test 4 — seconde question

Pose une seconde question différente sans redémarrer `llama-server`.

Confirme que :

- le modèle n’est pas rechargé ;
- la réponse arrive correctement ;
- le serveur reste stable.

## Test 5 — modèle indisponible

Arrête uniquement `llama-server`.

Laisse FastAPI et le frontend actifs.

Envoie une question.

Vérifie que l’utilisateur reçoit un message clair indiquant que le modèle local n’est pas disponible.

Relance ensuite le serveur uniquement si nécessaire pour les derniers tests.

---

# Vérification Git

Avant de terminer :

```text
git status
```

Vérifie que :

- aucun `.gguf` n’est prêt à être commité ;
- aucun binaire lourd de `runtime/llama.cpp/` n’est prêt à être commité ;
- seuls les fichiers source et documentation prévus apparaissent.

Ne fais pas le commit à la place de l’utilisateur sauf demande explicite.

---

# Interdictions absolues

Ne fais PAS :

- de mémoire ;
- d’historique de conversation ;
- de SQLite ;
- de base de données ;
- de RAG ;
- d’accès à `IA_WORKSPACE` ;
- d’accès Internet depuis Léa ;
- de recherche Web ;
- de modèle de développement ;
- de modèle santé animale ;
- de modèle vision ;
- de système de profils ;
- de sélection dynamique de modèles ;
- de Tauri ;
- de Docker ;
- d’Ollama ;
- d’authentification ;
- de télémétrie ;
- de fine-tuning ;
- de LoRA ;
- de streaming de tokens ;
- de lancement automatique de `llama-server` ;
- de script lançant tous les composants ;
- de gestion avancée des processus ;
- de fonctionnalité de l’étape 6 ou ultérieure.

---

# Critères de validation

L’étape 5 est terminée uniquement si :

- `llama-server` charge correctement Qwen3-4B sur GPU ;
- le modèle reste chargé entre plusieurs questions ;
- FastAPI communique réellement avec `llama-server` via localhost ;
- `POST /chat` produit une vraie réponse du modèle ;
- le frontend appelle `POST /chat` ;
- une vraie réponse Qwen apparaît dans la page ;
- aucun thinking interne n’est affiché ;
- une panne du serveur modèle est gérée proprement ;
- aucun historique/mémoire n’a été ajouté ;
- aucun service n’est exposé sur le réseau ;
- `TODO.md` reflète correctement les étapes terminées, l’étape 5 et l’étape 6 prévue ;
- aucune fonctionnalité de l’étape suivante n’a été commencée.

À la fin, fournis un compte rendu concis avec :

- fichiers créés/modifiés ;
- dépendances ajoutées ;
- commande utilisée pour `llama-server` ;
- résultat du test direct du modèle ;
- résultat du test FastAPI ;
- résultat du test frontend complet ;
- confirmation que le modèle reste chargé entre deux requêtes ;
- résultat du test lorsque `llama-server` est arrêté ;
- état final de `TODO.md` ;
- éventuels avertissements ou erreurs.

Puis ARRÊTE-TOI et attends la validation de l’utilisateur.
