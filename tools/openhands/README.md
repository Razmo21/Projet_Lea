# OpenHands SDK / Agent Server du profil Programmation

L’intégration de développement utilise le Software Agent SDK OpenHands sous
Windows et un Agent Server officiel dans Docker. Agent Canvas peut rester
installé à des fins administratives, mais il n'est ni démarré ni requis par ce
chemin. Le dépôt `L:\Projet_Lea` n'est jamais monté dans Docker.

## État opérationnel

L’étape 10 utilise désormais l’intégration Léa / SDK / Agent Server, et non un
bootstrap séparé. Le chemin normal est : Léa → Agent Server OpenHands minimal
dans Docker → llama.cpp local. Agent Canvas n’est jamais une précondition de ce
chemin.

## Architecture et composants épinglés

```text
Léa -> Agent Server OpenHands 1.43.1 dans Docker isolé -> llama.cpp local -> Qwen2.5-Coder-7B-Instruct Q6_K
```

- modèle unique : `models\development\qwen2.5-coder-7b-instruct-q6_k.gguf`, SHA-256 `46291ddea1bfb608fe63d9a1907eea6918bda87a7626593edc4bf97c5fd73f9d`, à 22 000 tokens avec un seul slot ;
- image Agent Server : `ghcr.io/openhands/agent-server@sha256:8ec6bd808b35cf50b7e5032f618ccbb33dd8e2bd80f8d130f12dafee24bab66a` (1.43.1) ;
- llama.cpp b10516 : `runtime\llama.cpp\llama-server.exe`, exposé uniquement sur `127.0.0.1:8081` sous l'alias `lea-development-openhands` ;
- Agent Server exposé uniquement sur `127.0.0.1:18010` ;
- template outillé épinglé : `tools\openhands\templates\qwen2.5-coder-function-call.jinja`, contrôlé par le registre avant le démarrage.

Le SDK utilise exclusivement `openai/lea-development-openhands` et la clé locale factice `local-llm`. Aucun LLM cloud, autre modèle, Canvas, MCP externe, recherche Web ou téléchargement n'est configuré. Docker Desktop doit être démarré manuellement : Léa vérifie sa disponibilité, mais ne le démarre jamais.

## Registre d'outils et historique

Le registre réel de l'Agent Server expose notamment les outils officiels `terminal`, `file_editor` et `task_tracker`. Ils sont importés explicitement dans l'Agent Server ; aucune simulation ni faux outil n'est utilisé.

Le client SDK 1.43.1 ne désérialise pas toujours sur l'hôte les définitions serveur `TerminalTool`, `FileEditorTool` et `TaskTrackerTool`. Le runner lit donc l'historique JSON paginé et authentique de l'Agent Server via :

```text
GET /api/conversations/{conversation_id}/events/search?limit=100
```

Il vérifie les `ActionEvent` et `ObservationEvent` réels et retire récursivement les champs de raisonnement des journaux. Cette récupération est une compatibilité d'historique, non un contournement du tool calling natif.

## Validation et persistance

Le run réel à 22K a validé la lecture des fichiers, les appels outillés natifs,
la correction, le retest vert et la réponse finale. Les événements détaillés
d’une session restent dans le volume d’état de l’Agent Server. SQLite ne garde
que le registre compact des runs, leurs résultats, leurs identifiants de session
et les métadonnées/hashs nécessaires aux checkpoints ; les snapshots de fichiers
restent dans le stockage local de checkpoints.

## Commandes de diagnostic SDK

Les scripts ci-dessous servent au diagnostic isolé du SDK. Ils lisent le
registre courant et appliquent leurs propres contrôles avant d’allouer un
runtime ; ils ne remplacent pas l’intégration et les validations de Léa.

```powershell
# Rend le fixture volontairement rouge, sans lancer Docker ni Qwen.
.\tools\openhands\run-openhands-sdk-smoke.ps1 -ResetSmokeFixture

# Smoke complet, qui démarre puis arrête ses propres services.
.\tools\openhands\run-openhands-sdk-smoke.ps1 -ContextSize 22000

# Cycle de vie SDK/Agent Server minimal, sans Canvas.
.\tools\openhands\start-openhands-sdk.ps1 -ContextSize 22000
.\tools\openhands\status-openhands-sdk.ps1
.\tools\openhands\stop-openhands-sdk.ps1
```

Le double démarrage est volontairement refusé. Ces scripts SDK sont des outils
de diagnostic ; le chemin normal passe par Léa. Les scripts sans suffixe `-sdk`
ne démarrent pas Agent Canvas.

## Isolement du smoke SDK historique

Cette section décrit uniquement le smoke SDK conservé pour le diagnostic ; le
run normal de Léa monte le seul projet figé du run, comme indiqué plus haut.

Le conteneur v2 `lea-openhands-sdk-smoke-v2` est limité à 4 Gio, 4 CPU et 512 PID. Il utilise exactement deux mounts :

```text
L:\IA_WORKSPACE -> /projects
lea_openhands_sdk_smoke_v2 -> /home/openhands/.openhands
```

Il est non privilégié, n'a pas de socket Docker, applique `no-new-privileges`, désactive VNC, VS Code, preload d'outils et webhooks. Il ne monte jamais `L:\Projet_Lea`. Docker conserve une connectivité potentielle vers `host.docker.internal` pour le LLM local, mais le smoke interdit réseau, téléchargements, Git et tout fichier hors du fixture. Ce smoke Linux ne valide ni PowerShell Windows, ni `lea.ps1`, ni Edge Stable, ni les validations Windows de l'étape 10.

## Étape 10

L’étape 10 est techniquement complète et attend la validation manuelle finale
de l’utilisateur. Aucun commit n’est créé par ces scripts.
