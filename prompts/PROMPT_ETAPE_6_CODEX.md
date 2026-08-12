# Prompt — Étape 6 du Projet Léa

Lis intégralement avant toute modification :

- `AGENTS.md`
- `README.md`
- `TODO.md`
- `docs/DECISIONS.md`
- `prompts/PROMPT_ETAPE_1_CODEX.md`
- `prompts/PROMPT_ETAPE_2_CODEX.md`
- `prompts/PROMPT_ETAPE_3_CODEX.md`
- `prompts/PROMPT_ETAPE_4_CODEX.md`
- `prompts/PROMPT_ETAPE_5_CODEX.md`

Nous commençons uniquement l’étape 6 du Projet Léa.

# Règle de suivi du projet

À chaque étape, mets à jour `TODO.md` afin qu’il reflète clairement :

- les étapes déjà terminées ;
- l’étape actuellement en cours ;
- la prochaine étape prévue, sans commencer son implémentation.

Pour cette étape :

- Étapes 1 à 5 : terminées.
- Étape 6 : simplifier et fiabiliser le démarrage, l’état et l’arrêt local de Léa.
- Étape 7 prévue : ajouter le contexte temporaire de conversation pendant une session, sans mémoire persistante.

Si l’étape 6 est validée par les tests, marque-la comme terminée dans `TODO.md`, mais n’entame pas l’étape 7.

---

# Objectif

Aujourd’hui, Léa nécessite trois lancements séparés :

1. `llama-server`
2. FastAPI
3. Vite

L’objectif de l’étape 6 est de pouvoir gérer tout Léa depuis UNE interface de commande simple sous Windows.

La forme préférée est un seul script PowerShell à la racine du projet :

```text
lea.ps1
```

avec trois actions :

```powershell
.\lea.ps1 start
.\lea.ps1 status
.\lea.ps1 stop
```

Le résultat attendu est :

```text
.\lea.ps1 start
        ↓
vérifications préalables
        ↓
llama-server
        ↓
FastAPI
        ↓
Vite
        ↓
Léa prête
```

et :

```text
.\lea.ps1 stop
        ↓
Vite arrêté
        ↓
FastAPI arrêté
        ↓
llama-server arrêté
        ↓
VRAM libérée
        ↓
aucun processus Léa restant
```

Cette étape ne doit ajouter aucune nouvelle fonctionnalité IA.

---

# Principe général

Le script doit rester :

- simple ;
- Windows natif ;
- lisible ;
- fiable ;
- limité au projet `Projet_Lea`.

N’ajoute pas de dépendance npm ou Python uniquement pour gérer les processus.

N’utilise pas Docker.

N’utilise pas un gestionnaire de processus externe.

Utilise PowerShell et les outils déjà présents sur Windows.

---

# Emplacement du script

Crée de préférence :

```text
lea.ps1
```

à la racine :

```text
L:\Projet_Lea\lea.ps1
```

Le script doit fonctionner même si l’utilisateur le lance depuis un autre dossier.

Il doit déterminer automatiquement la racine du projet à partir de l’emplacement du script, par exemple avec `$PSScriptRoot`.

Ne code pas en dur :

```text
L:\Projet_Lea
```

dans la logique interne si cela peut être évité.

Le projet doit rester facilement déplaçable vers un autre disque plus tard.

---

# Commandes supportées

Le script doit accepter exactement au minimum :

```powershell
.\lea.ps1 start
.\lea.ps1 status
.\lea.ps1 stop
```

Si aucune commande ou une commande invalide est fournie, affiche une aide courte et claire.

Exemple :

```text
Usage:
  .\lea.ps1 start
  .\lea.ps1 status
  .\lea.ps1 stop
```

Ne crée pas d’interface graphique.

---

# Composants existants à lancer

## 1. Modèle local

Exécutable :

```text
runtime/llama.cpp/llama-server.exe
```

Modèle :

```text
models/general/Qwen3-4B-Q4_K_M.gguf
```

Paramètres validés :

```text
-ngl 99
-c 4096
--host 127.0.0.1
--port 8080
--jinja
--alias lea-general
```

Le serveur modèle doit rester accessible uniquement sur :

```text
127.0.0.1:8080
```

Ne change pas les paramètres GPU validés.

---

## 2. Backend FastAPI

Python :

```text
backend/.venv/Scripts/python.exe
```

Commande logique :

```text
-m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Le répertoire de travail doit être :

```text
backend/
```

FastAPI doit rester accessible uniquement sur :

```text
127.0.0.1:8000
```

---

## 3. Frontend Vite

Commande logique :

```text
npm run dev -- --host 127.0.0.1 --port 5173
```

Répertoire de travail :

```text
racine du projet
```

Frontend :

```text
http://127.0.0.1:5173
```

N’utilise pas `0.0.0.0`.

---

# Ordre de démarrage

Le démarrage doit respecter cet ordre :

1. `llama-server`
2. FastAPI
3. Vite

Ne lance pas les trois aveuglément en parallèle.

Après chaque lancement, vérifie que le composant est réellement prêt avant de continuer.

---

# Vérifications de disponibilité

Utilise des vérifications simples avec un délai maximal raisonnable.

## llama-server

Après lancement, attends que le serveur soit réellement prêt.

Vérifie par exemple :

```text
http://127.0.0.1:8080/v1/models
```

ou un endpoint local équivalent déjà validé dans l’étape 5.

Le chargement du modèle peut prendre plusieurs secondes.

Ne considère pas Léa prête tant que le modèle n’est pas chargé.

## FastAPI

Vérifie :

```text
http://127.0.0.1:8000/health
```

La réponse attendue reste :

```json
{
  "status": "ok"
}
```

## Vite

Vérifie qu’une requête HTTP vers :

```text
http://127.0.0.1:5173
```

répond correctement.

---

# Message final de démarrage

Quand les trois composants sont prêts, affiche quelque chose de simple comme :

```text
Léa est prête.
Interface : http://127.0.0.1:5173
Modèle   : actif
Backend  : actif
Frontend : actif
```

N’ouvre pas automatiquement le navigateur sauf si cela est absolument nécessaire.

Pour cette étape, préfère simplement afficher l’URL.

---

# Gestion de l’état des processus

Le script doit pouvoir savoir quels processus IL a lancés afin de pouvoir les arrêter proprement plus tard.

Utilise une petite donnée d’état locale et temporaire, par exemple :

```text
.lea/
```

avec un fichier contenant les PID nécessaires.

Exemple conceptuel :

```text
.lea/processes.json
```

La structure exacte peut être adaptée.

Ce dossier doit être ignoré par Git.

Il ne doit contenir aucune donnée utilisateur importante.

Il doit pouvoir être supprimé sans endommager le projet.

---

# Règle de sécurité importante sur les processus

Ne tue JAMAIS un processus uniquement parce qu’il utilise le port 5173, 8000 ou 8080.

Un autre programme pourrait utiliser ce port.

Le script doit arrêter uniquement les processus qu’il peut raisonnablement identifier comme ayant été lancés par Léa.

Les PID sauvegardés servent à cela.

Avant d’arrêter un PID sauvegardé :

- vérifie si le processus existe encore ;
- vérifie autant que raisonnablement possible qu’il correspond au composant attendu.

Si l’état est ambigu, affiche une erreur claire au lieu de tuer un processus inconnu.

---

# Cas où Léa est déjà démarrée

Si l’utilisateur exécute :

```powershell
.\lea.ps1 start
```

alors que les trois composants gérés par Léa sont déjà actifs :

- ne lance pas une seconde copie ;
- affiche simplement que Léa est déjà démarrée ;
- affiche son état.

Si seulement une partie des composants est active, ne crée pas silencieusement un état incohérent.

Choisis une stratégie simple et sûre :

- soit refuser le démarrage et demander `.\lea.ps1 stop` puis `start`;
- soit nettoyer uniquement les processus clairement identifiés comme appartenant à Léa, puis redémarrer proprement.

Privilégie la solution la plus simple et la plus sûre.

---

# Ports déjà occupés

Avant de lancer chaque composant, vérifie si son port est déjà occupé.

Ports :

```text
8080 → llama-server
8000 → FastAPI
5173 → Vite
```

Si un port est occupé par un processus qui n’est pas clairement une instance déjà gérée de Léa :

ARRÊTE le démarrage.

Affiche un message clair, par exemple :

```text
Impossible de démarrer Léa : le port 8000 est déjà utilisé par un autre processus.
```

Ne change pas automatiquement de port.

Ne tue pas automatiquement le processus inconnu.

---

# Échec pendant le démarrage

Cas important :

- `llama-server` démarre ;
- FastAPI échoue ;
- ou Vite échoue.

Dans ce cas, le script ne doit pas laisser les composants précédents tourner inutilement.

Si une étape de démarrage échoue :

1. affiche clairement quel composant a échoué ;
2. arrête les processus Léa déjà démarrés pendant cette tentative ;
3. nettoie l’état temporaire ;
4. retourne une erreur.

Le PC doit revenir autant que possible à l’état précédent.

---

# Arrêt de Léa

Commande :

```powershell
.\lea.ps1 stop
```

Ordre préféré :

1. Vite
2. FastAPI
3. llama-server

L’objectif est de libérer complètement les ressources.

Pour chaque composant :

- essaie de l’arrêter proprement ;
- attends brièvement ;
- si le processus ne se termine pas, utilise une méthode Windows appropriée pour terminer uniquement son arbre de processus.

Pour Vite/npm, fais attention aux éventuels processus enfants Node.

Ne laisse pas `node.exe`, `python.exe` ou `llama-server.exe` liés à Léa tourner après un arrêt réussi.

Ne tue évidemment pas d’autres instances Node/Python étrangères au projet.

Après arrêt :

- supprime ou réinitialise l’état `.lea/`;
- vérifie que les ports 5173, 8000 et 8080 ne sont plus utilisés par les processus Léa ;
- vérifie que `llama-server` n’utilise plus la VRAM.

Ne modifie aucun réglage GPU.

---

# Commande status

Commande :

```powershell
.\lea.ps1 status
```

Elle doit afficher quelque chose de lisible.

Exemple :

```text
Léa
Modèle   : actif
Backend  : actif
Frontend : actif
Interface: http://127.0.0.1:5173
```

ou :

```text
Léa
Modèle   : arrêté
Backend  : arrêté
Frontend : arrêté
```

Si l’état sauvegardé indique un PID qui n’existe plus, considère le composant comme arrêté et nettoie l’état obsolète si cela peut être fait sans ambiguïté.

Ne démarre ni n’arrête rien avec `status`.

---

# Sorties console

Les messages doivent être courts et compréhensibles.

Évite d’afficher une énorme quantité de logs dans le terminal principal.

Cependant, les erreurs de démarrage doivent rester diagnosticables.

Si tu rediriges les sorties des composants vers des fichiers temporaires, place-les dans le dossier local d’état `.lea/` et ne les versionne pas.

N’ajoute pas un système complexe de logging.

---

# Fermeture manuelle / Ctrl+C

Le script doit être robuste dans la mesure raisonnable.

Si la solution choisie conserve un processus superviseur actif pendant que Léa tourne, `Ctrl+C` doit déclencher un nettoyage propre.

Si la solution choisie lance Léa en arrière-plan et rend immédiatement le terminal, documente clairement que :

```powershell
.\lea.ps1 stop
```

est la commande normale pour tout arrêter.

Choisis une seule approche simple.

Ne développe pas deux systèmes concurrents.

---

# Environnement virtuel Python

Ne recrée pas l’environnement virtuel.

Utilise celui déjà présent :

```text
backend/.venv
```

Si le Python de cet environnement n’existe pas, arrête le démarrage avec une erreur claire.

Ne lance pas automatiquement `pip install`.

L’installation des dépendances n’appartient pas à cette étape.

---

# Vérifications des fichiers nécessaires

Avant le démarrage, vérifie au minimum l’existence de :

```text
runtime/llama.cpp/llama-server.exe
models/general/Qwen3-4B-Q4_K_M.gguf
backend/.venv/Scripts/python.exe
package.json
```

Si un fichier essentiel manque :

- ne tente pas un démarrage partiel ;
- indique clairement ce qui manque.

---

# Ne pas exposer de service réseau

Tous les composants restent limités à la machine locale :

```text
Frontend : 127.0.0.1:5173
FastAPI  : 127.0.0.1:8000
Qwen     : 127.0.0.1:8080
```

Aucun composant ne doit écouter volontairement sur :

```text
0.0.0.0
```

Ne modifie pas le pare-feu Windows.

---

# Frontend / Backend / IA

Ne modifie pas leur comportement fonctionnel si ce n’est pas nécessaire.

Cette étape concerne uniquement :

- démarrage ;
- détection de disponibilité ;
- état ;
- arrêt ;
- nettoyage des processus.

Ne change pas :

- le prompt système de Léa ;
- `/no_think`;
- la route `/chat`;
- le format des réponses ;
- le design React ;
- le CSS ;
- les paramètres de génération ;
- la logique métier existante.

---

# Documentation

Mets à jour les documents strictement nécessaires afin d’expliquer l’utilisation.

Ajoute dans le README approprié une section courte avec :

```powershell
.\lea.ps1 start
.\lea.ps1 status
.\lea.ps1 stop
```

et l’URL :

```text
http://127.0.0.1:5173
```

Ne transforme pas la documentation en manuel énorme.

---

# AGENTS.md

Si `AGENTS.md` mentionne encore une ancienne étape comme étape actuelle :

- mets cette information à jour pour indiquer l’étape 6 ;
- préserve toutes les règles générales ;
- conserve explicitement le principe « une seule brique à la fois ».

Les interdictions propres aux anciennes étapes ne doivent pas empêcher l’étape 6 explicitement demandée.

---

# Avant de coder

Explique brièvement :

1. la stratégie choisie pour lancer les trois composants ;
2. comment les PID seront suivis ;
3. comment tu éviteras de tuer des processus étrangers ;
4. comment les ports seront vérifiés ;
5. comment tu détecteras que chaque service est prêt ;
6. comment tu nettoieras un démarrage partiellement échoué ;
7. quels fichiers seront créés ou modifiés.

Puis réalise uniquement l’étape 6.

---

# Tests obligatoires

Effectue réellement les tests suivants.

## Test 1 — état initial

Avec Léa complètement arrêtée :

```powershell
.\lea.ps1 status
```

Résultat attendu :

- modèle arrêté ;
- backend arrêté ;
- frontend arrêté.

## Test 2 — démarrage complet

Exécute :

```powershell
.\lea.ps1 start
```

Vérifie :

- `llama-server` démarre ;
- le modèle Qwen se charge sur CUDA ;
- FastAPI démarre ;
- Vite démarre ;
- les trois services sont prêts ;
- l’URL frontend répond ;
- le script indique clairement que Léa est prête.

## Test 3 — status actif

Exécute :

```powershell
.\lea.ps1 status
```

Vérifie que les trois composants sont annoncés actifs.

## Test 4 — vraie question

Sans lancer manuellement d’autre composant :

1. ouvre `http://127.0.0.1:5173`;
2. envoie une question simple ;
3. vérifie que la vraie réponse Qwen apparaît.

Cela confirme que `start` suffit réellement pour utiliser Léa.

## Test 5 — double démarrage

Avec Léa déjà active :

```powershell
.\lea.ps1 start
```

Vérifie qu’aucune seconde instance de :

- llama-server ;
- FastAPI ;
- Vite

n’est créée.

## Test 6 — arrêt complet

Exécute :

```powershell
.\lea.ps1 stop
```

Vérifie :

- frontend arrêté ;
- FastAPI arrêté ;
- llama-server arrêté ;
- ports Léa libérés ;
- processus enfants liés à Léa arrêtés ;
- VRAM du modèle libérée ;
- état temporaire nettoyé.

## Test 7 — arrêt déjà effectué

Exécute une seconde fois :

```powershell
.\lea.ps1 stop
```

Le script doit gérer proprement le fait que Léa soit déjà arrêtée.

Pas de stack trace ni d’erreur confuse.

## Test 8 — second cycle complet

Exécute :

```powershell
.\lea.ps1 start
```

puis :

```powershell
.\lea.ps1 stop
```

une seconde fois.

Le deuxième cycle doit fonctionner sans intervention manuelle.

## Test 9 — port occupé

Si possible sans perturber le poste :

1. occupe temporairement l’un des ports Léa avec un processus de test ;
2. lance `.\lea.ps1 start`;
3. vérifie que le script refuse proprement de démarrer ;
4. vérifie qu’il ne tue pas le processus étranger ;
5. nettoie ensuite le processus de test.

Ne laisse rien tourner après le test.

## Test 10 — fichier essentiel manquant simulé

Sans supprimer définitivement de fichier :

- simule temporairement l’absence d’un élément essentiel de manière sûre, par exemple en renommant brièvement un fichier puis en le restaurant ;
- vérifie que `start` échoue avant de lancer des services ;
- vérifie que le message indique clairement le fichier manquant ;
- restaure immédiatement le fichier.

Ne télécharge rien à nouveau.

---

# Vérification finale des processus

À la fin des tests, Léa doit être ARRÊTÉE.

Vérifie qu’il ne reste aucun processus du test correspondant à :

- `llama-server.exe` lancé depuis ce projet ;
- Python/Uvicorn lancé depuis `backend/.venv`;
- Vite/Node lancé pour ce projet.

Ne tue pas les processus Node ou Python étrangers.

---

# Vérification Git

Exécute :

```text
git status
```

et :

```text
git diff --check
```

Vérifie que :

- `.lea/` est ignoré ;
- aucun log temporaire n’est prêt à être commité ;
- aucun `.gguf` n’est prêt à être commité ;
- aucun binaire `llama.cpp` n’est prêt à être commité ;
- seuls les fichiers source/documentation prévus apparaissent.

Ne fais pas le commit à la place de l’utilisateur sauf demande explicite.

---

# Interdictions absolues

Ne fais PAS :

- de contexte conversationnel ;
- d’historique de conversation ;
- de mémoire persistante ;
- de SQLite ;
- de base de données ;
- de RAG ;
- d’accès à `IA_WORKSPACE` ;
- de recherche Web ;
- de système de profils ;
- de modèle supplémentaire ;
- de sélection dynamique de modèle ;
- de modification visuelle importante ;
- de refonte CSS ;
- de Markdown renderer ;
- de Tauri ;
- de Docker ;
- d’Ollama ;
- d’authentification ;
- de télémétrie ;
- de fine-tuning ;
- de LoRA ;
- de streaming de tokens ;
- de service Windows ;
- de démarrage automatique avec Windows ;
- d’icône dans la zone de notification ;
- de fonctionnalité de l’étape 7 ou ultérieure.

---

# Critères de validation

L’étape 6 est terminée uniquement si :

- `.\lea.ps1 start` suffit à démarrer tous les composants nécessaires ;
- le modèle est réellement prêt avant que Léa soit annoncée prête ;
- FastAPI et Vite sont réellement prêts ;
- `.\lea.ps1 status` reflète correctement l’état ;
- un double `start` ne crée pas de doublons ;
- un port étranger occupé n’est jamais tué automatiquement ;
- un échec partiel entraîne le nettoyage des composants déjà lancés ;
- `.\lea.ps1 stop` arrête uniquement les processus Léa ;
- les processus enfants sont eux aussi correctement arrêtés ;
- la VRAM du modèle est libérée après l’arrêt ;
- deux cycles `start → stop` successifs fonctionnent ;
- aucune nouvelle fonctionnalité IA n’a été ajoutée ;
- `TODO.md` reflète les étapes terminées, l’étape 6 et l’étape 7 prévue ;
- aucune fonctionnalité de l’étape 7 n’a été commencée.

À la fin, fournis un compte rendu concis avec :

- fichiers créés/modifiés ;
- commandes utilisateur finales ;
- méthode de suivi des processus ;
- résultat de chaque test obligatoire ;
- confirmation de la libération de la VRAM ;
- état final de `TODO.md` ;
- résultat de `git status`;
- éventuels avertissements ou erreurs restantes.

Puis ARRÊTE-TOI et attends la validation de l’utilisateur.
