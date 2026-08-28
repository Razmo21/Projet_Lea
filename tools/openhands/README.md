# OpenHands SDK minimal séparé de Léa

Le bootstrap de développement utilise le Software Agent SDK OpenHands sous Windows et un Agent Server officiel dans Docker. Agent Canvas peut rester installé à des fins administratives, mais il n'est ni démarré ni requis par ce chemin. Le dépôt `L:\Projet_Lea` n'est jamais monté dans Docker.

## État du bootstrap

`OPENHANDS_LOCAL_READY` — le 28 août 2026 à 12:56:45 UTC, le smoke réel SDK/Agent Server minimal a validé **22 000 tokens**, la plus grande fenêtre autorisée et testée. Aucun essai 20K, 18K ou 16K n'est requis tant que 22K reste viable.

Le run a utilisé une conversation et un volume `smoke-v2` séparés. Les anciennes conversations de smoke portant les définitions `TerminalTool`, `FileEditorTool` et `TaskTrackerTool` restent préservées dans l'état legacy et ne sont ni lues ni adoptées. Agent Canvas n'est pas une précondition du bootstrap.

## Architecture et composants épinglés

```text
Client SDK Windows -> Agent Server OpenHands 1.43.1 dans Docker isolé -> llama.cpp local -> Qwen2.5-Coder-14B-Instruct Q5_K_M
```

- modèle unique : `models\development\qwen2.5-coder-14b-instruct-q5_k_m.gguf` (10 508 873 152 octets), SHA-256 `98ab25e0132e3f1e6d3554e1b64de2b5021908819b740d9c208430117e49a775` ;
- image Agent Server : `ghcr.io/openhands/agent-server@sha256:8ec6bd808b35cf50b7e5032f618ccbb33dd8e2bd80f8d130f12dafee24bab66a` (1.43.1) ;
- llama.cpp existant : `runtime\llama.cpp\llama-server.exe`, exposé uniquement sur `127.0.0.1:8081` sous l'alias `lea-development-openhands` ;
- Agent Server exposé uniquement sur `127.0.0.1:18010` ;
- template outillé épinglé : `tools\openhands\templates\qwen2.5-coder-openai-tools.jinja`, SHA-256 `a24779148fa43c5dfeec5a6a40adb2f5bbead90b01cb70a338175070144c69c6`, lancé avec `--jinja --no-skip-chat-parsing --chat-template-file`.

Le SDK utilise exclusivement `openai/lea-development-openhands` et la clé locale factice `local-llm`. Aucun LLM cloud, autre modèle, Canvas, MCP externe, recherche Web ou téléchargement n'est configuré. Le probe OpenAI-compatible a réellement renvoyé `finish_reason=tool_calls` pour `record_smoke_probe`.

## Registre d'outils et historique

Le registre réel de l'Agent Server expose notamment les outils officiels `terminal`, `file_editor` et `task_tracker`. Ils sont importés explicitement dans l'Agent Server ; aucune simulation ni faux outil n'est utilisé.

Le client SDK 1.43.1 ne désérialise pas toujours sur l'hôte les définitions serveur `TerminalTool`, `FileEditorTool` et `TaskTrackerTool`. Le runner lit donc l'historique JSON paginé et authentique de l'Agent Server via :

```text
GET /api/conversations/{conversation_id}/events/search?limit=100
```

Il vérifie les `ActionEvent` et `ObservationEvent` réels et retire récursivement les champs de raisonnement des journaux. Cette récupération est une compatibilité d'historique, non un contournement du tool calling natif.

## Validation réelle à 22K

| Point | RAM physique libre minimale |
| --- | ---: |
| avant Qwen | 17,351 Gio |
| après chargement | 6,854 Gio |
| après premier prompt | 6,831 Gio |
| après démarrage Agent Server | 6,284 Gio |
| pendant le run réel | 6,047 Gio |
| après le run | 6,781 Gio |

Les 141 échantillons du run ne contiennent aucune mesure critique. Docker a utilisé 338,4 à 375,3 Mio sur 4 Gio ; WSL/Docker a conservé au minimum 14,18 Gio disponibles sur environ 15,45 Gio ; la VRAM Qwen était de 4 550 à 4 594 Mio sur 6 144 Mio ; le pagefile était de 2 786 à 2 832 Mio sur 7 984 Mio, avec un pic inchangé à 8 012 Mio. La hausse courante est de 44 Mio, `pagefile_severe=false`, et le maximum de mémoire engagée Windows est 25,178 Gio. Aucun OOM, pagination sévère ni instabilité n'a été observé.

Le fixture était d'abord rouge avec deux échecs. L'agent a lu `README.md`, `pricing.py` puis `test_pricing.py`, a exécuté les tests rouges, a appelé réellement `terminal` et `file_editor`, a modifié uniquement `pricing.py`, a retesté vert, puis a fourni un résumé cohérent. Le run a produit 9 actions (3 `terminal`, 6 `file_editor`), 35 événements d'historique Agent Server autoritatifs sur 37, et aucune erreur majeure. Les artefacts reproductibles sont sous `.lea\openhands-sdk\smoke-v2\logs\`.

## Politique et commandes

La politique active est : `>= 6 Gio` normale ; `>= 4 Gio et < 6 Gio` acceptable pour le profil nocturne ; `< 4 Gio` de façon durable critique avec arrêt propre. Un OOM Agent Server ou une pagination sévère rend également le contexte non viable. Les contextes autorisés sont 22K, 20K, 18K et 16K, dans cet ordre seulement lorsqu'un nouvel essai est nécessaire.

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

Le double démarrage est volontairement refusé. Les scripts sans suffixe `-sdk` restent les scripts Canvas legacy et ne font pas partie du chemin validé.

## Contrat d'isolation

Le conteneur v2 `lea-openhands-sdk-smoke-v2` est limité à 4 Gio, 4 CPU et 512 PID. Il utilise exactement deux mounts :

```text
L:\IA_WORKSPACE -> /projects
lea_openhands_sdk_smoke_v2 -> /home/openhands/.openhands
```

Il est non privilégié, n'a pas de socket Docker, applique `no-new-privileges`, désactive VNC, VS Code, preload d'outils et webhooks. Il ne monte jamais `L:\Projet_Lea`. Docker conserve une connectivité potentielle vers `host.docker.internal` pour le LLM local, mais le smoke interdit réseau, téléchargements, Git et tout fichier hors du fixture. Ce smoke Linux ne valide ni PowerShell Windows, ni `lea.ps1`, ni Edge Stable, ni les validations Windows de l'étape 10.

`C:\Users\vdpst\.wslconfig` est absent. Aucun changement de `.wslconfig` ni `wsl --shutdown` n'a été effectué : `autoMemoryReclaim` ne remplace pas la RAM nécessaire à une charge active.

## Étape 10

L'étape 10 de Léa reste gelée. Le bootstrap 22K ne la valide pas et aucun commit n'est créé par ces scripts.
